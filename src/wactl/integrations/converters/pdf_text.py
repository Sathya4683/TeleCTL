"""PDF text extraction via :mod:`pymupdf` (the ``fitz`` binding).

Used by the audiobook service. Returns plain text suitable for chunking
into TTS-sized pieces.
"""

from __future__ import annotations

import fitz  # type: ignore[import-untyped]

from wactl.exceptions import ConverterError, UserInputError


def extract_text(pdf_bytes: bytes) -> str:
    """Extract plain text from a PDF, page by page."""
    if not pdf_bytes:
        raise UserInputError(
            "Empty PDF input.",
            user_message="The PDF you sent is empty.",
        )
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise UserInputError(
            f"Failed to open PDF: {exc}",
            user_message="We couldn't open your PDF.",
        ) from exc

    try:
        parts: list[str] = []
        for page in doc:
            parts.append(page.get_text("text"))
        return "\n\n".join(parts).strip()
    except Exception as exc:
        raise ConverterError(
            f"PDF text extraction failed: {exc}",
        ) from exc
    finally:
        doc.close()


def page_count(pdf_bytes: bytes) -> int:
    """Return the number of pages in the PDF."""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        raise UserInputError(f"Failed to open PDF: {exc}") from exc
    try:
        return int(doc.page_count)
    finally:
        doc.close()


__all__ = ["extract_text", "page_count"]


# Public re-exports for cleaner callers.
def is_pdf(data: bytes) -> bool:
    """Sniff the first 5 bytes for the PDF magic header."""
    return data.startswith(b"%PDF-")
