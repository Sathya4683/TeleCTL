"""Domain-level outbound message helpers.

Each function takes a :class:`WhatsAppClient`, a recipient phone number,
and the message-specific payload. Returns the wamid of the outbound
message (so the caller can log it or surface it to the user).
"""

from __future__ import annotations

from typing import Any

from wactl.integrations.whatsapp.client import WhatsAppClient

#: Type alias for the outbound message id returned by Meta.
MessageId = str


async def send_text(
    client: WhatsAppClient,
    *,
    to: str,
    body: str,
    preview_url: bool = False,
    reply_to_message_id: str | None = None,
) -> MessageId:
    """Send a plain-text message."""
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"body": body, "preview_url": preview_url},
    }
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


async def send_document(
    client: WhatsAppClient,
    *,
    to: str,
    media_id: str | None = None,
    link: str | None = None,
    filename: str | None = None,
    caption: str | None = None,
    reply_to_message_id: str | None = None,
) -> MessageId:
    """Send a document by media_id (preferred) or by public link."""
    payload = _media_payload(
        to=to,
        media_id=media_id,
        link=link,
        reply_to_message_id=reply_to_message_id,
    )
    payload["type"] = "document"
    payload["document"] = _media_object(media_id, link, filename=filename, caption=caption)
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


async def send_image(
    client: WhatsAppClient,
    *,
    to: str,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
    reply_to_message_id: str | None = None,
) -> MessageId:
    """Send an image by media_id (preferred) or by public link."""
    payload = _media_payload(to=to, media_id=media_id, link=link, reply_to_message_id=reply_to_message_id)
    payload["type"] = "image"
    payload["image"] = _media_object(media_id, link, caption=caption)
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


async def send_audio(
    client: WhatsAppClient,
    *,
    to: str,
    media_id: str | None = None,
    link: str | None = None,
    reply_to_message_id: str | None = None,
) -> MessageId:
    """Send an audio clip (no caption support on audio type)."""
    payload = _media_payload(to=to, media_id=media_id, link=link, reply_to_message_id=reply_to_message_id)
    payload["type"] = "audio"
    payload["audio"] = _media_object(media_id, link)
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


async def send_video(
    client: WhatsAppClient,
    *,
    to: str,
    media_id: str | None = None,
    link: str | None = None,
    caption: str | None = None,
    reply_to_message_id: str | None = None,
) -> MessageId:
    """Send a video (caption supported)."""
    payload = _media_payload(to=to, media_id=media_id, link=link, reply_to_message_id=reply_to_message_id)
    payload["type"] = "video"
    payload["video"] = _media_object(media_id, link, caption=caption)
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


async def send_reaction(
    client: WhatsAppClient,
    *,
    to: str,
    message_id: str,
    emoji: str,
) -> MessageId:
    """React to a message with an emoji."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "reaction",
        "reaction": {"message_id": message_id, "emoji": emoji},
    }
    resp = await client.post_json(client.messages_url, payload)
    return _first_message_id(resp)


# ─── internal helpers ───────────────────────────────────────────────────


def _media_payload(
    *,
    to: str,
    media_id: str | None,
    link: str | None,
    reply_to_message_id: str | None,
) -> dict[str, Any]:
    if media_id is None and link is None:
        raise ValueError("send_document/image/audio/video requires media_id or link")
    payload: dict[str, Any] = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
    }
    if reply_to_message_id:
        payload["context"] = {"message_id": reply_to_message_id}
    return payload


def _media_object(
    media_id: str | None,
    link: str | None,
    *,
    filename: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    if media_id is not None:
        obj["id"] = media_id
    if link is not None:
        obj["link"] = link
    if filename is not None:
        obj["filename"] = filename
    if caption is not None:
        obj["caption"] = caption
    return obj


def _first_message_id(payload: dict[str, Any]) -> MessageId:
    """Extract the outbound message id from a Meta success envelope."""
    try:
        return str(payload["messages"][0]["id"])
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected Meta response shape: {payload}") from exc


__all__ = [
    "MessageId",
    "send_audio",
    "send_document",
    "send_image",
    "send_reaction",
    "send_text",
    "send_video",
]
