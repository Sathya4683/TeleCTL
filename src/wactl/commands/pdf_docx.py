"""``/pdf-docx`` — convert an inbound PDF attachment to a DOCX file.

Runs **synchronously** in Lambda: ``pdf2docx`` typically takes 5-30
seconds on multi-page documents, which fits comfortably inside the
15-minute Lambda timeout.

The DOCX is delivered via **multipart upload** (``sendDocument`` with
the bytes in the request body) instead of an HTTP URL. That avoids
Telegram's CDN URL-fetch path, which performs a HEAD pre-check that
fails on boto3's GET-signed presigned URLs (HEAD returns 403; the
resulting bot error was ``Bad Request: failed to get HTTP URL content``).
Multipart upload is the recommended path for any file > 5 MB.
"""

from __future__ import annotations

from wactl.commands._helpers import require_telegram
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.converters import pdf_docx
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
DOCX_SUFFIX = ".docx"


@register("/pdf-docx", sync=True, requires_media=True, description="Convert attached PDF to DOCX")
class PdfDocxCommand(Command):
    """Download → convert → upload via multipart → reply with the DOCX."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/pdf-docx requires a PDF attachment",
                user_message="Please attach a PDF when using /pdf-docx.",
            )
        docx_bytes = pdf_docx.pdf_to_docx(ctx.media_bytes)
        # Build a friendly filename for the user (preserve original PDF name if known).
        filename = "output.docx"
        if ctx.media_filename:
            base = ctx.media_filename.rsplit(".", 1)[0]
            if base:
                filename = f"{base}.docx"
        telegram = require_telegram(ctx)
        message_id = await messages.upload_document(
            telegram,
            chat_id=ctx.user.chat_id,
            file_bytes=docx_bytes,
            filename=filename,
            caption="Here's your DOCX.",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bytes": len(docx_bytes)},
        )


__all__ = ["DOCX_MIME", "DOCX_SUFFIX", "PdfDocxCommand"]
