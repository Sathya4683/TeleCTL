"""Pydantic models for Meta's WhatsApp Cloud API webhook envelopes.

These mirror the official structure documented at:
https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples

The shape is deep and contains many optional blocks depending on whether
the inbound event is a user message, a status update, or an error. We
discriminate on ``entry[].changes[].value`` content. Models are
``frozen=True`` so they can be hashed and used as dict keys.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Common config: immutable, ignore unknowns, validate on assignment."""

    model_config = ConfigDict(frozen=True, extra="ignore", validate_assignment=False)


# ─── Meta-side metadata ────────────────────────────────────────────────


class Metadata(_Base):
    """Phone-number-level metadata, present in every webhook value."""

    display_phone_number: str
    phone_number_id: str


class ContactProfile(_Base):
    name: str


class Contact(_Base):
    profile: ContactProfile
    wa_id: str  # user's WhatsApp ID (= phone number, prefix "+" omitted)


class TextContent(_Base):
    body: str


class ImageContent(_Base):
    mime_type: str
    sha256: str
    id: str  # media_id
    caption: str | None = None


class DocumentContent(_Base):
    mime_type: str
    sha256: str
    id: str  # media_id
    caption: str | None = None
    filename: str | None = None


class AudioContent(_Base):
    mime_type: str
    sha256: str
    id: str  # media_id
    voice: bool | None = None  # True → voice note


class VideoContent(_Base):
    mime_type: str
    sha256: str
    id: str  # media_id
    caption: str | None = None
    filename: str | None = None


class StickerContent(_Base):
    mime_type: str
    sha256: str
    id: str  # media_id
    animated: bool | None = None


# Union — discriminated by ``type``
Message = Annotated[
    Any,
    Field(discriminator="type"),
]


class TextMessage(_Base):
    """Plain text message — used for commands."""

    type: Literal["text"]
    id: str  # wamid...
    from_: str = Field(alias="from")
    timestamp: str
    text: TextContent
    context: dict[str, Any] | None = None  # reply-to metadata

    @property
    def body(self) -> str:
        return self.text.body


class MediaMessage(_Base):
    """Image, document, audio, video, or sticker message."""

    type: Literal["image", "document", "audio", "video", "sticker"]
    id: str
    from_: str = Field(alias="from")
    timestamp: str
    image: ImageContent | None = None
    document: DocumentContent | None = None
    audio: AudioContent | None = None
    video: VideoContent | None = None
    sticker: StickerContent | None = None
    context: dict[str, Any] | None = None

    @property
    def media_id(self) -> str | None:
        obj = getattr(self, self.type, None)
        return obj.id if obj is not None else None

    @property
    def media_mime(self) -> str | None:
        obj = getattr(self, self.type, None)
        return obj.mime_type if obj is not None else None

    @property
    def media_filename(self) -> str | None:
        obj = getattr(self, self.type, None)
        if isinstance(obj, DocumentContent | VideoContent):
            return obj.filename
        return None

    @property
    def media_caption(self) -> str | None:
        obj = getattr(self, self.type, None)
        if isinstance(obj, ImageContent | DocumentContent | VideoContent):
            return obj.caption
        return None


# ─── Envelope ──────────────────────────────────────────────────────────


class Value(_Base):
    """``entry[].changes[].value`` block."""

    messaging_product: Literal["whatsapp"]
    metadata: Metadata
    contacts: list[Contact] | None = None
    messages: list[TextMessage | MediaMessage] | None = None
    statuses: list[dict[str, Any]] | None = None
    errors: list[dict[str, Any]] | None = None


class Change(_Base):
    field: Literal["messages"]
    value: Value


class Entry(_Base):
    id: str  # WABA id
    changes: list[Change]


class WhatsAppEnvelope(_Base):
    """The full incoming POST body from Meta."""

    object: Literal["whatsapp_business_account"]
    entry: list[Entry]

    # ── Convenience flatteners ─────────────────────────────────────

    def all_messages(self) -> list[TextMessage | MediaMessage]:
        msgs: list[TextMessage | MediaMessage] = []
        for entry in self.entry:
            for change in entry.changes:
                if change.value.messages:
                    msgs.extend(change.value.messages)
        return msgs

    def primary_metadata(self) -> Metadata:
        # All values within the same POST share metadata; use the first.
        return self.entry[0].changes[0].value.metadata

    def primary_contact(self) -> Contact | None:
        for entry in self.entry:
            for change in entry.changes:
                if change.value.contacts:
                    return change.value.contacts[0]
        return None


__all__ = [
    "AudioContent",
    "Change",
    "Contact",
    "ContactProfile",
    "DocumentContent",
    "Entry",
    "ImageContent",
    "MediaMessage",
    "Metadata",
    "StickerContent",
    "TextContent",
    "TextMessage",
    "Value",
    "VideoContent",
    "WhatsAppEnvelope",
]
