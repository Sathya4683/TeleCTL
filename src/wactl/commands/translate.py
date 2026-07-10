"""``/translate`` — translate text or an attached document via Gemini.

Runs synchronously in Lambda: a single Gemini call is well under 5s.

Args: ``<lang> [text...]`` — first token is the target language code
(e.g. ``es``, ``fr``, ``de``). If no text follows and the inbound
message has no attachment, raise :class:`UserInputError`. If a document
attachment is present, extract text first.
"""

from __future__ import annotations

from wactl.commands._helpers import require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.converters import pdf_text
from wactl.integrations.gemini import text as gemini_text
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

PDF_MIME = "application/pdf"


@register("/translate", sync=True, description="Translate text to a target language")
class TranslateCommand(Command):
    """Translate a user-supplied string (or attached document) via Gemini."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        target_lang, text = _split_lang_and_text(ctx)
        if not text and ctx.media_bytes is None:
            raise UserInputError(
                "/translate needs text or an attachment",
                user_message="Send text after the language code, e.g. /translate es hello.",
            )
        if ctx.gemini is None:
            raise UserInputError(
                "Service is not configured for /translate",
                user_message="Service is misconfigured. Please try again later.",
            )

        if not text and ctx.media_bytes is not None:
            text = _extract_attachment_text(ctx)

        translated = await gemini_text.translate(
            ctx.gemini,
            text,
            target_language=target_lang,
        )
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_text(
            whatsapp,
            to=ctx.user.phone,
            body=translated,
            reply_to_message_id=ctx.user.message_id,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"target_language": target_lang, "input_chars": len(text)},
        )


# ─── helpers ─────────────────────────────────────────────────────────────


def _split_lang_and_text(ctx: CommandContext) -> tuple[str, str]:
    """First non-empty token is the language; the rest is the text."""
    raw = ctx.args.strip()
    if not raw:
        raise UserInputError(
            "/translate needs a language code, e.g. /translate es hola",
            user_message="Please specify a language, e.g. /translate es hello.",
        )
    parts = raw.split(maxsplit=1)
    lang = parts[0]
    text = parts[1].strip() if len(parts) > 1 else ""
    return lang, text


def _extract_attachment_text(ctx: CommandContext) -> str:
    """Read text from an attached PDF. Only PDFs supported in v1."""
    if ctx.media_mime_type != PDF_MIME:
        raise UserInputError(
            f"Unsupported attachment type {ctx.media_mime_type!r}",
            user_message="Translate currently supports PDF attachments only.",
        )
    assert ctx.media_bytes is not None  # dispatcher enforces requires_media=False here
    text = pdf_text.extract_text(ctx.media_bytes)
    if not text.strip():
        raise UserInputError(
            "PDF contains no extractable text",
            user_message="We couldn't read text from that PDF.",
        )
    return text


__all__ = ["TranslateCommand"]
