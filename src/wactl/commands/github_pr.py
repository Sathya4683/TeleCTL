"""``/github-pr`` — fetch a GitHub PR and summarize it via Gemini.

Runs synchronously in Lambda: a single GitHub API call plus a single
Gemini summary is well under 10 seconds. The user passes the PR URL
as the command args.
"""

from __future__ import annotations

import structlog

from wactl.commands._helpers import require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.gemini import text as gemini_text
from wactl.integrations.github import pr_summary as github_pr_summary
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse

logger = structlog.get_logger(__name__)


@register("/github-pr", sync=True, description="Summarize a GitHub pull request")
class GitHubPrCommand(Command):
    """Fetch PR metadata + diff, summarize, reply."""

    async def run(self, ctx: CommandContext) -> CommandResponse:
        url = ctx.args.strip()
        if not url:
            raise UserInputError(
                "/github-pr needs a PR URL",
                user_message="Please send a GitHub PR URL with /github-pr.",
            )
        if ctx.http is None or ctx.gemini is None:
            raise UserInputError(
                "Service is not configured for /github-pr",
                user_message="Service is misconfigured. Please try again later.",
            )

        token = _github_token(ctx)
        pr = await github_pr_summary.fetch_pr(ctx.http, url, token=token)
        summary = await gemini_text.summarize_github_pr(
            ctx.gemini,
            title=pr.title,
            body=pr.body,
            diff=pr.diff,
            additions=pr.additions,
            deletions=pr.deletions,
            changed_files=pr.changed_files,
        )

        head = f"_{pr.title}_\n_{pr.owner}/{pr.repo}#{pr.number}_"
        text = f"{head}\n\n{summary}"
        whatsapp = require_whatsapp(ctx)
        message_id = await messages.send_text(
            whatsapp,
            to=ctx.user.phone,
            body=text,
            reply_to_message_id=ctx.user.message_id,
        )
        logger.info(
            "github_pr.sent",
            url=pr.url,
            additions=pr.additions,
            deletions=pr.deletions,
            changed_files=pr.changed_files,
        )
        return CommandResponse(
            success=True,
            message_id=message_id,
            notes={
                "url": pr.url,
                "owner": pr.owner,
                "repo": pr.repo,
                "number": pr.number,
                "additions": pr.additions,
                "deletions": pr.deletions,
            },
        )


def _github_token(ctx: CommandContext) -> str | None:
    """Resolve an optional GitHub PAT from extra context.

    Production deployments pass the token via ``ctx._extra["github_token"]``.
    Public repos work without one (60 req/hr).
    """
    extra = getattr(ctx, "_extra", None) or {}
    token = extra.get("github_token")
    return str(token) if token else None


__all__ = ["GitHubPrCommand"]
