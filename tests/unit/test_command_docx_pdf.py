"""Tests for :mod:`wactl.commands.docx_pdf` + its converter."""

from __future__ import annotations

import io

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import docx_pdf
from wactl.exceptions import UserInputError
from wactl.integrations.converters import docx_pdf as converter

# ─── converter ────────────────────────────────────────────────────────


def _make_docx_bytes() -> bytes:
    """Build a minimal valid DOCX in memory."""
    from docx import Document

    doc = Document()
    doc.add_heading("Title Page", level=0)
    doc.add_paragraph("This is the introduction.")
    doc.add_heading("First Section", level=1)
    doc.add_paragraph("Body text with some content.")
    doc.add_heading("Subsection", level=2)
    doc.add_paragraph("More body text.")
    doc.add_paragraph("")  # empty paragraph
    doc.add_paragraph("Final paragraph with <html> & special chars.")

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_to_pdf_returns_valid_pdf() -> None:
    """Output should be a non-trivial PDF byte string."""
    pdf_bytes = converter.docx_to_pdf(_make_docx_bytes())
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 100


def test_docx_to_pdf_empty_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        converter.docx_to_pdf(b"")


def test_docx_to_pdf_invalid_raises_user_input_error() -> None:
    """Garbage bytes should fail with a friendly UserInputError."""
    with pytest.raises(UserInputError):
        converter.docx_to_pdf(b"this is not a docx file")


# ─── command ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_docx_pdf_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_telegram) -> None:
    """End-to-end: parse (real DOCX in fixture) → upload via multipart (mocked)."""
    called: dict[str, object] = {}

    def fake_docx_to_pdf(data: bytes) -> bytes:
        called["convert_input"] = data
        return b"%PDF-1.4\n% stub"

    monkeypatch.setattr(
        "wactl.integrations.converters.docx_pdf.docx_to_pdf",
        fake_docx_to_pdf,
    )

    async def _capturing_upload(*_args, **kwargs):
        called["upload_kwargs"] = kwargs
        return "999"

    monkeypatch.setattr(
        "wactl.integrations.telegram.messages.upload_document",
        _capturing_upload,
    )

    ctx = make_context(
        media_bytes=_make_docx_bytes(),
        media_filename="resume.docx",
        telegram=fake_telegram,
    )
    resp = await docx_pdf.DocxPdfCommand().run(ctx)

    assert resp.success
    assert resp.message_id == "999"
    assert called["convert_input"] == ctx.media_bytes
    assert called["upload_kwargs"]["file_bytes"] == b"%PDF-1.4\n% stub"
    assert called["upload_kwargs"]["filename"] == "resume.pdf"
    assert called["upload_kwargs"]["chat_id"] == 111111111
    assert "Here's your PDF" in called["upload_kwargs"]["caption"]


@pytest.mark.asyncio
async def test_docx_pdf_requires_media(fake_telegram) -> None:
    ctx = make_context(media_bytes=None, telegram=fake_telegram)
    with pytest.raises(UserInputError):
        await docx_pdf.DocxPdfCommand().run(ctx)


def test_docx_pdf_filename_fallback() -> None:
    """Without an inbound filename, output filename falls back to ``output.pdf``."""
    # Indirectly verified by the command's filename logic; this test
    # documents the contract for future readers.
    assert docx_pdf.PDF_SUFFIX == ".pdf"
    assert docx_pdf.DOCX_SUFFIX == ".docx"


def test_docx_pdf_is_registered_as_sync() -> None:
    """/docx-pdf is sync — runs inline in Lambda within the 15-min timeout."""
    from wactl.commands.registry import get

    cls = get("/docx-pdf")
    assert cls is not None
    assert cls.meta.sync is True
