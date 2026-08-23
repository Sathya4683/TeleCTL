"""``/pdf-audio`` — convert an inbound PDF into an audio file.

Runs **asynchronously** (enqueued to SQS FIFO) because TTS fan-out
across chunks takes 30-120 seconds, AND the conversion requires
``ffmpeg`` (a system binary not available in Lambda without a custom
layer). The worker process handles this command; the pipeline lives in
:mod:`wactl.services.audiobook`.

Audio file is uploaded to S3 and sent back as a Telegram audio message.
"""

from __future__ import annotations

from wactl.commands._helpers import media_bucket, output_key, require_telegram
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse
from wactl.services import audiobook

AUDIO_MIME = "audio/mpeg"
AUDIO_SUFFIX = ".mp3"


@register("/pdf-audio", sync=False, requires_media=True, description="Convert attached PDF to audio (TTS)")
class PdfAudioCommand(Command):
    """Convert a PDF to an audiobook via Gemini TTS."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/pdf-audio requires a PDF attachment",
                user_message="Please attach a PDF when using /pdf-audio.",
            )

        # The Gemini API key is read from environment at process start
        # (see ``wactl.config.settings.gemini_api_key``). For local dev,
        # set GEMINI_API_KEY in .env. In production on EC2, it's written
        # to /etc/wactl/worker.env by cloud-init.
        from wactl.config import settings  # noqa: PLC0415 — local import to avoid cycle

        api_key = settings.gemini_api_key
        if not api_key:
            raise UserInputError(
                "GEMINI_API_KEY is not set",
                user_message="Audio service is not configured. Please contact the bot admin.",
            )
        audio_bytes = await audiobook.synthesize(
            ctx.media_bytes,
            api_key=api_key,
        )

        bucket = media_bucket(ctx)
        key = output_key(ctx, AUDIO_SUFFIX)
        s3.put_object(bucket, key, audio_bytes, content_type=AUDIO_MIME)
        telegram = require_telegram(ctx)
        message_id = await messages.send_audio(
            telegram,
            chat_id=ctx.user.chat_id,
            link=s3.presigned_get_url(bucket, key),
            title="Audiobook",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "bytes": len(audio_bytes)},
        )


__all__ = ["AUDIO_MIME", "AUDIO_SUFFIX", "PdfAudioCommand"]
