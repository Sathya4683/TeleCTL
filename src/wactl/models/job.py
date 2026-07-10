"""SQS job envelope — async command work."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from wactl.models.command import CommandMeta
from wactl.models.user import UserContext


class Job(BaseModel):
    """A unit of work pushed to SQS for the EC2 worker.

    The worker deserializes this from the SQS body, re-hydrates the command
    via the registry, and dispatches. Fields are deliberately small so the
    serialized body fits well under SQS's 256 KB limit.
    """

    model_config = ConfigDict(frozen=True)

    job_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    command: str  # e.g. "/pdf-docx"
    args: str  # remainder after the command, may be empty
    user: UserContext
    media_id: str | None = None  # inbound wamid media id, if any
    media_mime: str | None = None
    media_filename: str | None = None
    enqueued_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    meta: CommandMeta | None = None  # filled by dispatcher for routing info


__all__ = ["Job"]
