"""Core command-layer models: metadata, request, response."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CommandMeta(BaseModel):
    """Static per-command metadata attached at registration time."""

    model_config = ConfigDict(frozen=True)

    name: str  # e.g. "/pdf-docx"
    sync: bool  # True → run inline in Lambda; False → enqueue to SQS
    requires_media: bool = False  # needs an inbound attachment
    description: str = ""  # human-readable, for /help


class CommandRequest(BaseModel):
    """Static-per-invocation data passed to a command's ``run()``."""

    model_config = ConfigDict(frozen=True)

    args: str = ""  # everything after the command
    raw_body: str = ""  # the original text body (for context echoes)


class CommandResponse(BaseModel):
    """What a command returns — kept terse on purpose.

    Most commands do not return a value; they call WhatsApp directly to
    send the result. The response is for logging and for the test harness
    to assert against.
    """

    model_config = ConfigDict(frozen=True)

    success: bool = True
    message_id: str | None = None  # the outbound WhatsApp message id
    notes: dict[str, Any] = Field(default_factory=dict)


__all__ = ["CommandMeta", "CommandRequest", "CommandResponse"]
