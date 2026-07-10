"""``/pdf-docx`` — convert an inbound PDF attachment to a DOCX file.

Runs asynchronously (enqueued to SQS) because ``pdf2docx`` can take
5-30 seconds on multi-page documents. The worker downloads the PDF
from Meta, converts it, uploads the DOCX to S3, and sends the
resulting document back to the user via WhatsApp.
"""

from __future__ import annotations

from wactl.commands._helpers import (
    media_bucket,
    output_key,
    require_whatsapp,
    suggest_filename,
)
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.converters import pdf_docx
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_SUFFIX = ".docx"


@register("/pdf-docx", sync=False, requires_media=True, description="Convert PDF to DOCX")
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
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_document(
            whatsapp,
            to=ctx.user.phone,
            link=s3.presigned_get_url(bucket, key),
            filename=suggest_filename(ctx, DOCX_SUFFIX, default="output.docx"),
            caption="Here's your DOCX.",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "bytes": len(docx_bytes)},
        )


__all__ = ["DOCX_MIME", "DOCX_SUFFIX", "PdfDocxCommand"]
