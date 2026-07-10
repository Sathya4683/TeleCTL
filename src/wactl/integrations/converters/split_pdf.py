"""Split PDF into chunks — used by ``/split-pdf``.

Pages can be split by fixed size (``pages_per_chunk``) or by an explicit
list of ranges (e.g., ``1-3,5,7-9``). The default is one PDF per page.
"""

from __future__ import annotations

import io

from pypdf import PdfReader, PdfWriter

from wactl.exceptions import ConverterError, UserInputError


def split(
    pdf_bytes: bytes,
    *,
    pages_per_chunk: int = 1,
    ranges: list[tuple[int, int]] | None = None,
) -> list[bytes]:
    """Split ``pdf_bytes``.

    If ``ranges`` is given, split using those ``(start, end)`` page ranges
    (1-indexed, inclusive). Otherwise, split every ``pages_per_chunk``
    pages. Returns a list of PDF blobs.
    """
    if not pdf_bytes:
        raise UserInputError(
            "Empty PDF input.",
            user_message="The PDF you sent is empty.",
        )
    if pages_per_chunk < 1 and not ranges:
        raise UserInputError(
            "pages_per_chunk must be >= 1",
            user_message="Invalid split parameters.",
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception as exc:
        raise UserInputError(
            f"Failed to read PDF: {exc}",
            user_message="We couldn't read your PDF.",
        ) from exc

    if ranges is None:
        ranges = _default_ranges(len(reader.pages), pages_per_chunk)

    outputs: list[bytes] = []
    for start, end in ranges:
        writer = PdfWriter()
        for page_idx in range(start - 1, end):
            if 0 <= page_idx < len(reader.pages):
                writer.add_page(reader.pages[page_idx])
        if len(writer.pages) == 0:  # empty range — skip
            continue
        buf = io.BytesIO()
        try:
            writer.write(buf)
        except Exception as exc:
            raise ConverterError(f"Failed to write split chunk: {exc}") from exc
        outputs.append(buf.getvalue())
    return outputs


def _default_ranges(page_count: int, per_chunk: int) -> list[tuple[int, int]]:
    """Return 1-indexed inclusive ranges covering the whole document."""
    ranges: list[tuple[int, int]] = []
    for start in range(1, page_count + 1, per_chunk):
        end = min(start + per_chunk - 1, page_count)
        ranges.append((start, end))
    return ranges


def parse_ranges(spec: str, max_pages: int) -> list[tuple[int, int]]:
    """Parse a user-supplied range spec like ``1-3,5,7-9`` into 1-indexed tuples.

    Raises :class:`UserInputError` on malformed input.
    """
    out: list[tuple[int, int]] = []
    for raw_piece in spec.split(","):
        piece = raw_piece.strip()
        if not piece:
            continue
        if "-" in piece:
            start_s, end_s = piece.split("-", 1)
            start, end = int(start_s), int(end_s)
        else:
            start = end = int(piece)
        if start < 1 or end < start or end > max_pages:
            raise UserInputError(
                f"Range {piece!r} is out of bounds",
                user_message=f"Invalid page range: {piece}",
            )
        out.append((start, end))
    if not out:
        raise UserInputError(
            "No pages selected",
            user_message="Please specify at least one page.",
        )
    return out


__all__ = ["parse_ranges", "split"]


# Helper for the merge module — avoided via export but exposed for tests.
def _open_writer() -> PdfWriter:  # pragma: no cover
    return PdfWriter()
