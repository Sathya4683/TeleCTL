"""End-to-end Telegram webhook tests.

These exercise the full path: API Gateway event → webhook handler →
parser → dispatcher → command. S3 / DynamoDB are mocked via moto; the
Telegram client is a ``MagicMock`` so no real HTTP calls are made.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from wactl import webhook
from wactl.config import settings
from wactl.integrations.telegram.client import TelegramClient
from wactl.webhook import WebhookDeps


def _make_event(body_dict: dict, *, http_method: str = "POST") -> dict:
    raw = json.dumps(body_dict, separators=(",", ":")).encode("utf-8")
    return {
        "httpMethod": http_method,
        "headers": {"content-type": "application/json"},
        "body": raw.decode(),
        "isBase64Encoded": False,
    }


def _load_fixture(name: str) -> dict:
    import pathlib

    p = pathlib.Path(__file__).resolve().parents[1] / "fixtures" / name
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.fixture
def deps(monkeypatch: pytest.MonkeyPatch) -> WebhookDeps:
    """Wire WebhookDeps with a fake Telegram client + dedup helper.

    The DynamoDB dedup table is mocked to always return ``True`` (claim
    succeeds) so the message gets processed.
    """

    def fake_try_claim(table: str, message_id: str, *, ttl_seconds: int, metadata=None) -> bool:
        return True

    monkeypatch.setattr("wactl.webhook.dynamodb.try_claim", fake_try_claim)

    tg = MagicMock(spec=TelegramClient)
    tg.bot_token = "test-token"
    tg.api_base = "https://api.telegram.org"
    tg.send_message = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999))
    )
    tg.send_photo = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999))
    )
    tg.send_document = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999))
    )
    tg.send_audio = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999))
    )
    tg.send_chat_action = AsyncMock(
        return_value=MagicMock(result=True)
    )
    tg.aclose = AsyncMock()
    return WebhookDeps(telegram=tg, http=None, s3=None, sqs=None)


# ─── happy paths ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_help_command_returns_command_list(deps: WebhookDeps) -> None:
    event = _make_event(_load_fixture("telegram_text_update.json").copy())
    # rewrite body to /help
    event["body"] = json.dumps(
        {
            "update_id": 1,
            "message": {
                "message_id": 1,
                "from": {"id": 1001, "is_bot": False, "first_name": "Alice"},
                "chat": {"id": 1001, "type": "private"},
                "date": 1700000000,
                "text": "/help",
            },
        }
    )
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200
    deps.telegram.send_message.assert_awaited()
    # messages.send_text calls client.send_message with (chat_id, text, ...) — both positional.
    args = deps.telegram.send_message.await_args.args
    text = args[1]
    assert "/help" in text
    assert "/image-resize" in text
    assert "/pdf-audio" in text


@pytest.mark.asyncio
async def test_unknown_command_replies_with_hint(deps: WebhookDeps) -> None:
    event = _make_event(
        {
            "update_id": 1,
            "message": {
                "message_id": 2,
                "from": {"id": 1001, "is_bot": False, "first_name": "Alice"},
                "chat": {"id": 1001, "type": "private"},
                "date": 1700000000,
                "text": "/nope",
            },
        }
    )
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200
    deps.telegram.send_message.assert_awaited()
    args = deps.telegram.send_message.await_args.args
    assert "/" in args[1]


@pytest.mark.asyncio
async def test_plain_message_without_slash_is_ignored(deps: WebhookDeps) -> None:
    event = _make_event(
        {
            "update_id": 1,
            "message": {
                "message_id": 3,
                "from": {"id": 1001, "is_bot": False, "first_name": "Alice"},
                "chat": {"id": 1001, "type": "private"},
                "date": 1700000000,
                "text": "hello there",
            },
        }
    )
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200
    # No outbound calls — the bot only responds to slash-commands.
    deps.telegram.send_message.assert_not_awaited()
    deps.telegram.send_photo.assert_not_awaited()


# ─── secret-token ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_secret_token_mismatch_returns_401(
    monkeypatch: pytest.MonkeyPatch, deps: WebhookDeps
) -> None:
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "expected", raising=False)
    event = _make_event(_load_fixture("telegram_text_update.json").copy())
    event["headers"] = {"x-telegram-bot-api-secret-token": "wrong"}
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 401


@pytest.mark.asyncio
async def test_secret_token_match_passes(
    monkeypatch: pytest.MonkeyPatch, deps: WebhookDeps
) -> None:
    monkeypatch.setattr(settings, "telegram_webhook_secret_token", "expected", raising=False)
    event = _make_event(_load_fixture("telegram_text_update.json").copy())
    event["headers"] = {"x-telegram-bot-api-secret-token": "expected"}
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200


@pytest.mark.asyncio
async def test_secret_token_unset_skips_check(deps: WebhookDeps) -> None:
    """No header needed when TELEGRAM_WEBHOOK_SECRET_TOKEN is unset."""
    event = _make_event(_load_fixture("telegram_text_update.json").copy())
    event["headers"] = {}
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200


# ─── malformed payload ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_malformed_payload_returns_200(deps: WebhookDeps) -> None:
    """Webhook always returns 200 (Telegram doesn't auto-retry, but be polite)."""
    event = _make_event({"this is not a valid update": True})
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200


# ─── async dispatch ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pdf_audio_enqueues_to_sqs(
    monkeypatch: pytest.MonkeyPatch, deps: WebhookDeps
) -> None:
    """``/pdf-audio`` should hit ``dispatch_async`` → SQS send_message."""

    sent: list[dict[str, object]] = []

    async def _fake_dispatch_async(*_a, **_kw):
        sent.append({"kw": _kw})
        return "msg-id"

    # webhook.py imports dispatch_async directly, so we patch the binding
    # inside the webhook module (not the source module).
    monkeypatch.setattr(webhook, "dispatch_async", _fake_dispatch_async)

    event = _make_event(
        {
            "update_id": 1,
            "message": {
                "message_id": 4,
                "from": {"id": 1001, "is_bot": False, "first_name": "Alice"},
                "chat": {"id": 1001, "type": "private"},
                "date": 1700000000,
                "caption": "/pdf-audio",
                "document": {
                    "file_id": "DOC1",
                    "file_unique_id": "u",
                    "file_name": "a.pdf",
                    "mime_type": "application/pdf",
                },
            },
        }
    )
    resp = await webhook.handle_async(event, deps=deps)
    assert resp["statusCode"] == 200
    assert len(sent) == 1
    # message_group_id is the chat_id (FIFO ordering per user)
    assert sent[0]["kw"]["message_group_id"] == "1001"
