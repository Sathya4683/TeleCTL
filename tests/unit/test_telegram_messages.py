"""Tests for :mod:`wactl.integrations.telegram.messages` (high-level helpers)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wactl.integrations.telegram import messages


def _client(message_id: int = 999) -> MagicMock:
    """MagicMock TelegramClient with every send_* method returning a result."""
    client = MagicMock()
    resp = MagicMock()
    resp.result = MagicMock()
    resp.result.message_id = message_id
    for m in (
        "send_message",
        "send_photo",
        "send_document",
        "send_audio",
        "send_voice",
        "send_chat_action",
    ):
        setattr(client, m, AsyncMock(return_value=resp))
    return client


@pytest.mark.asyncio
async def test_send_text_returns_message_id_str() -> None:
    new_id = await messages.send_text(_client(), chat_id=42, text="hi")
    assert new_id == "999"


@pytest.mark.asyncio
async def test_send_photo_requires_link_or_file_id() -> None:
    with pytest.raises(ValueError):
        await messages.send_photo(_client(), chat_id=42)


@pytest.mark.asyncio
async def test_send_photo_rejects_both_link_and_file_id() -> None:
    with pytest.raises(ValueError):
        await messages.send_photo(_client(), chat_id=42, link="x", file_id="y")


@pytest.mark.asyncio
async def test_send_document_passes_caption() -> None:
    client = _client()
    await messages.send_document(
        client, chat_id=42, link="https://x/y.pdf", caption="the doc"
    )
    call = client.send_document.await_args
    # chat_id and document are positional on the underlying client.
    assert call.args[0] == 42
    assert call.args[1] == "https://x/y.pdf"
    assert call.kwargs["caption"] == "the doc"


@pytest.mark.asyncio
async def test_send_audio_passes_title() -> None:
    client = _client()
    await messages.send_audio(client, chat_id=42, link="https://x/y.mp3", title="track")
    call = client.send_audio.await_args
    assert call.args[0] == 42
    assert call.args[1] == "https://x/y.mp3"
    assert call.kwargs["title"] == "track"


@pytest.mark.asyncio
async def test_send_typing_swallows_errors() -> None:
    client = MagicMock()
    client.send_chat_action = AsyncMock(side_effect=Exception("boom"))
    # Should NOT raise — typing is best-effort.
    await messages.send_typing(client, chat_id=42)
