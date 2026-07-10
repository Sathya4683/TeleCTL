"""Tests for :mod:`wactl.integrations.converters.merge_pdf`."""

from __future__ import annotations

import io

import pytest

from wactl.exceptions import UserInputError
from wactl.integrations.converters.merge_pdf import merge


def _make_pdf(text: str) -> bytes:
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_merge_empty_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        merge([])


def test_merge_single_pdf_returns_valid_pdf() -> None:
    blob = _make_pdf("only")
    out = merge([blob])
    assert out.startswith(b"%PDF-")
    assert len(out) > 0


def test_merge_two_pdfs_combines_pages() -> None:
    a = _make_pdf("Alpha")
    b = _make_pdf("Beta")
    out = merge([a, b])
    assert out.startswith(b"%PDF-")
    # Round-trip: extract text from the merged PDF and verify both pages present
    from wactl.integrations.converters.pdf_text import extract_text

    text = extract_text(out)
    assert "Alpha" in text
    assert "Beta" in text


def test_merge_invalid_pdf_in_list_raises_user_input_error() -> None:
    a = _make_pdf("good")
    with pytest.raises(UserInputError):
        merge([a, b"not a pdf"])


def test_merge_three_pdfs_preserves_order() -> None:
    blobs = [_make_pdf(f"page-{i}") for i in range(3)]
    out = merge(blobs)
    from wactl.integrations.converters.pdf_text import extract_text

    text = extract_text(out)
    idx0 = text.index("page-0")
    idx1 = text.index("page-1")
    idx2 = text.index("page-2")
    assert idx0 < idx1 < idx2
