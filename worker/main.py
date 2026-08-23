"""EC2 worker entry point.

The worker's only job today is ``/pdf-audio``: poll SQS for a job envelope,
download the PDF from Telegram, synthesize an MP3 via Gemini TTS, upload
to S3, and send the audio back to the user. The pipeline is the same as
:class:`wactl.commands.pdf_audio.PdfAudioCommand`; we hard-code the call
here instead of routing through the dispatcher because the worker's job
mix is exactly one command.

SIGTERM-aware — ``asyncio.run`` propagates the cancellation and systemd's
``TimeoutStopSec=30`` gives us time to finish in-flight work.

Run with::

    python -m worker.main

Environment variables
---------------------
- ``TELEGRAM_BOT_TOKEN``   Bot token from @BotFather (required)
- ``GEMINI_API_KEY``        Gemini TTS API key (required)
- ``AWS_REGION``            AWS region (default: ``us-east-1``)
- ``WACTL_JOBS_QUEUE``      Jobs SQS FIFO queue URL (required)
- ``WACTL_S3_MEDIA_BUCKET`` Media bucket for output MP3s (required)
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from wactl.commands.base import CommandContext
from wactl.commands.pdf_audio import PdfAudioCommand
from wactl.config import settings
from wactl.integrations.aws import sqs
from wactl.integrations.telegram import media as tg_media
from wactl.integrations.telegram.client import TelegramClient
from wactl.logging import bind_context, configure_logging, get_logger, reset_context
from wactl.models.job import Job

configure_logging()
logger = get_logger(__name__)


class Worker:
    """Long-poll + dispatch loop for the (single) async command."""

    def __init__(self) -> None:
        self._telegram: TelegramClient | None = None
        self._stopping = False

    async def run(self) -> None:
        """Block until SIGTERM. Installs signal handlers first."""
        loop = asyncio.get_running_loop()
        for sig in (asyncio.signal.SIGTERM, asyncio.signal.SIGINT):
            loop.add_signal_handler(sig, self._on_signal, sig)

        logger.info("worker.starting", queue_url=settings.sqs_jobs_queue_url)
        try:
            while not self._stopping:
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
            if self._telegram is not None:
                await self._telegram.aclose()
            reset_context()

    def _on_signal(self, sig: int) -> None:
        logger.info("worker.signal_received", signal=sig)
        self._stopping = True

    def _ensure_telegram(self) -> TelegramClient:
        if self._telegram is None:
            if not settings.telegram_bot_token:
                raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
            self._telegram = TelegramClient(
                bot_token=settings.telegram_bot_token,
                api_base=settings.telegram_api_base,
                timeout_seconds=settings.http_timeout_seconds,
            )
        return self._telegram

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
        """Deserialize, run, ack on success / redrive on failure."""
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
                await self._handle_pdf_audio(job)
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
                # Leave the message alone → SQS redrives up to max_receive_count
                # then DLQs. ``WactlError.retryable`` controls nothing here;
                # we let the redrive policy decide.

    async def _handle_pdf_audio(self, job: Job) -> None:
        """The single async command we support.

        Mirrors :class:`PdfAudioCommand.run` end-to-end — downloads the PDF,
        synthesizes audio, uploads the MP3, replies to the user.
        """
        if job.command != "/pdf-audio":
            logger.warning("worker.unknown_command_dropped", command=job.command)
            return

        telegram = self._ensure_telegram()

        # We need media_bytes — same as the Lambda path. The dispatcher
        # pattern is overkill here; do the two-step inline.
        if job.media_id is None:
            raise ValueError("/pdf-audio job is missing media_id")

        async with _step("download", chat_id=job.user.chat_id):
            media_bytes = await tg_media.download(telegram, job.media_id)

        # Build the context the command expects.
        ctx = CommandContext(
            user=job.user,
            args=job.args,
            media_id=job.media_id,
            media_bytes=media_bytes,
            media_mime_type=job.media_mime,
            media_filename=job.media_filename,
            telegram=telegram,
        )

        async with _step("synthesize", chat_id=job.user.chat_id):
            response = await PdfAudioCommand().run(ctx)

        logger.info(
            "worker.pdf_audio.delivered",
            chat_id=job.user.chat_id,
            message_id=response.message_id,
        )


@asynccontextmanager
async def _step(name: str, **fields: Any) -> AsyncIterator[None]:
    """Log begin/end of a pipeline step with bound context."""
    bind_context(step=name, **fields)
    try:
        yield
    finally:
        reset_context()


@asynccontextmanager
async def _job_context(job: Job) -> AsyncIterator[None]:
    """Bind log context for the duration of one job."""
    bind_context(job_id=job.job_id, command=job.command, chat_id=str(job.user.chat_id))
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
