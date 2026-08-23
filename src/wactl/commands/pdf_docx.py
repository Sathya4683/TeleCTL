"""``/pdf-docx`` — convert an inbound PDF attachment to a DOCX file.

Runs **synchronously** in Lambda: ``pdf2docx`` typically takes 5-30
seconds on multi-page documents, which fits comfortably inside the
15-minute Lambda timeout. The DOCX is uploaded to S3 and a presigned
URL is sent back via Telegram (the response body itself is never the
DOCX, so the 6 MB API Gateway payload limit is irrelevant).

The DOCX is delivered via ``sendDocument`` with the presigned URL — a
``file_id`` is returned by Telegram and the user can forward it.
"""

from __future__ import annotations

from wactl.commands._helpers import (
    media_bucket,
    output_key,
    require_telegram,
)
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.converters import pdf_docx
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_SUFFIX = ".docx"


@register("/pdf-docx", sync=True, requires_media=True, description="Convert attached PDF to DOCX")
class PdfDocxCommand(Command):
    """Download → convert → upload → reply with the DOCX."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/pdf-docx requires a PDF attachment",
                user_message="Please attach a PDF when using /pdf-docx.",
            )
        docx_bytes = pdf_docx.pdf_to_docx(ctx.media_bytes)
        bucket = media_bucket(ctx)
        key = output_key(ctx, DOCX_SUFFIX)
        s3.put_object(bucket, key, docx_bytes, content_type=DOCX_MIME)
        telegram = require_telegram(ctx)
        message_id = await messages.send_document(
            telegram,
            chat_id=ctx.user.chat_id,
            link=s3.presigned_get_url(bucket, key),
            caption="Here's your DOCX.",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "bytes": len(docx_bytes)},
        )


__all__ = ["DOCX_MIME", "DOCX_SUFFIX", "PdfDocxCommand"]
