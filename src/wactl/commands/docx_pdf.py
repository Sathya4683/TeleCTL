"""``/docx-pdf`` — convert an inbound DOCX attachment to a PDF file.

Runs synchronously in Lambda. ``python-docx`` parses the DOCX and
``reportlab`` renders a basic PDF (text + heading levels; tables,
images, fonts, complex layout are flattened). Fast (1-3 s for a
20-page DOCX). Output is uploaded to Telegram via multipart.

The fidelity caveat: this is **text + headings only** — for full
DOCX fidelity (formatting, tables, images) you'd need LibreOffice
headless or a paid API. For most documents this is enough to read
on the go.
"""

from __future__ import annotations

from wactl.commands._helpers import require_telegram
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.converters import docx_pdf
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

DOCX_SUFFIX = ".docx"
PDF_SUFFIX = ".pdf"


@register(
    "/docx-pdf",
    sync=True,
    requires_media=True,
    description="Convert attached DOCX to PDF (text + headings only)",
)
class DocxPdfCommand(Command):
    """Download → convert → upload via multipart → reply with the PDF."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/docx-pdf requires a DOCX attachment",
                user_message="Please attach a .docx file when using /docx-pdf.",
            )
        pdf_bytes = docx_pdf.docx_to_pdf(ctx.media_bytes)

        # Build a friendly filename for the user (preserve original DOCX name).
        filename = "output.pdf"
        if ctx.media_filename:
            base = ctx.media_filename.rsplit(".", 1)[0]
            if base:
                filename = f"{base}.pdf"

        telegram = require_telegram(ctx)
        message_id = await messages.upload_document(
            telegram,
            chat_id=ctx.user.chat_id,
            file_bytes=pdf_bytes,
            filename=filename,
            caption="Here's your PDF (text + headings).",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bytes": len(pdf_bytes)},
        )


__all__ = ["DOCX_SUFFIX", "PDF_SUFFIX", "DocxPdfCommand"]
