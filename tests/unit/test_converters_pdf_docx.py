"""Tests for :mod:`wactl.integrations.converters.pdf_docx`."""

from __future__ import annotations

import io

import pytest

from wactl.exceptions import UserInputError
from wactl.integrations.converters.pdf_docx import pdf_to_docx


def _make_pdf(text: str = "hello") -> bytes:
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_pdf_to_docx_empty_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        pdf_to_docx(b"")


def test_pdf_to_docx_returns_valid_docx() -> None:
    pdf = _make_pdf("hello world")
    out = pdf_to_docx(pdf)
    # DOCX files are ZIP archives starting with the PK magic header.
    assert out.startswith(b"PK")
    assert len(out) > 0


def test_pdf_to_docx_invalid_pdf_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        pdf_to_docx(b"not a pdf at all")


def test_pdf_to_docx_multipage() -> None:
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    for i in range(3):
        p = doc.new_page()
        p.insert_text((72, 72), f"page {i + 1}")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    out = pdf_to_docx(buf.getvalue())
    assert out.startswith(b"PK")
    assert len(out) > 1000  # multi-page DOCX should be reasonably large
