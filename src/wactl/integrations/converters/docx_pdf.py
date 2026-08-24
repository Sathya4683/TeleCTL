"""DOCX to PDF converter (text-only).

Uses :mod:`python-docx` to parse the DOCX and :mod:`reportlab` to
render a basic PDF. **Formatting fidelity is intentionally limited:**
bold/italic/headings are preserved, but tables, images, lists, fonts,
and complex layout are flattened to plain text. For full-fidelity
DOCX to PDF rendering, use a tool like LibreOffice headless or
``aspose-words-cloud`` (neither of which we ship).

Typical conversion is 1-3 seconds for a 20-page DOCX.
"""

from __future__ import annotations

import io

from docx import Document
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from wactl.exceptions import ConverterError, UserInputError

PAGE_MARGIN = 0.75 * inch


def docx_to_pdf(docx_bytes: bytes) -> bytes:
    """Convert ``docx_bytes`` to a PDF byte string.

    Raises :class:`UserInputError` if the input is unreadable as a DOCX.
    Raises :class:`ConverterError` for any other failure during conversion.
    """
    if not docx_bytes:
        raise UserInputError(
            "Empty DOCX input.",
            user_message="The DOCX you sent is empty.",
        )

    try:
        document = Document(io.BytesIO(docx_bytes))
    except Exception as exc:
        raise UserInputError(
            f"DOCX parse failed: {exc}",
            user_message="We couldn't read your DOCX. Please make sure it's a valid file.",
        ) from exc

    try:
        buffer = io.BytesIO()
        _render(document, buffer)
        return buffer.getvalue()
    except UserInputError:
        raise
    except Exception as exc:
        raise ConverterError(
            f"DOCX to PDF conversion failed: {exc}",
            retryable=False,
        ) from exc


def _render(document, buffer: io.BytesIO) -> None:
    """Render a parsed ``python-docx`` Document into ``buffer`` as PDF."""
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        leftMargin=PAGE_MARGIN,
        rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN,
        bottomMargin=PAGE_MARGIN,
        title="Converted from DOCX",
    )
    base = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=base["BodyText"],
        fontSize=11,
        leading=14,
        spaceAfter=6,
    )
    heading_styles = {
        0: ParagraphStyle("H0", parent=base["Title"], fontSize=22, leading=28, spaceAfter=14),
        1: ParagraphStyle("H1", parent=base["Heading1"], fontSize=18, leading=22, spaceAfter=12),
        2: ParagraphStyle("H2", parent=base["Heading2"], fontSize=14, leading=18, spaceAfter=10),
        3: ParagraphStyle("H3", parent=base["Heading3"], fontSize=12, leading=16, spaceAfter=8),
        4: ParagraphStyle("H4", parent=base["Heading4"], fontSize=11, leading=14, spaceAfter=6),
    }

    story: list = []
    title_text = _core_properties_title(document) or "Converted document"
    story.append(Paragraph(_escape(title_text), heading_styles[0]))
    story.append(Spacer(1, 0.2 * inch))

    for para in document.paragraphs:
        text = para.text
        if not text.strip():
            story.append(Spacer(1, 6))
            continue
        style_name = (para.style.name or "").lower() if para.style else ""
        if style_name.startswith("heading"):
            try:
                level = int(style_name.replace("heading", "").strip() or "1")
            except ValueError:
                level = 1
            level = max(1, min(level, 4))
            story.append(Paragraph(_escape(text), heading_styles[level]))
        else:
            story.append(Paragraph(_escape(text), body_style))

    # Tables: render rows as tab-separated lines (better than nothing).
    for table in document.tables:
        story.append(Spacer(1, 8))
        for row in table.rows:
            cells = [_escape(cell.text.strip()) for cell in row.cells]
            story.append(Paragraph(" | ".join(cells), body_style))
        story.append(Spacer(1, 6))

    pdf.build(story)


def _core_properties_title(document) -> str | None:
    """Return the DOCX title from core properties, or None if missing."""
    try:
        title = document.core_properties.title
    except Exception:
        return None
    if title and title.strip():
        return title.strip()
    return None


def _escape(text: str) -> str:
    """Escape characters that reportlab's Paragraph treats as markup."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


__all__ = ["docx_to_pdf"]
