"""Tests for :mod:`wactl.commands.split_pdf`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import split_pdf as cmd_split_pdf
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_split_pdf_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Page count, split, upload, and document send happen in order."""
    called: dict[str, object] = {}

    monkeypatch.setattr(
        "wactl.commands.split_pdf.pdf_text.page_count",
        lambda _b: 5,
    )

    def fake_split(_pdf: bytes, **kwargs):
        called["split_kwargs"] = kwargs
        return [b"chunk-1", b"chunk-2"]

    monkeypatch.setattr(
        "wactl.integrations.converters.split_pdf.split",
        fake_split,
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_document",
        _capture_send,
    )

    monkeypatch.setattr(
        "wactl.commands.split_pdf.s3.put_object",
        lambda *a, **kw: called.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.split_pdf.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/split",
    )

    ctx = make_context(
        media_bytes=b"%PDF-1.4",
        media_mime_type="application/pdf",
        args="1-3",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_split_pdf.SplitPdfCommand().run(ctx)

    assert resp.success
    assert resp.message_id == "wamid.OUT"
    assert called["send_kwargs"]["link"] == "https://signed.example/split"
    assert called["send_kwargs"]["caption"] == "Part 1 of 2."
    assert resp.notes["total_pages"] == 5
    assert resp.notes["total_chunks"] == 2
    assert resp.notes["chunk"] == 1


@pytest.mark.asyncio
async def test_split_pdf_uses_pages_per_chunk_when_no_args(
    monkeypatch: pytest.MonkeyPatch, fake_whatsapp
) -> None:
    """Without args, defaults to one PDF per page."""
    called: dict[str, object] = {}

    monkeypatch.setattr(
        "wactl.commands.split_pdf.pdf_text.page_count",
        lambda _b: 3,
    )

    def fake_split(_pdf: bytes, **kwargs):
        called["split_kwargs"] = kwargs
        return [b"p1", b"p2", b"p3"]

    monkeypatch.setattr(
        "wactl.integrations.converters.split_pdf.split",
        fake_split,
    )
    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_document",
        AsyncMock(return_value="wamid.OUT"),
    )
    monkeypatch.setattr(
        "wactl.commands.split_pdf.s3.put_object",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "wactl.commands.split_pdf.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/x",
    )

    ctx = make_context(
        media_bytes=b"%PDF-1.4",
        media_mime_type="application/pdf",
        args="",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_split_pdf.SplitPdfCommand().run(ctx)

    assert resp.success
    assert called["split_kwargs"].get("pages_per_chunk") == 1
    assert resp.notes["total_chunks"] == 3


@pytest.mark.asyncio
async def test_split_pdf_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_split_pdf.SplitPdfCommand().run(ctx)
