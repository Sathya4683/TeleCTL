"""Dispatch commands — synchronously (Lambda) or async (SQS → worker).

The dispatcher is the boundary between the webhook handler and the
command implementation. It:
- Validates the routed command against ``CommandMeta`` (requires_media, etc.)
- Downloads inbound media via the WhatsApp client when needed
- Either runs the command immediately (``dispatch_sync``) or enqueues a
  :class:`Job` to SQS for the worker to pick up (``dispatch_async``).

Nothing here is command-specific — adding a new command never touches
this file.
"""

from __future__ import annotations

from typing import Any, cast

from wactl.commands.base import Command, CommandContext
from wactl.exceptions import CommandNotFoundError, UserInputError
from wactl.integrations.whatsapp.media import download as _download_media
from wactl.models.command import CommandResponse
from wactl.models.job import Job
from wactl.models.user import UserContext
from wactl.router import RoutedCommand


async def prepare_context(
    routed: RoutedCommand,
    *,
    user: UserContext,
    whatsapp: Any,
    raw_body: str = "",
    media_id: str | None = None,
    media_mime: str | None = None,
    media_filename: str | None = None,
    s3: Any = None,
    sqs: Any = None,
    http: Any = None,
    gemini: Any = None,
    secrets: Any = None,
) -> CommandContext:
    """Build a :class:`CommandContext` and, if needed, download inbound media.

    Raises :class:`UserInputError` if the command requires media but none
    was attached, or if the media download fails.
    """
    media_bytes: bytes | None = None
    cmd_cls = cast("type[Command]", routed.cls)
    if cmd_cls.meta.requires_media:
        if media_id is None:
            raise UserInputError(
                f"Command {routed.name!r} requires an attachment",
                user_message=f"Please attach a file when using {routed.name}.",
            )
        if whatsapp is None:
            raise UserInputError(
                f"Command {routed.name!r} requires WhatsApp but no client was provided",
                user_message="Service is misconfigured. Please try again later.",
            )
        media_bytes = await _download_media(whatsapp, media_id)

    return CommandContext(
        user=user,
        args=routed.args,
        raw_body=raw_body,
        media_id=media_id,
        media_bytes=media_bytes,
        media_mime_type=media_mime,
        whatsapp=whatsapp,
        secrets=secrets,
        s3=s3,
        sqs=sqs,
        http=http,
        gemini=gemini,
        media_filename=media_filename,
    )


async def dispatch_sync(
    routed: RoutedCommand,
    *,
    user: UserContext,
    whatsapp: Any,
    raw_body: str = "",
    media_id: str | None = None,
    media_mime: str | None = None,
    media_filename: str | None = None,
    s3: Any = None,
    sqs: Any = None,
    http: Any = None,
    gemini: Any = None,
    secrets: Any = None,
) -> CommandResponse:
    """Run a sync command inline. Returns the command's response."""
    cmd_cls = cast("type[Command]", routed.cls)
    ctx = await prepare_context(
        routed,
        user=user,
        whatsapp=whatsapp,
        raw_body=raw_body,
        media_id=media_id,
        media_mime=media_mime,
        media_filename=media_filename,
        s3=s3,
        sqs=sqs,
        http=http,
        gemini=gemini,
        secrets=secrets,
    )
    cmd: Command = cmd_cls()
    return await cmd.run(ctx)


async def dispatch_async(
    routed: RoutedCommand,
    *,
    user: UserContext,
    sqs: Any,
    queue_url: str,
    raw_body: str = "",
    media_id: str | None = None,
    media_mime: str | None = None,
    media_filename: str | None = None,
) -> str:
    """Enqueue a Job to SQS for the worker. Returns the SQS MessageId.

    Sync-only fields (``whatsapp``, ``http``, ``gemini``) are not part of
    the job — the worker re-hydrates them from environment / Secrets Manager.
    """
    if sqs is None:
        raise CommandNotFoundError("dispatch_async called without sqs client")
    cmd_cls = cast("type[Command]", routed.cls)
    job = Job(
        command=routed.name,
        args=routed.args,
        user=user,
        media_id=media_id,
        media_mime=media_mime,
        media_filename=media_filename,
        meta=cmd_cls.meta,
    )
    # Pydantic's model_dump_json keeps the envelope small + deterministic.
    body = job.model_dump_json()
    return cast("str", await sqs.send_message(queue_url, {"job": body}))


__all__ = ["dispatch_async", "dispatch_sync", "prepare_context"]
