"""``/web-summary`` — fetch a URL and summarize it via Gemini.

Runs synchronously in Lambda: a single URL fetch plus a single Gemini
call is well under 10 seconds. The user's full URL is passed as the
command args (e.g. ``/web-summary https://example.com/article``).
"""

from __future__ import annotations

import structlog

from wactl.commands._helpers import require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.gemini import text as gemini_text
from wactl.integrations.web import fetcher as web_fetcher
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

logger = structlog.get_logger(__name__)


@register("/web-summary", sync=True, description="Summarize a public web page")
class WebSummaryCommand(Command):
    """Fetch a URL, summarize with Gemini, reply with bullet points."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        url = ctx.args.strip()
        if not url:
            raise UserInputError(
                "/web-summary needs a URL",
                user_message="Please send a URL with /web-summary.",
            )
        if ctx.http is None or ctx.gemini is None:
            raise UserInputError(
                "Service is not configured for /web-summary",
                user_message="Service is misconfigured. Please try again later.",
            )

        page = await web_fetcher.fetch_and_extract(ctx.http, url)
        if not page.markdown.strip():
            raise UserInputError(
                f"No readable content at {url}",
                user_message="We couldn't read anything useful on that page.",
            )
        # Trim very long pages to keep prompt + token usage bounded.
        body = page.markdown if len(page.markdown) <= 30_000 else page.markdown[:30_000]
        summary = await gemini_text.summarize(ctx.gemini, body)

        text = f"_{page.title}_\n\n{summary}" if page.title else summary
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_text(
            whatsapp,
            to=ctx.user.phone,
            body=text,
            reply_to_message_id=ctx.user.message_id,
        )
        logger.info(
            "web_summary.sent",
            url=page.url,
            bytes=page.bytes_downloaded,
            title=page.title,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"url": page.url, "bytes": page.bytes_downloaded},
        )


__all__ = ["WebSummaryCommand"]
