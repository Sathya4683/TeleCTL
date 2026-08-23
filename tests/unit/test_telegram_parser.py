"""Tests for :mod:`wactl.integrations.telegram.parser`."""

from __future__ import annotations

import pytest

from wactl.exceptions import WebhookError
from wactl.integrations.telegram.parser import parse_envelope


def _envelope(text: str | None = None, **media_kwargs) -> dict:
    """Build a minimal Update envelope with a text message by default."""
    msg: dict = {
        "message_id": 1,
        "from": {"id": 100, "first_name": "Alice", "username": "alice"},
        "chat": {"id": 100, "type": "private"},
        "date": 1700000000,
    }
    if text is not None:
        msg["text"] = text
    if media_kwargs:
        msg.update(media_kwargs)
    return {"update_id": 1, "message": msg}


def test_parses_text_command() -> None:
    parsed = parse_envelope(_envelope(text="/image-resize 800x600"))
    assert len(parsed) == 1
    p = parsed[0]
    assert p.body == "/image-resize 800x600"
    assert p.user.chat_id == 100
    assert p.user.message_id == 1
    assert p.media_id is None


def test_parses_caption_as_body() -> None:
    """Photos sent with a caption should still route as a command."""
    parsed = parse_envelope(
        _envelope(
            caption="/image-resize 800x600",
            photo=[{"file_id": "ABC", "width": 100, "height": 100, "file_unique_id": "u"}],
        )
    )
    p = parsed[0]
    assert p.body == "/image-resize 800x600"
    # photo's last entry is selected as the full-res file_id
    assert p.media_id == "ABC"
    assert p.media_mime == "image/jpeg"


def test_parses_photo_picks_last_size() -> None:
    parsed = parse_envelope(
        _envelope(
            photo=[
                {"file_id": "THUMB", "width": 90, "height": 90, "file_unique_id": "t"},
                {"file_id": "FULL", "width": 800, "height": 600, "file_unique_id": "f"},
            ],
        )
    )
    p = parsed[0]
    assert p.media_id == "FULL"
    assert p.media_mime == "image/jpeg"


def test_parses_document_with_filename() -> None:
    parsed = parse_envelope(
        _envelope(
            document={
                "file_id": "DOC",
                "file_unique_id": "u",
                "file_name": "report.pdf",
                "mime_type": "application/pdf",
            },
        )
    )
    p = parsed[0]
    assert p.media_id == "DOC"
    assert p.media_mime == "application/pdf"
    assert p.media_filename == "report.pdf"


def test_parses_voice() -> None:
    parsed = parse_envelope(
        _envelope(voice={"file_id": "V", "file_unique_id": "u", "duration": 5})
    )
    p = parsed[0]
    assert p.media_id == "V"
    assert p.media_mime == "audio/ogg"


def test_empty_envelope_returns_empty_list() -> None:
    """Updates without a ``message`` field (e.g. callback_query) are ignored."""
    parsed = parse_envelope({"update_id": 1})
    assert parsed == []


def test_message_without_from_is_skipped() -> None:
    """Channel posts have no `from`; skip them for now."""
    parsed = parse_envelope(
        {"update_id": 1, "message": {"message_id": 1, "chat": {"id": 9, "type": "channel"}, "date": 0}}
    )
    assert parsed == []


def test_malformed_envelope_raises_webhook_error() -> None:
    with pytest.raises(WebhookError):
        parse_envelope({"update_id": 1, "message": {"this is wrong": True}})
