"""``/pdf-audio`` — convert an inbound PDF into an audio file.

Runs asynchronously (enqueued to SQS) because TTS fan-out across chunks
takes 30-120 seconds. The pipeline lives in :mod:`wactl.services.audiobook`.

Audio file is uploaded to S3 and sent back as a WhatsApp audio message.
"""

from __future__ import annotations

from wactl.commands._helpers import media_bucket, output_key, require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.aws import secrets as aws_secrets
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse
from wactl.services import audiobook

AUDIO_MIME = "audio/mpeg"
AUDIO_SUFFIX = ".mp3"


@register("/pdf-audio", sync=False, requires_media=True, description="Convert PDF to audio (TTS)")
class PdfAudioCommand(Command):
    """Convert a PDF to an audiobook via Gemini TTS."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/pdf-audio requires a PDF attachment",
                user_message="Please attach a PDF when using /pdf-audio.",
            )

        api_key = aws_secrets.get_secret("wactl/gemini/api-key")
        audio_bytes = await audiobook.synthesize(
            ctx.media_bytes,
            api_key=api_key,
        )

        bucket = media_bucket(ctx)
        key = output_key(ctx, AUDIO_SUFFIX)
        s3.put_object(bucket, key, audio_bytes, content_type=AUDIO_MIME)
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_audio(
            whatsapp,
            to=ctx.user.phone,
            link=s3.presigned_get_url(bucket, key),
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "bytes": len(audio_bytes)},
        )


__all__ = ["AUDIO_MIME", "AUDIO_SUFFIX", "PdfAudioCommand"]
