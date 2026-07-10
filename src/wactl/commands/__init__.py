"""Command registry — import each command module to fire its @register decorator.

The order of imports below defines the order commands appear in ``/help``.
New commands are added by appending an import here.
"""

from __future__ import annotations

from wactl.commands import (  # noqa: F401 — side-effect: registers commands
    github_pr,
    image_compress,
    image_resize,
    merge_pdf,
    pdf_audio,
    pdf_docx,
    split_pdf,
    translate,
    web_summary,
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
