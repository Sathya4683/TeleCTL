"""Core webhook logic shared by the Lambda and the worker.

The :func:`handle` function is the single entry-point for any incoming
webhook event. It performs, in order:

1. **Optional secret-token check** — if ``TELEGRAM_WEBHOOK_SECRET_TOKEN`` is
   set, we verify the ``X-Telegram-Bot-Api-Secret-Token`` header.
2. **Body decoding** — API Gateway passes the body as a string unless it
   was binary; we always work with ``bytes`` then decode to JSON.
3. **Parse + dedup** — extract the message list; claim the message_id in
   DynamoDB so retries don't double-process.
4. **Route + dispatch** — for text messages, look up the command and
   either run it inline (sync) or enqueue a job (async).
5. **Always return 200** — Telegram DOES retry on non-2xx (up to 8
   attempts with exponential backoff over ~30 min). We still swallow
   internal errors at the boundary so a permanently-bad Update doesn't
   spam Telegram's retry loop.

The function is intentionally synchronous-callable by both ``asyncio.run``
(Lambda) and direct invocation (tests).
"""

from __future__ import annotations

import asyncio
import base64
import hmac
from dataclasses import dataclass
from typing import Any

import structlog

from wactl.commands import (  # noqa: F401 — side-effect: registers commands
    help,
    image_compress,
    image_resize,
)
from wactl.commands import registry as cmd_registry  # noqa: F401 — ensure imports register
from wactl.config import settings
from wactl.dispatcher import dispatch_async, dispatch_sync
from wactl.exceptions import (
    CommandNotFoundError,
    ConfigError,
    DuplicateMessageError,
    SignatureVerificationError,
    UserInputError,
    WactlError,
    WebhookError,
)
from wactl.integrations.aws import dynamodb
from wactl.integrations.telegram import messages as tg_messages
from wactl.integrations.telegram.parser import parse_envelope
from wactl.logging import bind_context, reset_context
from wactl.router import route

logger = structlog.get_logger(__name__)

SECRET_HEADER = "x-telegram-bot-api-secret-token"


@dataclass(frozen=True)
class WebhookDeps:
    """All the integrations a webhook invocation needs.

    Built once per process by :func:`build_deps`. Tests can build their
    own versions with mocks; production wires the real Telegram client.
    """

    telegram: Any
    http: Any
    s3: Any
    sqs: Any


def build_deps() -> WebhookDeps:
    """Construct production integrations from settings.

    Bot token is read from ``settings.telegram_bot_token`` (plain env
    var). HTTP and AWS clients are lazy singletons in the integration
    modules; we only build the Telegram wrapper here.
    """
    if not settings.telegram_bot_token:
        raise ConfigError(
            "TELEGRAM_BOT_TOKEN is not set",
            user_message="Service is misconfigured. Please try again later.",
        )

    # Lazy import keeps cold-start latency small.
    from wactl.integrations.telegram.client import TelegramClient  # noqa: PLC0415

    telegram = TelegramClient(
        bot_token=settings.telegram_bot_token,
        api_base=settings.telegram_api_base,
        timeout_seconds=settings.http_timeout_seconds,
    )

    http = None
    if settings.s3_media_bucket:
        # Lazy: only build an HTTP client if any sync command uses one.
        import httpx  # noqa: PLC0415 — local to avoid top-level latency

        http = httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    # SQS client is needed only for /pdf-audio (the only async command). We
    # build it lazily only when the queue URL is configured, so the Lambda
    # container can cold-start quickly when no /pdf-audio jobs are expected.
    sqs = None
    if settings.sqs_jobs_queue_url:
        from wactl.integrations.aws import sqs as _sqs  # noqa: PLC0415

        sqs = _sqs

    return WebhookDeps(
        telegram=telegram,
        http=http,
        s3=None,
        sqs=sqs,
    )


def _decode_body(event: dict[str, Any]) -> bytes:
    """Return the POST body as bytes, base64-decoding if API Gateway flagged it."""
    body: Any = event.get("body", "")
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8")


def _verify_secret_token(
    headers: dict[str, str],
    expected: str,
) -> None:
    """Verify the ``X-Telegram-Bot-Api-Secret-Token`` header in constant time.

    Raises :class:`SignatureVerificationError` if the header is missing or
    doesn't match.
    """
    provided = headers.get(SECRET_HEADER) or headers.get(SECRET_HEADER.lower())
    if not provided or not hmac.compare_digest(provided, expected):
        raise SignatureVerificationError(
            "Missing or mismatched X-Telegram-Bot-Api-Secret-Token"
        )


def _is_duplicate(message_id: int) -> bool:
    """Return True if we've already claimed this message_id in DynamoDB."""
    try:
        claimed = dynamodb.try_claim(
            settings.dynamodb_dedup_table,
            str(message_id),
            ttl_seconds=settings.dedup_ttl_seconds,
        )
    except WactlError:
        # If dedup is unavailable we fail open — better to risk a double
        # process than to drop a real user message.
        return False
    return not claimed


async def _process_message(
    *,
    parsed: Any,
    deps: WebhookDeps,
) -> None:
    """Route + dispatch a single parsed Telegram message."""
    user = parsed.user

    # Text-only path: body must start with "/".
    if parsed.body is None:
        logger.info("webhook.ignored_non_text", message_id=user.message_id)
        return

    body = parsed.body
    if not body.startswith("/"):
        logger.info("webhook.ignored_non_command", message_id=user.message_id)
        return

    try:
        routed = route(body)
    except CommandNotFoundError:
        logger.info("webhook.unknown_command", body=body[:64])
        await tg_messages.send_text(
            deps.telegram,
            chat_id=user.chat_id,
            text="Send a command starting with '/' (e.g. /help, /image-resize).",
            reply_to_message_id=user.message_id,
        )
        return

    try:
        if routed.cls.meta.sync:
            resp = await dispatch_sync(
                routed,
                user=user,
                telegram=deps.telegram,
                http=deps.http,
                s3=deps.s3,
                secrets=None,
                media_id=parsed.media_id,
                media_mime=parsed.media_mime,
                media_filename=parsed.media_filename,
                raw_body=body,
            )
            logger.info(
                "command.sync.complete",
                command=routed.name,
                success=resp.success,
            )
        else:
            await dispatch_async(
                routed,
                user=user,
                sqs=deps.sqs,
                queue_url=settings.sqs_jobs_queue_url,
                media_id=parsed.media_id,
                media_mime=parsed.media_mime,
                media_filename=parsed.media_filename,
                message_group_id=str(user.chat_id),
            )
            logger.info("command.async.enqueued", command=routed.name)
    except UserInputError as exc:
        logger.info("command.user_error", command=routed.name, message=str(exc))
        await tg_messages.send_text(
            deps.telegram,
            chat_id=user.chat_id,
            text=exc.user_message,
            reply_to_message_id=user.message_id,
        )
    except WactlError as exc:
        logger.error(
            "command.failed",
            command=routed.name,
            error=type(exc).__name__,
            message=str(exc),
        )


async def _handle_post_async(
    event: dict[str, Any],
    deps: WebhookDeps,
) -> dict[str, Any]:
    """Process a POST webhook payload asynchronously."""
    raw_body = _decode_body(event)

    # Optional secret-token check.
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    if settings.telegram_webhook_secret_token:
        try:
            _verify_secret_token(headers, settings.telegram_webhook_secret_token)
        except SignatureVerificationError as exc:
            logger.warning("webhook.secret_token_invalid", message=str(exc))
            # 401 is the right answer for a bad shared secret.
            return {"statusCode": 401, "body": "forbidden"}

    try:
        import json as _json  # noqa: PLC0415 — local import keeps top-level clean

        payloads = parse_envelope(_json.loads(raw_body))
    except WebhookError as exc:
        logger.warning("webhook.parse_failed", message=str(exc))
        return {"statusCode": 200}

    for parsed in payloads:
        with bind_context(
            message_id=str(parsed.user.message_id),
            chat_id=str(parsed.user.chat_id),
        ):
            if _is_duplicate(parsed.user.message_id):
                logger.info("webhook.duplicate_dropped")
                continue
            await _process_message(parsed=parsed, deps=deps)

    return {"statusCode": 200}


def handle(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps: WebhookDeps | None = None,
) -> dict[str, Any]:
    """Entry point — Lambda calls this with the API Gateway event.

    ``deps`` is injected in tests; production builds them once per
    container.
    """
    reset_context()

    if deps is None:
        try:
            deps = build_deps()
        except ConfigError as exc:
            logger.error("webhook.config_error", message=str(exc))
            return {"statusCode": 500, "body": "misconfigured"}

    try:
        return _dispatch_post(event, deps)
    except SignatureVerificationError as exc:
        logger.warning("webhook.signature_invalid", message=str(exc))
        return {"statusCode": 401, "body": "forbidden"}
    except DuplicateMessageError:
        return {"statusCode": 200}
    except WactlError as exc:
        logger.error(
            "webhook.unhandled",
            error=type(exc).__name__,
            message=str(exc),
        )
        return {"statusCode": 200}
    except Exception as exc:
        logger.error("webhook.unexpected_exception", error=type(exc).__name__, message=str(exc))
        return {"statusCode": 200}


async def handle_async(
    event: dict[str, Any],
    context: Any = None,
    *,
    deps: WebhookDeps | None = None,
) -> dict[str, Any]:
    """Async entry point. Tests use this; Lambda uses :func:`handle`."""
    reset_context()

    if deps is None:
        try:
            deps = build_deps()
        except ConfigError as exc:
            logger.error("webhook.config_error", message=str(exc))
            return {"statusCode": 500, "body": "misconfigured"}

    try:
        return await _handle_post_async(event, deps)
    except SignatureVerificationError as exc:
        logger.warning("webhook.signature_invalid", message=str(exc))
        return {"statusCode": 401, "body": "forbidden"}
    except DuplicateMessageError:
        return {"statusCode": 200}
    except WactlError as exc:
        logger.error(
            "webhook.unhandled",
            error=type(exc).__name__,
            message=str(exc),
        )
        return {"statusCode": 200}
    except Exception as exc:
        logger.error("webhook.unexpected_exception", error=type(exc).__name__, message=str(exc))
        return {"statusCode": 200}


def _dispatch_post(event: dict[str, Any], deps: WebhookDeps) -> dict[str, Any]:
    """Run the async handler via :func:`asyncio.run`.

    Production cold-start path. Tests call :func:`handle_async` instead
    (asyncio.run would fail inside a running event loop).
    """
    return asyncio.run(_handle_post_async(event, deps))


__all__ = [
    "SECRET_HEADER",
    "WebhookDeps",
    "build_deps",
    "handle",
    "handle_async",
]
