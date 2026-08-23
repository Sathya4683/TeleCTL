"""Command registry — import each command module to fire its @register decorator.

The order of imports below defines the order commands appear in ``/help``.
To enable a previously-disabled command (e.g. ``merge_pdf``), add its import
back here AND make sure its ``@register`` decorator still points to the
correct name. The other command modules stay on disk (and stay in their
existing unit tests) — only the import is removed, so re-enabling is a
one-line change.
"""

from __future__ import annotations

from wactl.commands import (  # noqa: F401 — side-effect: registers commands
    help,
    image_compress,
    image_resize,
    pdf_audio,
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
