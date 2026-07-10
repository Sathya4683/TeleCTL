"""PDF → DOCX conversion via :mod:`pdf2docx`.

Used by :class:`wactl.commands.pdf_docx.PdfDocxCommand`. Wraps the
``pdf2docx.Converter`` to operate on bytes in / bytes out so commands
don't touch disk or tempfile setup.
"""

from __future__ import annotations

import io

from pdf2docx import Converter  # type: ignore[import-untyped]
from pdf2docx.converter import ConversionException  # type: ignore[import-untyped]

from wactl.exceptions import ConverterError, UserInputError


def pdf_to_docx(pdf_bytes: bytes) -> bytes:
    """Convert ``pdf_bytes`` to DOCX bytes.

    Raises :class:`UserInputError` when the input is unreadable as PDF;
    raises :class:`ConverterError` for any other failure.
    """
    if not pdf_bytes:
        raise UserInputError(
            "Empty PDF input.",
            user_message="The PDF you sent is empty.",
        )

    try:
        src = io.BytesIO(pdf_bytes)
        dst = io.BytesIO()
        cv = Converter(stream=src)
        try:
            cv.convert(dst)
        finally:
            cv.close()
    except (ConversionException, ValueError, OSError, RuntimeError) as exc:
        # pdf2docx raises ConversionException for layout issues and
        # RuntimeError (FileDataError) for unreadable input. Both are
        # "the user gave us a bad PDF" and should surface as such.
        raise UserInputError(
            f"PDF parsing failed: {exc}",
            user_message="We couldn't read your PDF. Please make sure it's valid.",
        ) from exc
    except Exception as exc:
        raise ConverterError(
            f"pdf-to-docx conversion failed: {exc}",
            retryable=False,
        ) from exc

    return dst.getvalue()


__all__ = ["pdf_to_docx"]  # public surface
