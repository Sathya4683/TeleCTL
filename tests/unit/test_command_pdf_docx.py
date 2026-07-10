"""Tests for :mod:`wactl.commands.pdf_docx`."""

from __future__ import annotations

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import pdf_docx
from wactl.exceptions import UserInputError


def _make_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n% test\n%%EOF"


@pytest.mark.asyncio
async def test_pdf_docx_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """End-to-end: convert (mocked) → upload (mocked) → reply (mocked)."""
    called: dict[str, object] = {}

    def fake_pdf_to_docx(data: bytes) -> bytes:
        called["convert_input"] = data
        return b"docx-bytes"

    monkeypatch.setattr(
        "wactl.integrations.converters.pdf_docx.pdf_to_docx",
        fake_pdf_to_docx,
    )

    async def _capturing_send(*_args, **kwargs):
        called["send_kwargs"] = kwargs
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_document",
        _capturing_send,
    )

    def fake_put(bucket, key, body, *, content_type=None, metadata=None):
        called["put"] = (bucket, key, body, content_type)

    monkeypatch.setattr("wactl.commands.pdf_docx.s3.put_object", fake_put)
    monkeypatch.setattr(
        "wactl.commands.pdf_docx.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/abc",
    )

    ctx = make_context(media_bytes=_make_pdf_bytes(), whatsapp=fake_whatsapp)
    resp = await pdf_docx.PdfDocxCommand().run(ctx)

    assert resp.success
    assert resp.message_id == "wamid.OUT"
    assert called["convert_input"] == _make_pdf_bytes()
    assert called["send_kwargs"]["link"] == "https://signed.example/abc"


@pytest.mark.asyncio
async def test_pdf_docx_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await pdf_docx.PdfDocxCommand().run(ctx)
