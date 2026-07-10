"""EC2 worker entry point.

Polls SQS for jobs, dispatches them to registered commands, sends results
via WhatsApp, deletes the message on success, or surfaces a failure to
DLQ. SIGTERM-aware — drains the in-flight job before exiting.

Run with::

    python -m worker.main

The worker shares :mod:`wactl` (under ``src/``) with the Lambda handler;
both consumers install dependencies via the same release tarball.

Environment variables
---------------------
- ``WACTL_ENV``         ``dev`` | ``staging`` | ``prod``  (default: ``prod``)
- ``AWS_REGION``        AWS region (default: ``us-east-1``)
- ``WACTL_JOBS_QUEUE``  Jobs SQS queue URL (no default — required)
- ``WACTL_WORKER_POLL_SECONDS``  Long-poll wait (default ``20``)
- ``WACTL_WORKER_MAX_MESSAGES``  Max receive per poll (default ``10``)
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from wactl import dispatcher as _dispatcher
from wactl.commands import registry as cmd_registry
from wactl.config import settings
from wactl.integrations.aws import sqs
from wactl.logging import bind_context, configure_logging, get_logger, reset_context
from wactl.models.job import Job
from wactl.webhook import build_deps

# ``worker.shutdown`` is intentionally separate from the package proper
# to keep the worker side-effects (signal handler installation) out of any
# Lambda cold-start path.
from worker import shutdown

configure_logging()
logger = get_logger(__name__)


class Worker:
    """Long-poll + dispatch loop, SIGTERM-aware."""

    def __init__(self) -> None:
        self._deps: Any | None = None

    async def run(self) -> None:
        """Block until SIGTERM. Installs signal handlers first."""
        shutdown.install()
        logger.info("worker.starting")
        try:
            while not shutdown.is_set():
                try:
                    await self._poll_once()
                except Exception as exc:
                    logger.error(
                        "worker.poll_failed",
                        error=type(exc).__name__,
                        message=str(exc),
                    )
                    # Avoid hammering a broken downstream.
                    await asyncio.sleep(min(5, settings.http_timeout_seconds))
        finally:
            logger.info("worker.stopped")
            reset_context()

    async def _poll_once(self) -> None:
        """Single long-poll + dispatch cycle."""
        queue_url = settings.sqs_jobs_queue_url
        if not queue_url:
            logger.warning("worker.no_queue_url")
            await asyncio.sleep(5)
            return

        messages = await asyncio.to_thread(
            sqs.receive_message,
            queue_url,
            max_messages=10,
            wait_seconds=20,
            visibility_timeout=900,
        )
        if not messages:
            return
        for message in messages:
            await self._process_message(message)

    async def _process_message(self, message: dict[str, Any]) -> None:
        """Deserialize, run, ack on success / nack on permanent failure."""
        handle = message.get("_receipt_handle")
        body = message.get("job")
        if not isinstance(body, str):
            logger.warning("worker.unparseable_message", keys=list(message.keys()))
            if handle:
                await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
            return

        try:
            job = Job.model_validate_json(body)
        except Exception as exc:
            logger.error("worker.job_parse_failed", error=type(exc).__name__, message=str(exc))
            if handle:
                await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
            return

        async with _job_context(job):
            try:
                await self._dispatch(job)
                if handle:
                    await asyncio.to_thread(sqs.delete_message, settings.sqs_jobs_queue_url, handle)
                logger.info("worker.job_done", job_id=job.job_id, command=job.command)
            except Exception as exc:
                logger.error(
                    "worker.job_failed",
                    job_id=job.job_id,
                    command=job.command,
                    error=type(exc).__name__,
                    message=str(exc),
                )

    async def _dispatch(self, job: Job) -> None:
        """Look up the command class and run it; ignore sync/async distinction."""
        cls = cmd_registry.get(job.command)
        if cls is None:
            logger.warning("worker.command_not_registered", command=job.command)
            return
        # Worker supports both ``sync=True`` and ``sync=False`` — sync
        # commands run inline here just the same.
        deps = self._deps or build_deps()
        ctx = await _dispatcher.prepare_context(
            cast("Any", _FakeRouted(job.command, cls)),
            user=job.user,
            whatsapp=deps.whatsapp,
            http=deps.http,
            gemini=deps.gemini,
            s3=deps.s3,
            secrets=deps.secrets_manager,
            media_id=job.media_id,
            media_mime=job.media_mime,
            media_filename=job.media_filename,
        )
        cmd: Any = cls()
        await cmd.run(ctx)

    def _ensure_deps(self) -> Any:
        """Lazy-build dependencies — keeps process-import cheap."""
        if self._deps is None:
            self._deps = build_deps()
        return self._deps


class _FakeRouted:
    """Minimal stand-in for :class:`wactl.router.RoutedCommand`.

    :func:`wactl.dispatcher.prepare_context` only touches ``routed.name`` and
    ``routed.cls.meta`` — both of which we provide.
    """

    def __init__(self, name: str, cls: type[Any]) -> None:
        self.name = name
        self.cls = cls


@asynccontextmanager
async def _job_context(job: Job) -> AsyncIterator[None]:
    """Bind log context for the duration of one job."""
    bind_context(job_id=job.job_id, command=job.command, user_phone=job.user.phone)
    try:
        yield
    finally:
        reset_context()


def main() -> None:
    """``python -m worker.main`` entry point."""
    worker = Worker()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(worker.run())


if __name__ == "__main__":
    main()
