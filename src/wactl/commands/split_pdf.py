"""``/split-pdf`` — split an inbound PDF by page range.

Runs asynchronously (enqueued to SQS) because page-splitting on large
PDFs can exceed comfortable inline window.

Args: a range spec like ``1-3,5,7-9``. Default splits into single-page
PDFs. If multiple chunks result, the first chunk is sent back; a
follow-up ``/split-pdf continue`` would emit the next batch — for v1
we send only the first chunk and surface the chunk count.
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
from wactl.integrations.converters import pdf_text, split_pdf
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

PDF_MIME = "application/pdf"
PDF_SUFFIX = ".pdf"


@register("/split-pdf", sync=False, requires_media=True, description="Split PDF by page ranges")
class SplitPdfCommand(Command):
    """Split ``ctx.media_bytes`` according to ``ctx.args``."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/split-pdf requires a PDF attachment",
                user_message="Please attach a PDF when using /split-pdf.",
            )

        total_pages = pdf_text.page_count(ctx.media_bytes)
        if ctx.args.strip():
            ranges = split_pdf.parse_ranges(ctx.args, total_pages)
            chunks = split_pdf.split(ctx.media_bytes, ranges=ranges)
        else:
            chunks = split_pdf.split(ctx.media_bytes, pages_per_chunk=1)

        if not chunks:
            raise UserInputError(
                "/split-pdf produced no chunks",
                user_message="No pages matched. Check your range spec.",
            )

        # v1: send the first chunk only; user can re-invoke for more.
        first = chunks[0]
        bucket = media_bucket(ctx)
        key = output_key(ctx, PDF_SUFFIX)
        s3.put_object(bucket, key, first, content_type=PDF_MIME)
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_document(
            whatsapp,
            to=ctx.user.phone,
            link=s3.presigned_get_url(bucket, key),
            filename=suggest_filename(ctx, PDF_SUFFIX, default="split.pdf"),
            caption=f"Part 1 of {len(chunks)}.",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={
                "bucket": bucket,
                "key": key,
                "chunk": 1,
                "total_chunks": len(chunks),
                "total_pages": total_pages,
                "bytes": len(first),
            },
        )


__all__ = ["PDF_MIME", "PDF_SUFFIX", "SplitPdfCommand"]
