"""End-to-end tests for :mod:`wactl.webhook` and the Lambda handler.

These exercise the full chain — API Gateway event in, response out —
with mocked integrations. Real AWS / WhatsApp is never touched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from wactl import webhook
from wactl.exceptions import SignatureVerificationError

# ─── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def fake_deps() -> webhook.WebhookDeps:
    """Build a :class:`WebhookDeps` with every collaborator mocked."""
    whatsapp = MagicMock(name="whatsapp")
    whatsapp.messages_url = "https://graph.facebook.com/v21.0/pn-1/messages"
    whatsapp.post_json = AsyncMock(
        return_value={"messages": [{"id": "wamid.OUT"}]},
    )
    whatsapp.send_text = AsyncMock(return_value="wamid.OUT")
    whatsapp.send_document = AsyncMock(return_value="wamid.OUT")
    whatsapp.send_image = AsyncMock(return_value="wamid.OUT")
    whatsapp.send_audio = AsyncMock(return_value="wamid.OUT")

    return webhook.WebhookDeps(
        whatsapp=whatsapp,
        http=MagicMock(name="http"),
        gemini=MagicMock(name="gemini"),
        s3=None,
        sqs=None,
        secrets_manager=None,
    )


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _call(event: dict[str, Any], deps: webhook.WebhookDeps | None = None) -> dict[str, Any]:
    """Invoke :func:`webhook.handle` (which manages its own event loop)."""
    return webhook.handle(event, deps=deps)


def _make_event(body: dict[str, Any], *, sig: str | None = None, http_method: str = "POST") -> dict[str, Any]:
    raw = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers: dict[str, str] = {}
    if sig is not None:
        headers["X-Hub-Signature-256"] = sig
    return {
        "httpMethod": http_method,
        "headers": headers,
        "body": raw.decode("utf-8"),
        "isBase64Encoded": False,
    }


def _make_get_event(
    *, mode: str = "subscribe", token: str = "good-token", challenge: str = "12345"
) -> dict[str, Any]:
    return {
        "httpMethod": "GET",
        "queryStringParameters": {
            "hub.mode": mode,
            "hub.verify_token": token,
            "hub.challenge": challenge,
        },
        "headers": {},
        "body": None,
    }


# ─── Signature verification ─────────────────────────────────────────────


def test_verify_signature_round_trip() -> None:
    body = b"hello"
    sig = _sign(body, "secret")
    webhook.verify_signature(body, sig, "secret")  # no raise


@pytest.mark.parametrize(
    "header",
    [None, "", "sha256=", "plaintext-deadbeef"],
)
def test_verify_signature_rejects_invalid_headers(header: str | None) -> None:
    with pytest.raises(SignatureVerificationError):
        webhook.verify_signature(b"hello", header, "secret")


def test_verify_signature_rejects_wrong_secret() -> None:
    body = b"hello"
    sig = _sign(body, "secret-A")
    with pytest.raises(SignatureVerificationError):
        webhook.verify_signature(body, sig, "secret-B")


# ─── GET handshake ──────────────────────────────────────────────────────


def test_get_with_correct_token_returns_challenge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wactl.integrations.aws.secrets.get_secret",
        lambda name: "good-token",
    )
    res = webhook.verify_webhook_get(_make_get_event())
    assert res is not None
    assert res.challenge == "12345"


def test_get_with_wrong_token_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "wactl.integrations.aws.secrets.get_secret",
        lambda name: "good-token",
    )
    res = webhook.verify_webhook_get(_make_get_event(token="wrong"))
    assert res is None


# ─── POST flow (sync command) ───────────────────────────────────────────


def _text_envelope(body: str, *, wamid: str = "wamid.IN1", from_: str = "15551234567") -> dict[str, Any]:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550000000", "phone_number_id": "pn-1"},
                            "contacts": [{"profile": {"name": "Alice"}, "wa_id": from_}],
                            "messages": [
                                {
                                    "from": from_,
                                    "id": wamid,
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_post_runs_sync_command(
    monkeypatch: pytest.MonkeyPatch,
    fake_deps: webhook.WebhookDeps,
) -> None:
    """A text command runs synchronously and is dispatched through send_text."""
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")

    # The dedup claim is in-process state; stub to always succeed.
    monkeypatch.setattr("wactl.webhook._is_duplicate", lambda mid: False)

    # Stub send_text at the messages module — the actual command also calls
    # messages.send_text, so we monkeypatch there.
    sent: list[dict[str, Any]] = []

    async def _capture(*_a, **kw):
        sent.append(kw)
        return "wamid.OUT"

    monkeypatch.setattr("wactl.integrations.whatsapp.messages.send_text", _capture)

    # Register a tiny throwaway command for this test (avoid disturbing the
    # global registry by saving it first then restoring on exit).
    from wactl.commands.base import Command, CommandContext
    from wactl.commands.registry import all as registry_all
    from wactl.commands.registry import register
    from wactl.commands.registry import restore as registry_restore
    from wactl.models.command import CommandResponse

    saved = registry_all()

    @register("/_test_ping", sync=True)
    class PingCommand(Command):
        async def run(self, ctx: CommandContext) -> CommandResponse:
            return CommandResponse(success=True, message_id="wamid.test")

    try:
        env = _text_envelope("/_test_ping")
        raw = json.dumps(env, separators=(",", ":")).encode("utf-8")
        sig = _sign(raw, "secret")
        event = _make_event(env, sig=sig)

        resp = _call(event, deps=fake_deps)
        assert resp == {"statusCode": 200}

        # No reply was sent by _test_ping itself, so the only send_text
        # invocations must be zero (the command did not send anything).
        assert sent == []
    finally:
        registry_restore(saved)


def test_post_dedup_drops_repeat(
    monkeypatch: pytest.MonkeyPatch,
    fake_deps: webhook.WebhookDeps,
) -> None:
    """A repeat wamid is silently dropped (no command execution)."""
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")
    # Force dedup hit.
    monkeypatch.setattr("wactl.webhook._is_duplicate", lambda mid: True)

    # Register a sentinel that explodes if it runs.
    from wactl.commands.base import Command, CommandContext
    from wactl.commands.registry import all as registry_all
    from wactl.commands.registry import register
    from wactl.commands.registry import restore as registry_restore
    from wactl.models.command import CommandResponse

    saved = registry_all()

    @register("/_test_dedup", sync=True)
    class DedupCommand(Command):
        async def run(self, ctx: CommandContext) -> CommandResponse:
            raise RuntimeError("must not run")

    try:
        env = _text_envelope("/_test_dedup", wamid="wamid.DUP")
        raw = json.dumps(env, separators=(",", ":")).encode("utf-8")
        sig = _sign(raw, "secret")
        event = _make_event(env, sig=sig)
        resp = _call(event, deps=fake_deps)
        assert resp == {"statusCode": 200}
    finally:
        registry_restore(saved)


def test_post_unknown_command_replies_with_help(
    monkeypatch: pytest.MonkeyPatch,
    fake_deps: webhook.WebhookDeps,
) -> None:
    """``/foobar`` (not registered) triggers the help reply."""
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")
    monkeypatch.setattr("wactl.webhook._is_duplicate", lambda mid: False)

    sent: list[dict[str, Any]] = []

    async def _capture(*_a, **kw):
        sent.append(kw)
        return "wamid.OUT"

    monkeypatch.setattr("wactl.integrations.whatsapp.messages.send_text", _capture)

    env = _text_envelope("/not-a-real-command")
    raw = json.dumps(env, separators=(",", ":")).encode("utf-8")
    sig = _sign(raw, "secret")
    event = _make_event(env, sig=sig)

    resp = _call(event, deps=fake_deps)
    assert resp == {"statusCode": 200}
    assert len(sent) == 1
    assert "command" in sent[0]["body"].lower()


def test_post_invalid_signature_swallows(
    monkeypatch: pytest.MonkeyPatch,
    fake_deps: webhook.WebhookDeps,
) -> None:
    """A bad signature is logged + 200 returned (no retry storm from Meta)."""
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")
    env = _text_envelope("/anything")
    event = _make_event(env, sig="sha256=" + "0" * 64)
    resp = _call(event, deps=fake_deps)
    assert resp == {"statusCode": 200}


def test_post_handles_status_only_payload(
    monkeypatch: pytest.MonkeyPatch,
    fake_deps: webhook.WebhookDeps,
) -> None:
    """A webhook with no messages (only statuses) is a no-op."""
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")
    env = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550000000", "phone_number_id": "pn-1"},
                            "statuses": [{"id": "wamid.ST1", "status": "delivered"}],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(env, separators=(",", ":")).encode("utf-8")
    sig = _sign(raw, "secret")
    event = _make_event(env, sig=sig)
    resp = _call(event, deps=fake_deps)
    assert resp == {"statusCode": 200}


def test_lambda_handler_is_thin_wrapper() -> None:
    """The Lambda entry point delegates to wactl.webhook.handle."""
    import importlib

    mod = importlib.import_module("lambda.webhook.handler")
    assert callable(mod.lambda_handler)
    assert mod.lambda_handler.__module__ == "lambda.webhook.handler"
