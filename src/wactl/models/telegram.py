"""Pydantic models for the Telegram Bot API.

Mirrors the subset of https://core.telegram.org/bots/api that the bot uses.
Models are ``frozen=True`` so they can be hashed and used as dict keys.

Discriminator field is omitted — the parser picks fields explicitly rather
than via Pydantic unions, because the envelope has many optional fields
and the discriminator form becomes brittle as fields are added.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    """Common config: immutable, ignore unknowns."""

    model_config = ConfigDict(frozen=True, extra="ignore")


# ─── Telegram user / chat ──────────────────────────────────────────────


class TelegramUser(_Base):
    """``from`` or ``chat`` user. Either may appear on a Message."""

    id: int
    is_bot: bool = False
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    language_code: str | None = None


class TelegramChat(_Base):
    """Where the message lives. Private chats use the user's id as chat id."""

    id: int
    type: str  # "private" | "group" | "supergroup" | "channel"
    title: str | None = None
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None


# ─── Media payloads ────────────────────────────────────────────────────


class PhotoSize(_Base):
    """One entry in ``message.photo``. Pick the last for full resolution."""

    file_id: str
    file_unique_id: str
    width: int
    height: int
    file_size: int | None = None


class Document(_Base):
    file_id: str
    file_unique_id: str
    thumbnail: PhotoSize | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Voice(_Base):
    file_id: str
    file_unique_id: str
    duration: int
    mime_type: str | None = None
    file_size: int | None = None


class Audio(_Base):
    file_id: str
    file_unique_id: str
    duration: int
    performer: str | None = None
    title: str | None = None
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


class Video(_Base):
    file_id: str
    file_unique_id: str
    width: int
    height: int
    duration: int
    file_name: str | None = None
    mime_type: str | None = None
    file_size: int | None = None


# ─── Envelope ──────────────────────────────────────────────────────────


class Message(_Base):
    """A single incoming message from Telegram."""

    message_id: int
    from_: TelegramUser | None = Field(default=None, alias="from")
    chat: TelegramChat
    date: int  # unix epoch seconds
    text: str | None = None
    caption: str | None = None

    photo: list[PhotoSize] | None = None
    document: Document | None = None
    voice: Voice | None = None
    audio: Audio | None = None
    video: Video | None = None


class Update(_Base):
    """Top-level webhook payload. wactl only handles ``message`` today."""

    update_id: int
    message: Message | None = None
    edited_message: Message | None = None


# ─── Outbound API response shapes ──────────────────────────────────────


class ResponseResult(_Base):
    """Generic wrapper for `result` field. Only the fields we read."""

    message_id: int | None = None
    file_path: str | None = None
    file_id: str | None = None
    file_size: int | None = None


class TelegramResponse(_Base):
    """Every Bot API call returns ``{"ok": bool, "result": ...}``."""

    ok: bool
    result: Any | None = None
    description: str | None = None
    error_code: int | None = None


__all__ = [
    "Audio",
    "Document",
    "Message",
    "PhotoSize",
    "ResponseResult",
    "TelegramChat",
    "TelegramResponse",
    "TelegramUser",
    "Update",
    "Video",
    "Voice",
]
