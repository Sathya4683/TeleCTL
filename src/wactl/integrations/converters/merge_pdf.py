"""Merge multiple PDF inputs into one, using :mod:`pypdf`."""

from __future__ import annotations

import io

from pypdf import PdfWriter

from wactl.exceptions import ConverterError, UserInputError


def merge(pdf_blobs: list[bytes]) -> bytes:
    """Concatenate ``pdf_blobs`` (in order) and return the merged PDF bytes."""
    if not pdf_blobs:
        raise UserInputError(
            "merge() called with no inputs",
            user_message="Please attach at least one PDF.",
        )

    writer = PdfWriter()
    for idx, blob in enumerate(pdf_blobs):
        try:
            writer.append(io.BytesIO(blob))
        except Exception as exc:
            raise UserInputError(
                f"PDF {idx + 1} is not a valid PDF: {exc}",
                user_message=f"PDF #{idx + 1} is not a valid PDF.",
            ) from exc

    out = io.BytesIO()
    try:
        writer.write(out)
    except Exception as exc:
        raise ConverterError(f"PDF merge failed: {exc}") from exc
    return out.getvalue()


__all__ = ["merge"]


# ─── Helper exposed for the split command ──────────────────────────────


def open_writer() -> PdfWriter:
    """Create an empty :class:`PdfWriter` (helper for split_pdf)."""
    return PdfWriter()
