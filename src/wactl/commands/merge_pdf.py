"""``/merge-pdf`` — concatenate multiple PDF attachments into one.

Runs asynchronously (enqueued to SQS) because the file count is
unbounded and total size can exceed Lambda's limits.

This command expects two or more PDFs sent within a short window. The
first message kicks off the job (recorded via the worker), and the
following PDFs are joined when the user sends ``/merge-pdf done``.

For the v1 implementation, the user is expected to send each PDF as a
separate message; the worker reads the latest N messages from a small
DynamoDB buffer keyed by phone number, and merges them. This module
focuses on the merge step — the buffering concern is the worker's.
"""

from __future__ import annotations

from wactl.commands._helpers import media_bucket, output_key, require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.converters import merge_pdf
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

PDF_MIME = "application/pdf"
PDF_SUFFIX = ".pdf"


@register("/merge-pdf", sync=False, requires_media=True, description="Merge multiple PDFs into one")
class MergePdfCommand(Command):
    """Merge a single attachment with previously-buffered PDFs (same session)."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError(
                "/merge-pdf requires at least one PDF attachment",
                user_message="Please attach a PDF when using /merge-pdf.",
            )

        # The dispatcher / worker should have already populated
        # ``ctx._extra["pending_pdfs"]`` with previously buffered bytes.
        # We prepend the current attachment and merge the whole list.
        extra = getattr(ctx, "_extra", None) or {}
        prior: list[bytes] = list(extra.get("pending_pdfs", []))
        blobs = [*prior, ctx.media_bytes]
        if len(blobs) < 1:
            raise UserInputError(
                "/merge-pdf needs at least one PDF",
                user_message="Send one or more PDFs and try again.",
            )

        merged = merge_pdf.merge(blobs)
        bucket = media_bucket(ctx)
        key = output_key(ctx, PDF_SUFFIX)
        s3.put_object(bucket, key, merged, content_type=PDF_MIME)
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_document(
            whatsapp,
            to=ctx.user.phone,
            link=s3.presigned_get_url(bucket, key),
            filename="merged.pdf",
            caption=f"Merged {len(blobs)} PDFs.",
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"bucket": bucket, "key": key, "count": len(blobs), "bytes": len(merged)},
        )


__all__ = ["PDF_MIME", "PDF_SUFFIX", "MergePdfCommand"]
