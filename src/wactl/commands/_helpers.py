"""Internal helpers shared by all commands.

These are not exposed in the public API. Each helper is small and
deliberately stays out of the ``wactl.commands.base`` so that the
public surface remains minimal.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wactl.commands.base import CommandContext
from wactl.config import settings
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3

if TYPE_CHECKING:
    from wactl.integrations.whatsapp.client import WhatsAppClient


def media_bucket(ctx: CommandContext) -> str:
    """Resolve the media bucket name from the context / config."""
    extra = getattr(ctx, "_extra", None) or {}
    bucket = extra.get("s3_bucket")
    if bucket:
        return str(bucket)
    return settings.s3_media_bucket or "wactl-media-dev"


def output_key(ctx: CommandContext, suffix: str) -> str:
    """Build a deterministic S3 key for an outbound artifact."""
    safe_user = ctx.user.phone[-10:]  # last 10 digits, no PII leak
    return s3.make_key("out", safe_user, f"{ctx.user.message_id}{suffix}")


def suggest_filename(ctx: CommandContext, suffix: str, *, default: str | None = None) -> str:
    """Build a friendly filename for the outbound media.

    Honors ``ctx.media_filename`` when present, but ensures the right
    extension is in place. ``default`` overrides the inferred base.
    """
    name = ctx.media_filename or default or f"output{suffix}"
    if not name.lower().endswith(suffix.lower()):
        base = name.rsplit(".", 1)[0] if "." in name else name
        name = f"{base}{suffix}"
    return name


def require_whatsapp(ctx: CommandContext) -> WhatsAppClient:
    """Return the WhatsApp client or raise a user-facing :class:`UserInputError`.

    The dispatcher populates ``ctx.whatsapp`` for every command that
    sends a reply. If it's missing the deployment is misconfigured
    and we surface a friendly message rather than letting ``send_*``
    raise a confusing TypeError.
    """
    if ctx.whatsapp is None:
        raise UserInputError(
            "WhatsApp client missing from context",
            user_message="Service is misconfigured. Please try again later.",
        )
    return ctx.whatsapp


__all__ = ["media_bucket", "output_key", "require_whatsapp", "suggest_filename"]
