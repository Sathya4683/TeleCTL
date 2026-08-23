"""``/help`` — list the available slash commands.

Always sync, never requires media. Reads from the global command
registry, so adding a new command automatically shows up in ``/help``.

The output uses Telegram Markdown so each command name renders as a
code block.
"""

from __future__ import annotations

from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import get as get_command
from wactl.commands.registry import names, register
from wactl.exceptions import UserInputError
from wactl.integrations.telegram import messages
from wactl.models.command import CommandResponse

HELP_HEADER = "Available commands:\n"


@register("/help", sync=True, requires_media=False, description="Show this help message")
class HelpCommand(Command):
    """Reply with a Markdown list of every registered command."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.telegram is None:
            raise UserInputError(
                "Telegram client missing from context",
                user_message="Service is misconfigured. Please try again later.",
            )

        lines = [HELP_HEADER]
        for name in names():
            cls = get_command(name)
            if cls is None:
                continue
            desc = cls.meta.description or "(no description)"
            sync_tag = "" if cls.meta.sync else " (async)"
            lines.append(f"• `{name}`{sync_tag} — {desc}")

        text = "\n".join(lines)
        message_id = await messages.send_text(
            ctx.telegram,
            chat_id=ctx.user.chat_id,
            text=text,
            reply_to_message_id=ctx.user.message_id,
            parse_mode="Markdown",
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={"commands_listed": len(lines) - 1},
        )


__all__ = ["HelpCommand"]
