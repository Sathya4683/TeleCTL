"""User-context model shared by Lambda and worker."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class UserContext(BaseModel):
    """Who is the message from, and where do we reply to?

    Constructed by the parser from the webhook envelope. Carried into the
    command's :class:`CommandContext` so commands never need to re-parse.
    """

    model_config = ConfigDict(frozen=True)

    phone: str  # E.164 without "+", e.g. "16505551234"
    name: str | None  # WhatsApp profile name, may be empty
    message_id: str  # wamid...; used for dedup + reply context
    waba_id: str  # the WhatsApp Business Account id
    phone_number_id: str  # which of our phone numbers received it

    def __str__(self) -> str:  # pragma: no cover — cosmetic
        return f"User(phone={self.phone!r}, name={self.name!r})"


__all__ = ["UserContext"]
