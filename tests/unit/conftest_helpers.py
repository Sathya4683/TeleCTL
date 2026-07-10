"""Shared fixtures for command-level unit tests.

These helpers build mock :class:`CommandContext` objects and the
fakes they depend on. Tests import from here to keep boilerplate down.

This module is intentionally NOT prefixed with ``test_`` so pytest does
not collect it as a test file.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from wactl.commands.base import CommandContext
from wactl.models.user import UserContext


def make_user() -> UserContext:
    """Construct a deterministic :class:`UserContext`."""
    return UserContext(
        phone="15551234567",
        name="alice",
        message_id="wamid.TEST",
        waba_id="waba-1",
        phone_number_id="pn-1",
    )


def make_context(
    *,
    user: UserContext | None = None,
    args: str = "",
    media_bytes: bytes | None = None,
    media_mime_type: str | None = None,
    media_filename: str | None = None,
    whatsapp: Any = None,
    s3: Any = None,
    s3_bucket: str = "wactl-media-test",
    http: Any = None,
    gemini: Any = None,
    extra: dict[str, Any] | None = None,
) -> CommandContext:
    """Build a :class:`CommandContext` with sensible test defaults."""
    return CommandContext(
        user=user or make_user(),
        args=args,
        raw_body="",
        media_id="mid.test" if media_bytes is not None else None,
        media_bytes=media_bytes,
        media_mime_type=media_mime_type,
        media_filename=media_filename,
        whatsapp=whatsapp,
        s3=s3,
        http=http,
        gemini=gemini,
        s3_bucket=s3_bucket,  # type: ignore[call-arg]
        **(extra or {}),
    )


@pytest.fixture
def fake_whatsapp() -> MagicMock:
    """A :class:`MagicMock` standing in for a :class:`WhatsAppClient`.

    All HTTP-bound methods are :class:`AsyncMock` returning a wamid or
    the right empty shape so it can be awaited anywhere commands call it.
    """
    client = MagicMock(name="whatsapp")
    client.messages_url = "https://graph.facebook.com/v21.0/pn-1/messages"
    # Sub-methods on the wrapper — also async.
    client.post_json = AsyncMock(
        return_value={"messages": [{"id": "wamid.OUT"}]},
    )
    client.get_json = AsyncMock(
        return_value={"url": "https://look.example/b", "messages": [{"id": "wamid.OUT"}]},
    )
    client.get_bytes = AsyncMock(return_value=b"binary-blob")
    # High-level send_* — convenience, also async.
    client.send_text = AsyncMock(return_value="wamid.OUT")
    client.send_document = AsyncMock(return_value="wamid.OUT")
    client.send_image = AsyncMock(return_value="wamid.OUT")
    client.send_audio = AsyncMock(return_value="wamid.OUT")
    return client


@pytest.fixture
def fake_s3(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch :mod:`wactl.integrations.aws.s3` with an in-memory fake."""
    fake = MagicMock(name="s3")
    fake.put_object = MagicMock()
    fake.presigned_get_url = MagicMock(return_value="https://example.com/presigned")
    fake.make_key = MagicMock(side_effect=lambda *parts: "/".join(parts))
    monkeypatch.setattr("wactl.integrations.aws.s3", fake)
    return fake
