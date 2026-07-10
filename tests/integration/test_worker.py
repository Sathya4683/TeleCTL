"""Tests for :mod:`worker.main` — the SQS long-poll loop.

These tests stub SQS via the integration module's functions, so no AWS
round-trip is involved. Real behavioral verification happens against a
``moto``-mocked SQS in the end-to-end test (Phase 11).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from worker import main as worker_main

from wactl.models.job import Job
from wactl.models.user import UserContext


@pytest.fixture
def fake_sqs_messages(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Patch SQS to return whatever messages we queue."""
    queue: list[dict[str, Any]] = []
    monkeypatch.setattr("wactl.config.settings.sqs_jobs_queue_url", "https://sqs.test/q")

    def receive(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        return list(queue)

    def delete(_queue_url: str, handle: str) -> None:
        queue[:] = [m for m in queue if m["_receipt_handle"] != handle]

    monkeypatch.setattr("wactl.integrations.aws.sqs.receive_message", receive)
    monkeypatch.setattr("wactl.integrations.aws.sqs.delete_message", delete)
    monkeypatch.setattr("wactl.integrations.aws.sqs.send_message", lambda *_a, **_kw: "msg-id")
    return queue


def _enqueue(queue: list[dict[str, Any]], job: Job) -> None:
    queue.append(
        {
            "_receipt_handle": f"rh-{job.job_id}",
            "_message_id": f"mid-{job.job_id}",
            "job": job.model_dump_json(),
        }
    )


@pytest.fixture
def stub_command_run(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace `prepare_context` and ``PdfDocxCommand.run`` so the test is hermetic."""
    sentinel: dict[str, Any] = {}

    async def _fake_prepare_context(*_a: Any, **_kw: Any) -> Any:
        return MagicMock(name="ctx")

    async def _fake_run(_self: Any, _ctx: Any) -> Any:
        sentinel["ran"] = True

        class _Resp:
            success = True

        return _Resp()

    # Worker imports ``dispatcher`` via ``import … as …`` then calls
    # ``_dispatcher.prepare_context``. Patch the attribute on the worker's
    # bound reference.
    import worker.main as _wm

    monkeypatch.setattr(_wm._dispatcher, "prepare_context", _fake_prepare_context)

    from wactl.commands import pdf_docx

    monkeypatch.setattr(pdf_docx.PdfDocxCommand, "run", _fake_run)
    return sentinel


def _user() -> UserContext:
    return UserContext(
        phone="15551234567",
        name="alice",
        message_id="wamid.M1",
        waba_id="waba-1",
        phone_number_id="pn-1",
    )


def _job(command: str = "/pdf-docx") -> Job:
    return Job(
        command=command,
        args="",
        user=_user(),
        media_id="mid.test",
        media_mime="application/pdf",
    )


def _patch_run_with_sentinel(monkeypatch: pytest.MonkeyPatch, sentinel: dict[str, Any]) -> None:
    """Stub ``PdfDocxCommand.run`` to record invocation + return success."""
    return  # obsolete; use stub_command_run fixture



def _make_worker_with_fake_deps() -> worker_main.Worker:
    """Build a worker whose ``build_deps`` is bypassed."""
    worker = worker_main.Worker()
    fake_deps = MagicMock(
        name="deps",
        whatsapp=MagicMock(),
        http=MagicMock(),
        gemini=MagicMock(),
        s3=None,
        secrets_manager=None,
    )
    worker._deps = fake_deps  # type: ignore[attr-defined]
    return worker


@pytest.mark.asyncio
async def test_worker_processes_queued_job(
    monkeypatch: pytest.MonkeyPatch,
    fake_sqs_messages: list[dict[str, Any]],
    stub_command_run: dict[str, Any],
) -> None:
    """A queued Job gets deserialized, dispatched, then ack'd via delete."""
    job = _job()
    _enqueue(fake_sqs_messages, job)

    def _receive_then_stop(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        monkeypatch.setattr(worker_main.shutdown, "is_set", lambda: True)
        return list(fake_sqs_messages)

    monkeypatch.setattr("wactl.integrations.aws.sqs.receive_message", _receive_then_stop)

    worker = _make_worker_with_fake_deps()
    await worker.run()

    assert stub_command_run.get("ran") is True
    assert not fake_sqs_messages  # message deleted after success


@pytest.mark.asyncio
async def test_worker_drops_unparseable_message(
    monkeypatch: pytest.MonkeyPatch,
    fake_sqs_messages: list[dict[str, Any]],
) -> None:
    """A malformed SQS body is logged + deleted (poison-pill safety)."""
    fake_sqs_messages.append(
        {
            "_receipt_handle": "rh-bad",
            "_message_id": "mid-bad",
            "job": "not-json{{",
        }
    )

    def _receive_then_stop(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        monkeypatch.setattr(worker_main.shutdown, "is_set", lambda: True)
        return list(fake_sqs_messages)

    monkeypatch.setattr("wactl.integrations.aws.sqs.receive_message", _receive_then_stop)
    worker = _make_worker_with_fake_deps()
    await worker.run()

    assert not fake_sqs_messages


@pytest.mark.asyncio
async def test_worker_drains_after_exception(
    monkeypatch: pytest.MonkeyPatch,
    fake_sqs_messages: list[dict[str, Any]],
) -> None:
    """If SQS receive_message raises, the worker logs and continues."""
    received = {"n": 0}

    def _flaky(*_a: Any, **_kw: Any) -> list[dict[str, Any]]:
        received["n"] += 1
        if received["n"] == 1:
            raise RuntimeError("simulated SQS outage")
        monkeypatch.setattr(worker_main.shutdown, "is_set", lambda: True)
        return []

    monkeypatch.setattr("wactl.integrations.aws.sqs.receive_message", _flaky)
    worker = _make_worker_with_fake_deps()
    await worker.run()

    assert received["n"] >= 2
