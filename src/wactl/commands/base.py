"""Base classes for commands.

A command is a single async function that:
- Receives a :class:`CommandContext` (user, integrations, media)
- Returns a :class:`CommandResponse`
- Is registered via :func:`wactl.commands.registry.register`

Commands MUST NOT touch httpx, boto3, or the Telegram Bot API directly.
They orchestrate integrations; that's the entire point of the plugin split.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from wactl.models.command import CommandMeta, CommandResponse
from wactl.models.user import UserContext

if TYPE_CHECKING:
    from wactl.integrations.telegram.client import TelegramClient

logger = structlog.get_logger(__name__)


class CommandContext:
    """Everything a command needs to do its work.

    Passed by-value through the worker and Lambda. All integration handles
    are injected so commands stay testable without real AWS / Telegram.
    """

    __slots__ = (
        "_extra",
        "args",
        "gemini",
        "http",
        "logger",
        "media_bytes",
        "media_filename",
        "media_id",
        "media_mime_type",
        "raw_body",
        "s3",
        "secrets",
        "sqs",
        "telegram",
        "user",
    )

    def __init__(
        self,
        *,
        user: UserContext,
        args: str = "",
        raw_body: str = "",
        media_id: str | None = None,
        media_bytes: bytes | None = None,
        media_mime_type: str | None = None,
        media_filename: str | None = None,
        telegram: TelegramClient | None = None,
        secrets: Any | None = None,
        s3: Any | None = None,
        sqs: Any | None = None,
        http: httpx.AsyncClient | None = None,
        gemini: Any | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
        **extra: Any,
    ) -> None:
        self.user = user
        self.args = args
        self.raw_body = raw_body
        self.media_id = media_id
        self.media_bytes = media_bytes
        self.media_mime_type = media_mime_type
        self.media_filename = media_filename
        self.telegram = telegram
        self.secrets = secrets
        self.s3 = s3
        self.sqs = sqs
        self.http = http
        self.gemini = gemini
        self.logger = logger or structlog.get_logger("wactl.command")
        self._extra = extra


class Command(ABC):
    """Abstract base — subclasses declare ``name`` and ``meta``."""

    #: Slash-prefixed name, e.g. "/pdf-docx". Must be unique.
    name: str
    #: Static metadata; set in subclass.
    meta: CommandMeta

    @abstractmethod
    async def run(self, ctx: CommandContext) -> CommandResponse:
        """Execute the command. Subclasses override."""


__all__ = ["Command", "CommandContext"]
