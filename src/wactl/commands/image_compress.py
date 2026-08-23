"""``/image-compress`` — recompress an inbound image to a smaller JPEG/PNG.

Runs synchronously in Lambda: Pillow recompress is fast and the output
stays well below Lambda's payload limit.

Args: optional quality 1..95 (default 75). Optional ``max-width`` and
``target-bytes`` flags, e.g. ``/image-compress q=70 max=1600``.
"""

from __future__ import annotations

from wactl.commands._helpers import media_bucket, output_key, require_telegram
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.converters import image_compress as img_compress
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

IMAGE_JPEG = "image/jpeg"
COMPRESS_SUFFIX = ".jpg"


@register("/image-compress", sync=True, requires_media=True, description="Compress an attached image")
class ImageCompressCommand(Command):
    """Recompress an image and send it back."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/image-compress requires an image attachment",
                user_message="Please attach an image when using /image-compress.",
            )

        quality, max_width, target_bytes = _parse_args(ctx.args)

        if max_width is not None:
            out_bytes = img_compress.resize_and_compress(
                ctx.media_bytes,
                max_width=max_width,
                quality=quality,
                target_bytes=target_bytes,
            )
        else:
            out_bytes = img_compress.recompress(
                ctx.media_bytes,
                quality=quality,
                format="JPEG",
            )

        bucket = media_bucket(ctx)
        key = output_key(ctx, COMPRESS_SUFFIX)
        s3.put_object(bucket, key, out_bytes, content_type=IMAGE_JPEG)
        telegram = require_telegram(ctx)
        message_id = await messages.send_photo(
            telegram,
            chat_id=ctx.user.chat_id,
            link=s3.presigned_get_url(bucket, key),
            caption=f"Compressed (q={quality})",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={
                "bucket": bucket,
                "key": key,
                "bytes": len(out_bytes),
                "quality": quality,
            },
        )


# ─── helpers ─────────────────────────────────────────────────────────────


def _parse_args(args: str) -> tuple[int, int | None, int | None]:
    """Parse ``q=70 max=1600 target=200000`` into typed values."""
    quality = 75
    max_width: int | None = None
    target_bytes: int | None = None
    for tok in args.split():
        if "=" not in tok:
            raise UserInputError(
                f"Unknown token {tok!r}",
                user_message="Expected key=value pairs like q=70 max=1600.",
            )
        key, _, value = tok.partition("=")
        key = key.strip().lower()
        value = value.strip()
        try:
            n = int(value)
        except ValueError as exc:
            raise UserInputError(
                f"{key!r} must be an integer",
                user_message=f"{key} must be a number, got {value!r}.",
            ) from exc
        if key in {"q", "quality"}:
            quality = n
        elif key in {"max", "max-width"}:
            max_width = n
        elif key in {"target", "target-bytes", "bytes"}:
            target_bytes = n
        else:
            raise UserInputError(
                f"Unknown option {key!r}",
                user_message=f"Unknown option {key!r}. Supported: q, max, target.",
            )
    return quality, max_width, target_bytes


__all__ = ["ImageCompressCommand"]
