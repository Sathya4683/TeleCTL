"""Tests for the EC2 worker (``worker.main``).

The worker is hard-coded to handle a single command (``/pdf-audio``).
These tests stub SQS receive/send, the Gemini TTS pipeline, S3 upload,
and the Telegram client so we can exercise the polling + dispatch loop
end-to-end without any real AWS or Telegram calls.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest


def _job_envelope(
    *,
    command: str = "/pdf-audio",
    user_chat_id: int = 111111111,
    media_id: str = "DOC123",
    media_filename: str = "report.pdf",
) -> str:
    """Build a JSON Job body matching ``wactl.models.job.Job``."""
    job = {
        "job_id": "00000000-0000-0000-0000-000000000001",
        "command": command,
        "args": "",
        "user": {
            "chat_id": user_chat_id,
            "username": "alice",
            "first_name": "Alice",
            "message_id": 42,
        },
        "media_id": media_id,
        "media_mime": "application/pdf",
        "media_filename": media_filename,
        "enqueued_at": "2026-01-01T00:00:00Z",
    }
    return json.dumps(job)


@pytest.mark.asyncio
async def test_worker_picks_up_pdf_audio_and_calls_handler(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Single-message SQS receive → /pdf-audio handler runs end-to-end."""
    import worker.main as worker_main

    # The worker reads settings.sqs_jobs_queue_url; if empty it logs
    # ``worker.no_queue_url`` and returns. Set a fake URL for the test.
    monkeypatch.setattr(
        worker_main.settings, "sqs_jobs_queue_url", "https://sqs.test/q", raising=False
    )

    handled: dict[str, object] = {}

    # Make the worker exit after a single poll.
    worker = worker_main.Worker()
    monkeypatch.setattr(worker, "_stopping", True)

    async def fake_synthesize(pdf_bytes: bytes, *, api_key: str, **_kw):
        handled["synth_bytes"] = pdf_bytes
        handled["api_key"] = api_key
        return b"mp3-bytes"

    # Patch the audiobook pipeline referenced by the worker module.
    monkeypatch.setattr("wactl.commands.pdf_audio.audiobook.synthesize", fake_synthesize)

    # Set the Gemini key on settings (read by PdfAudioCommand).
    monkeypatch.setattr(
        "wactl.config.settings.gemini_api_key", "test-key", raising=False
    )

    # Stub SQS receive_message — returns one message, then empty on next call.
    # NOTE: sqs.receive_message is a SYNC boto3 call wrapped by the worker
    # via asyncio.to_thread, so the fake must also be sync.
    receive_calls = {"n": 0}

    def fake_receive(*_a, **_kw):
        receive_calls["n"] += 1
        if receive_calls["n"] == 1:
            body = {"job": _job_envelope()}
            body["_receipt_handle"] = "rh-1"
            body["_message_id"] = "m-1"
            return [body]
        # Signal "stop" by making the worker exit.
        worker._stopping = True
        return []

    monkeypatch.setattr(worker_main.sqs, "receive_message", fake_receive)

    # Stub SQS delete (also sync — wrapped via asyncio.to_thread).
    deleted: list[str] = []

    def fake_delete(*_a, **_kw):
        deleted.append(_kw.get("receipt_handle", _a[1] if len(_a) > 1 else ""))

    monkeypatch.setattr(worker_main.sqs, "delete_message", fake_delete)

    # Stub S3 helpers used by the command.
    monkeypatch.setattr(
        "wactl.commands.pdf_audio.s3.put_object",
        lambda *a, **kw: handled.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.pdf_audio.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/audio",
    )

    # Stub Telegram client methods used by the command (telegram client
    # lazy-built on first use; we force-build with a MagicMock).
    fake_tg = MagicMock()
    fake_tg.bot_token = "test-token"
    fake_tg.get_file = AsyncMock(
        return_value=MagicMock(result=MagicMock(file_path="docs/file.pdf"))
    )
    fake_tg.download_file = AsyncMock(return_value=b"%PDF-1.4\nfake-pdf\n%%EOF")
    fake_tg.send_audio = AsyncMock(
        return_value=MagicMock(result=MagicMock(message_id=999))
    )
    monkeypatch.setattr(worker, "_ensure_telegram", lambda: fake_tg)

    await worker._poll_once()

    # Synthesize was called with the PDF bytes downloaded via Telegram.
    assert handled["synth_bytes"] == b"%PDF-1.4\nfake-pdf\n%%EOF"
    assert handled["api_key"] == "test-key"
    # Message was acked (deleted from SQS).
    assert len(deleted) == 1
    assert deleted[0] == "rh-1"
    # Telegram send_audio was awaited.
    fake_tg.send_audio.assert_awaited()


@pytest.mark.asyncio
async def test_worker_drops_unknown_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the queue contains a command we don't recognize, ack and skip."""
    import worker.main as worker_main

    monkeypatch.setattr(
        worker_main.settings, "sqs_jobs_queue_url", "https://sqs.test/q", raising=False
    )

    worker = worker_main.Worker()
    monkeypatch.setattr(worker, "_stopping", True)

    body = {"job": _job_envelope(command="/pdf-docx")}
    body["_receipt_handle"] = "rh-2"
    body["_message_id"] = "m-2"

    receive_calls = {"n": 0}

    def fake_receive(*_a, **_kw):
        receive_calls["n"] += 1
        if receive_calls["n"] == 1:
            return [body]
        worker._stopping = True
        return []

    monkeypatch.setattr(worker_main.sqs, "receive_message", fake_receive)

    deleted: list[str] = []

    def fake_delete(*_a, **_kw):
        deleted.append(_kw.get("receipt_handle", _a[1] if len(_a) > 1 else ""))

    monkeypatch.setattr(worker_main.sqs, "delete_message", fake_delete)

    await worker._poll_once()
    # Message acked even though command was unhandled.
    assert deleted == ["rh-2"]
