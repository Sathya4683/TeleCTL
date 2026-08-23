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
        chat_id=111111111,
        username="alice",
        first_name="Alice",
        message_id=42,
    )


def make_context(
    *,
    user: UserContext | None = None,
    args: str = "",
    media_bytes: bytes | None = None,
    media_mime_type: str | None = None,
    media_filename: str | None = None,
    telegram: Any = None,
    s3: Any = None,
    s3_bucket: str = "wactl-media-test",
    http: Any = None,
    gemini: Any | None = None,
    extra: dict[str, Any] | None = None,
) -> CommandContext:
    """Build a :class:`CommandContext` with sensible test defaults."""
    return CommandContext(
        user=user or make_user(),
        args=args,
        raw_body="",
        media_id="AgAC-test-file-id" if media_bytes is not None else None,
        media_bytes=media_bytes,
        media_mime_type=media_mime_type,
        media_filename=media_filename,
        telegram=telegram,
        s3=s3,
        http=http,
        gemini=gemini,
        s3_bucket=s3_bucket,  # type: ignore[call-arg]
        **(extra or {}),
    )


@pytest.fixture
def fake_telegram() -> MagicMock:
    """A :class:`MagicMock` standing in for a :class:`TelegramClient`.

    All HTTP-bound methods are :class:`AsyncMock` returning a numeric
    message_id so they can be awaited anywhere commands call them.
    """
    client = MagicMock(name="telegram")
    client.bot_token = "test-token"
    client.api_base = "https://api.telegram.org"

    # Direct methods — also async.
    client.send_message = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999)),
    )
    client.send_photo = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999)),
    )
    client.send_document = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999)),
    )
    client.send_audio = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999)),
    )
    client.send_voice = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999)),
    )
    client.send_chat_action = AsyncMock(
        return_value=MagicMock(result=True),
    )
    client.get_file = AsyncMock(
        return_value=MagicMock(result=MagicMock(file_path="photos/file_0.jpg")),
    )
    client.download_file = AsyncMock(return_value=b"binary-blob")

    # High-level convenience used by commands/messages.py.
    client.aclose = AsyncMock()
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
