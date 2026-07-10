"""Tests for :mod:`wactl.integrations.converters.split_pdf`."""

from __future__ import annotations

import io

import pytest

from wactl.exceptions import UserInputError
from wactl.integrations.converters.split_pdf import parse_ranges, split


def _make_pdf(page_count: int) -> bytes:
    import fitz  # type: ignore[import-untyped]

    doc = fitz.open()
    for i in range(page_count):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {i + 1}")
    buf = io.BytesIO()
    doc.save(buf)
    doc.close()
    return buf.getvalue()


def test_split_empty_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        split(b"")


def test_split_default_one_per_chunk() -> None:
    pdf = _make_pdf(3)
    parts = split(pdf)
    assert len(parts) == 3
    for blob in parts:
        assert blob.startswith(b"%PDF-")


def test_split_with_pages_per_chunk() -> None:
    pdf = _make_pdf(5)
    parts = split(pdf, pages_per_chunk=2)
    assert len(parts) == 3  # [1-2], [3-4], [5]
    from wactl.integrations.converters.pdf_text import page_count as _pc

    assert _pc(parts[0]) == 2
    assert _pc(parts[1]) == 2
    assert _pc(parts[2]) == 1


def test_split_with_explicit_ranges() -> None:
    pdf = _make_pdf(5)
    parts = split(pdf, ranges=[(1, 2), (4, 5)])
    assert len(parts) == 2
    from wactl.integrations.converters.pdf_text import page_count as _pc

    assert _pc(parts[0]) == 2
    assert _pc(parts[1]) == 2


def test_split_invalid_pdf_raises_user_input_error() -> None:
    with pytest.raises(UserInputError):
        split(b"not a pdf")


def test_split_zero_per_chunk_raises() -> None:
    pdf = _make_pdf(2)
    with pytest.raises(UserInputError):
        split(pdf, pages_per_chunk=0)


# ─── parse_ranges ──────────────────────────────────────────────────────


def test_parse_ranges_simple() -> None:
    assert parse_ranges("1-3,5,7-9", max_pages=10) == [(1, 3), (5, 5), (7, 9)]


def test_parse_ranges_single_page() -> None:
    assert parse_ranges("3", max_pages=10) == [(3, 3)]


def test_parse_ranges_strips_whitespace() -> None:
    assert parse_ranges("1-2, 4", max_pages=5) == [(1, 2), (4, 4)]


def test_parse_ranges_out_of_bounds_raises() -> None:
    with pytest.raises(UserInputError):
        parse_ranges("1-10", max_pages=5)


def test_parse_ranges_reversed_raises() -> None:
    with pytest.raises(UserInputError):
        parse_ranges("5-3", max_pages=10)


def test_parse_ranges_zero_raises() -> None:
    with pytest.raises(UserInputError):
        parse_ranges("0-2", max_pages=10)


def test_parse_ranges_empty_raises() -> None:
    with pytest.raises(UserInputError):
        parse_ranges("", max_pages=10)


def test_parse_ranges_skips_empty_pieces() -> None:
    assert parse_ranges("1, ,3", max_pages=5) == [(1, 1), (3, 3)]
