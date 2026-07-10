"""Tests for :mod:`wactl.integrations.whatsapp.messages`."""

from __future__ import annotations

from typing import Any

import pytest

from wactl.integrations.whatsapp.messages import (
    send_audio,
    send_document,
    send_image,
    send_reaction,
    send_text,
    send_video,
)


class _FakeClient:
    """Captures posted payloads and returns a canned response."""

    def __init__(self, message_id: str = "wamid-out") -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.message_id = message_id
        self.messages_url = "https://example.com/messages"

    async def post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((url, body))
        return {"messages": [{"id": self.message_id}]}


@pytest.mark.asyncio
async def test_send_text_basic() -> None:
    client = _FakeClient()
    mid = await send_text(client, to="1555", body="hi")
    assert mid == "wamid-out"
    _, payload = client.calls[0]
    assert payload["to"] == "1555"
    assert payload["type"] == "text"
    assert payload["text"]["body"] == "hi"


@pytest.mark.asyncio
async def test_send_text_with_reply_context() -> None:
    client = _FakeClient()
    await send_text(client, to="1555", body="r", reply_to_message_id="orig")
    _, payload = client.calls[0]
    assert payload["context"] == {"message_id": "orig"}


@pytest.mark.asyncio
async def test_send_text_with_preview_url() -> None:
    client = _FakeClient()
    await send_text(client, to="1555", body="see https://x", preview_url=True)
    _, payload = client.calls[0]
    assert payload["text"]["preview_url"] is True


@pytest.mark.asyncio
async def test_send_document_with_media_id() -> None:
    client = _FakeClient()
    mid = await send_document(client, to="1", media_id="med-1", filename="a.pdf", caption="c")
    assert mid == "wamid-out"
    _, payload = client.calls[0]
    assert payload["type"] == "document"
    assert payload["document"]["id"] == "med-1"
    assert payload["document"]["filename"] == "a.pdf"
    assert payload["document"]["caption"] == "c"


@pytest.mark.asyncio
async def test_send_document_with_link() -> None:
    client = _FakeClient()
    await send_document(client, to="1", link="https://files/a.pdf")
    _, payload = client.calls[0]
    assert payload["document"]["link"] == "https://files/a.pdf"


@pytest.mark.asyncio
async def test_send_document_requires_id_or_link() -> None:
    client = _FakeClient()
    with pytest.raises(ValueError):
        await send_document(client, to="1")


@pytest.mark.asyncio
async def test_send_image_with_caption() -> None:
    client = _FakeClient()
    await send_image(client, to="1", media_id="img-1", caption="pretty")
    _, payload = client.calls[0]
    assert payload["type"] == "image"
    assert payload["image"]["id"] == "img-1"
    assert payload["image"]["caption"] == "pretty"


@pytest.mark.asyncio
async def test_send_audio_no_caption() -> None:
    client = _FakeClient()
    await send_audio(client, to="1", media_id="aud-1")
    _, payload = client.calls[0]
    assert payload["type"] == "audio"
    assert payload["audio"]["id"] == "aud-1"


@pytest.mark.asyncio
async def test_send_video_with_caption() -> None:
    client = _FakeClient()
    await send_video(client, to="1", media_id="vid-1", caption="funny")
    _, payload = client.calls[0]
    assert payload["type"] == "video"
    assert payload["video"]["caption"] == "funny"


@pytest.mark.asyncio
async def test_send_reaction() -> None:
    client = _FakeClient()
    await send_reaction(client, to="1", message_id="orig", emoji="🔥")
    _, payload = client.calls[0]
    assert payload["type"] == "reaction"
    assert payload["reaction"] == {"message_id": "orig", "emoji": "🔥"}


@pytest.mark.asyncio
async def test_unexpected_response_shape_raises() -> None:
    """If Meta returns a malformed body, we raise ValueError."""

    class _BadClient(_FakeClient):
        async def post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
            self.calls.append((url, body))
            return {"messages": []}  # empty list — should fail

    client = _BadClient()
    with pytest.raises(ValueError):
        await send_text(client, to="1", body="hi")
