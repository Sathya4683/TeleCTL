"""Map incoming message text → command class + args.

The router is intentionally tiny: it parses ``"<command> <args...>"`` into
``(name, args)`` and resolves the name against the registry.

Media-aware commands (those with ``meta.requires_media=True``) still go
through here; the dispatcher is responsible for fetching media bytes
before running them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from wactl.commands.registry import get
from wactl.exceptions import CommandNotFoundError

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class RoutedCommand:
    """The result of :func:`route` — a class plus the args tail."""

    name: str
    cls: Any  # type[Command]; cast at use sites
    args: str


def parse(text: str) -> tuple[str, str]:
    """Split ``text`` into ``(command, rest)``.

    Rules:
    - Leading/trailing whitespace is stripped.
    - First whitespace-separated token is the command (must start with ``/``).
    - The rest of the string is returned verbatim, with surrounding whitespace
      stripped.
    - If the text has no whitespace, ``rest`` is empty.

    >>> parse("/pdf-docx")
    ('/pdf-docx', '')
    >>> parse("/image-resize 800x600")
    ('/image-resize', '800x600')
    """
    text = text.strip()
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    return cmd, rest


def route(text: str) -> RoutedCommand:
    """Resolve ``text`` to a registered command class.

    Raises :class:`CommandNotFoundError` if the command isn't registered.
    """
    name, args = parse(text)
    if not name.startswith("/"):
        raise CommandNotFoundError(f"Message does not start with a command: {text!r}")
    cls = get(name)
    if cls is None:
        raise CommandNotFoundError(f"Unknown command {name!r}")
    return RoutedCommand(name=name, cls=cls, args=args)


__all__ = ["RoutedCommand", "parse", "route"]
