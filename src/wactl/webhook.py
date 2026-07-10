"""Core webhook logic shared by Lambda + worker.

The :func:`handle` function is the single entry-point for any incoming
webhook event. It performs, in order:

1. **GET handshake** — Meta sends a GET to ``/webhook`` during webhook
   registration; we echo ``hub.challenge`` if the verify token matches.
2. **HMAC verification** — POSTs ship an ``X-Hub-Signature-256`` header
   we must verify against the raw body using the app secret from Secrets
   Manager.
3. **Body decoding** — API Gateway passes the body as a string unless
   it was binary. We always work with ``bytes``.
4. **Parse + dedup** — extract the message list; claim the message_id in
   DynamoDB so Meta's retries don't double-process.
5. **Route + dispatch** — for text messages, look up the command and
   either run it inline (sync) or enqueue a job (async).
6. **Always return 200** — Meta retries up to 7 days on non-200, so any
   internal error is logged + swallowed at the boundary.

The function is intentionally synchronous-callable by both ``asyncio.run``
(Lambda) and direct invocation (tests).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

import structlog

from wactl.commands import (  # noqa: F401 — side-effect: registers commands
    github_pr,
    image_compress,
    image_resize,
    merge_pdf,
    pdf_audio,
    pdf_docx,
    split_pdf,
    translate,
    web_summary,
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
from wactl.integrations.aws import dynamodb, secrets
from wactl.integrations.whatsapp import messages as wa_messages
from wactl.integrations.whatsapp.parser import parse_envelope
from wactl.logging import bind_context, reset_context
from wactl.router import route

logger = structlog.get_logger(__name__)

SIG_HEADER = "X-Hub-Signature-256"
SIG_PREFIX = "sha256="


@dataclass(frozen=True)
class VerificationResult:
    """The required response body for a webhook verification GET."""

    challenge: str


def _decode_body(event: dict[str, Any]) -> bytes:
    """Return the POST body as bytes, base64-decoding if API Gateway flagged it."""
    body: Any = event.get("body", "")
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8")


def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> None:
    """Raise :class:`SignatureVerificationError` if the HMAC is missing or invalid.

    Meta sends ``sha256=<hex>``. We recompute ``hmac_sha256(raw_body, app_secret)``
    and compare in constant time.
    """
    if not signature_header or not signature_header.startswith(SIG_PREFIX):
        raise SignatureVerificationError("Missing or malformed signature header")
    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    provided = signature_header[len(SIG_PREFIX) :].strip()
    if not hmac.compare_digest(expected, provided):
        raise SignatureVerificationError("HMAC mismatch")


def verify_webhook_get(event: dict[str, Any]) -> VerificationResult | None:
    """Handle a GET request from Meta's webhook registration handshake.

    Returns a :class:`VerificationResult` if the token matches, ``None`` otherwise.
    Meta is happy with a 200 containing the challenge; we never send a 403.
    """
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    if mode != "subscribe" or not challenge:
        return None
    expected_token = secrets.get_secret(settings.whatsapp_verify_token_secret)
    if params.get("hub.verify_token") == expected_token:
        logger.info("webhook.verified", mode=mode)
        return VerificationResult(challenge=challenge)
    logger.warning("webhook.verify_token_mismatch")
    return None


@dataclass(frozen=True)
class WebhookDeps:
    """All the integrations a webhook invocation needs.

    Built once per process by :func:`build_deps`. Tests can build their own
    versions with mocks; production wires real AWS + WhatsApp clients.
    """

    whatsapp: Any
    http: Any
    gemini: Any
    s3: Any
    sqs: Any
    secrets_manager: Any


def build_deps(*, access_token: str | None = None) -> WebhookDeps:
    """Construct production integrations from settings + Secrets Manager.

    The optional ``access_token`` parameter is reserved for tests that want
    to inject a deterministic token without hitting Secrets Manager.
    """
    # Lazy imports to keep cold-start latency small in Lambda.
    from wactl.integrations.gemini.client import GeminiClient  # noqa: PLC0415
    from wactl.integrations.whatsapp.client import WhatsAppClient  # noqa: PLC0415

    token = access_token or secrets.get_secret(settings.whatsapp_access_token_secret)
    whatsapp = WhatsAppClient(
        api_version=settings.whatsapp_api_version,
        phone_number_id=settings.whatsapp_phone_number_id,
        access_token=token,
    )

    gemini_key = secrets.get_secret(settings.gemini_api_key_secret)
    gemini = GeminiClient(api_key=gemini_key, text_model=settings.gemini_text_model)

    http = None
    if settings.s3_media_bucket:
        # Lazy: only build an HTTP client if any sync command uses one.
        import httpx  # noqa: PLC0415 — local to avoid top-level latency

        http = httpx.AsyncClient(timeout=settings.http_timeout_seconds)

    return WebhookDeps(
        whatsapp=whatsapp,
        http=http,
        gemini=gemini,
        s3=None,
        sqs=None,
        secrets_manager=None,
    )


def _is_duplicate(message_id: str) -> bool:
    """Return True if we've already claimed this wamid in DynamoDB."""
    try:
        claimed = dynamodb.try_claim(
            settings.dynamodb_dedup_table,
            message_id,
            ttl_seconds=settings.dedup_ttl_seconds,
        )
    except WactlError:
        # If dedup is unavailable we fail open — better to risk a double
        # process than to drop a real user message.
        return False
    return not claimed


async def _process_text(
    *,
    user: Any,
    body: str,
    raw_body: str,
    deps: WebhookDeps,
) -> None:
    """Route + dispatch a text command. Errors are logged, never re-raised."""
    try:
        routed = route(body)
    except CommandNotFoundError:
        # Unknown command — tell the user what commands are available.
        await wa_messages.send_text(
            deps.whatsapp,
            to=user.phone,
            body="Send a command starting with '/' (e.g. /pdf-docx, /image-resize).",
            reply_to_message_id=user.message_id,
        )
        return

    try:
        if routed.cls.meta.sync:
            resp = await dispatch_sync(
                routed,
                user=user,
                whatsapp=deps.whatsapp,
                http=deps.http,
                gemini=deps.gemini,
                s3=deps.s3,
                secrets=deps.secrets_manager,
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
            )
            logger.info("command.async.enqueued", command=routed.name)
    except UserInputError as exc:
        logger.info("command.user_error", command=routed.name, message=str(exc))
        # Surface the friendly user_message; ignore the technical one.
        await wa_messages.send_text(
            deps.whatsapp,
            to=user.phone,
            body=exc.user_message,
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
    app_secret = secrets.get_secret(settings.whatsapp_app_secret_secret)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    verify_signature(raw_body, headers.get(SIG_HEADER.lower()), app_secret)

    try:
        import json as _json  # noqa: PLC0415 — local import keeps top-level clean

        payloads = parse_envelope(_json.loads(raw_body))
    except WebhookError as exc:
        logger.warning("webhook.parse_failed", message=str(exc))
        return {"statusCode": 200}

    for parsed in payloads:
        with bind_context(message_id=parsed.user.message_id, user_phone=parsed.user.phone):
            if _is_duplicate(parsed.user.message_id):
                logger.info("webhook.duplicate_dropped")
                continue
            if parsed.message.type == "text":
                await _process_text(
                    user=parsed.user,
                    body=parsed.message.body,
                    raw_body=raw_body.decode("utf-8", errors="replace"),
                    deps=deps,
                )
            else:
                # Media messages without a slash-command: acknowledge so Meta
                # doesn't retry. Commands that need an attachment are always
                # triggered by a slash-command, so plain media is inert.
                logger.info("webhook.ignored_media_without_command")

    return {"statusCode": 200}


def handle(  # noqa: PLR0911 — many early-returns for distinct error paths
    event: dict[str, Any],
    context: Any = None,
    *,
    deps: WebhookDeps | None = None,
) -> dict[str, Any]:
    """Entry point — Lambda calls this with the API Gateway event.

    ``deps`` is injected in tests; production builds them once per container.
    """
    reset_context()
    http_method = (
        event.get("httpMethod") or event.get("requestContext", {}).get("http", {}).get("method") or "POST"
    ).upper()

    if http_method == "GET":
        verdict = verify_webhook_get(event)
        if verdict is None:
            return {"statusCode": 403, "body": "Forbidden"}
        return {"statusCode": 200, "body": verdict.challenge}

    if deps is None:
        try:
            deps = build_deps()
        except ConfigError as exc:
            logger.error("webhook.config_error", message=str(exc))
            return {"statusCode": 500, "body": "misconfigured"}

    try:
        return _dispatch_post(event, deps)
    except SignatureVerificationError as exc:
        # Meta retries on non-200, but never reveal the failure to attackers.
        logger.warning("webhook.signature_invalid", message=str(exc))
        return {"statusCode": 200}
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

    The Lambda cold-start path — production only. Tests call
    :func:`handle` from inside a running loop and should use
    :func:`handle_async` instead, or wrap the call in their own
    ``asyncio.run`` boundary.
    """
    return asyncio.run(_handle_post_async(event, deps))


__all__ = [
    "SIG_HEADER",
    "SIG_PREFIX",
    "VerificationResult",
    "WebhookDeps",
    "build_deps",
    "handle",
    "verify_signature",
    "verify_webhook_get",
]
