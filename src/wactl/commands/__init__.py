"""Command registry — import each command module to fire its @register decorator.

The order of imports below defines the order commands appear in ``/help``.

**Lazy-loading note:** ``pdf_audio`` is intentionally NOT imported here.
It pulls in ``google-genai`` + ``pymupdf`` + ``pydub`` at import time, none
of which are needed by the webhook Lambda (which only serves sync
commands). The EC2 worker imports ``pdf_audio`` directly:

    from wactl.commands.pdf_audio import PdfAudioCommand

To enable a previously-disabled command (e.g. ``merge_pdf``), add its
import back here AND make sure its ``@register`` decorator still points to
the correct name.
"""

from __future__ import annotations

from wactl.commands import (  # noqa: F401 — side-effect: registers commands
    docx_pdf,
    help,
    image_compress,
    image_resize,
    pdf_docx,
)
from wactl.commands.registry import all as all_commands
from wactl.commands.registry import clear as clear_registry
from wactl.commands.registry import get as get_command
from wactl.commands.registry import register

__all__ = [
    "all_commands",
    "clear_registry",
    "get_command",
    "register",
]
