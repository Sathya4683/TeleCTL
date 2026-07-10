"""Tests for :mod:`wactl.integrations.converters.pdf_text`."""

from __future__ import annotations

import io

import pytest

from wactl.exceptions import UserInputError
from wactl.integrations.converters.pdf_text import extract_text, is_pdf, page_count


def _make_pdf(text_per_page: list[str]) -> bytes:
    """Generate a tiny multi-page PDF using pymupdf."""
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    for text in text_per_page:
        page = doc.new_page()
        page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_is_pdf_true() -> None:
    assert is_pdf(b"%PDF-1.4\n")


def test_is_pdf_false() -> None:
    assert not is_pdf(b"hello world")
    assert not is_pdf(b"")


def test_extract_text_empty_raises() -> None:
    with pytest.raises(UserInputError):
        extract_text(b"")


def test_extract_text_single_page() -> None:
    pdf = _make_pdf(["Hello world"])
    text = extract_text(pdf)
    assert "Hello" in text


def test_extract_text_multi_page() -> None:
    pdf = _make_pdf(["Page one text", "Page two text", "Page three text"])
    text = extract_text(pdf)
    assert "Page one" in text
    assert "Page two" in text
    assert "Page three" in text
    # Pages separated by blank line
    assert text.count("\n\n") >= 2


def test_extract_text_invalid_pdf_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        extract_text(b"not a pdf at all")


def test_page_count_multi() -> None:
    pdf = _make_pdf(["a", "b", "c"])
    assert page_count(pdf) == 3


def test_page_count_invalid_raises() -> None:
    with pytest.raises(UserInputError):
        page_count(b"junk")


def test_extract_text_handles_blank_page_gracefully() -> None:
    """A page with no text should not crash; produce empty doc."""
    pdf = _make_pdf(["", "  "])
    text = extract_text(pdf)
    assert isinstance(text, str)
