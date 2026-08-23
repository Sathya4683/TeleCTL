"""``/image-resize`` — resize an inbound image attachment.

Runs synchronously in Lambda: Pillow resize of a typical photo is
under 2 seconds and images stay well below Lambda's payload limits.

Args: ``W`` or ``HxV`` or ``WxH`` (e.g. ``800x600``, ``1024``, ``x600``).
Default fit mode is ``contain`` (preserves aspect, fits inside box).
"""

from __future__ import annotations

from wactl.commands._helpers import media_bucket, output_key, require_telegram
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.converters import image_resize as img_resize
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

IMAGE_PNG = "image/png"
IMAGE_JPEG = "image/jpeg"
IMAGE_WEBP = "image/webp"
RESIZE_SUFFIX = ".png"


@register("/image-resize", sync=True, requires_media=True, description="Resize an attached image")
class ImageResizeCommand(Command):
    """Resize an image and send it back."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/image-resize requires an image attachment",
                user_message="Please attach an image when using /image-resize.",
            )

        width, height, fit = _parse_args(ctx.args)
        out_bytes = img_resize.resize(
            ctx.media_bytes,
            width=width,
            height=height,
            fit=fit,
        )
        mime = _mime_for(ctx.media_mime_type)
        bucket = media_bucket(ctx)
        key = output_key(ctx, RESIZE_SUFFIX)
        s3.put_object(bucket, key, out_bytes, content_type=mime)
        telegram = require_telegram(ctx)
        message_id = await messages.send_photo(
            telegram,
            chat_id=ctx.user.chat_id,
            link=s3.presigned_get_url(bucket, key),
            caption=f"Resized to {width or 'auto'}x{height or 'auto'}",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "bytes": len(out_bytes)},
        )


# ─── helpers ─────────────────────────────────────────────────────────────


def _parse_args(args: str) -> tuple[int | None, int | None, img_resize.FitMode]:
    """Parse ``WxH`` / ``W`` / ``xH`` into (width, height, fit)."""
    raw = args.strip()
    if not raw:
        raise UserInputError(
            "/image-resize needs a size, e.g. /image-resize 800x600",
            user_message="Please specify a target size like 800x600 or 1024.",
        )
    fit = img_resize.FitMode.CONTAIN
    size_str = raw
    for mode in img_resize.FitMode:
        suffix = f":{mode.value}"
        if raw.lower().endswith(suffix):
            size_str = raw[: -len(suffix)].strip()
            fit = mode
            break

    if "x" in size_str.lower():
        w_s, h_s = size_str.lower().split("x", 1)
        w = int(w_s) if w_s.strip() else None
        h = int(h_s) if h_s.strip() else None
    else:
        w = int(size_str)
        h = None
    if (w is not None and w <= 0) or (h is not None and h <= 0):
        raise UserInputError(
            f"Invalid size {raw!r}",
            user_message="Width and height must be positive.",
        )
    return w, h, fit


def _mime_for(input_mime: str | None) -> str:
    """Return the MIME type to advertise for the resized output."""
    if input_mime and input_mime.lower() in {IMAGE_PNG, IMAGE_JPEG, IMAGE_WEBP}:
        return input_mime
    return IMAGE_PNG


__all__ = ["ImageResizeCommand"]
