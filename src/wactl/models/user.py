"""User-context model shared by Lambda and worker."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UserContext(BaseModel):
    """Who is the message from, and where do we reply to?

    Constructed by the parser from the Telegram Update envelope. Carried into
    the command's :class:`CommandContext` so commands never need to re-parse.

    For Telegram, ``chat_id`` is the bot's reply target — an integer that
    uniquely identifies the chat (private chats use the user's id).
    """

    model_config = ConfigDict(frozen=True)

    chat_id: int
    username: str | None = None
    first_name: str | None = None
    message_id: int

    def __str__(self) -> str:  # pragma: no cover — cosmetic
        return f"User(chat_id={self.chat_id!r}, first_name={self.first_name!r})"


__all__ = ["UserContext"]
