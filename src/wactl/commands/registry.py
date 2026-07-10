"""Command registry — the plugin core.

Adding a new command means:

1. Create ``src/wactl/commands/<name>.py`` with a class that subclasses
   :class:`wactl.commands.base.Command`, sets ``name`` + ``meta``, and
   implements ``async def run(self, ctx)``.
2. Decorate it with :func:`register`.
3. Import the module from ``src/wactl/commands/__init__.py`` so the
   decorator fires at startup.

Then :func:`get` and :func:`all` return it for the router/dispatcher.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from wactl.models.command import CommandMeta

if TYPE_CHECKING:
    from wactl.commands.base import Command

#: Registry: name → Command class (not instance).
_REGISTRY: dict[str, type[Any]] = {}


class CommandAlreadyRegisteredError(RuntimeError):
    """Raised if two commands share a name. Catches copy-paste mistakes early."""


def register(
    name: str,
    *,
    sync: bool = True,
    requires_media: bool = False,
    description: str = "",
) -> Callable[[type[Any]], type[Any]]:
    """Class decorator: register a Command subclass under ``name``.

    Parameters
    ----------
    name:
        Slash-prefixed command, e.g. ``"/pdf-docx"``.
    sync:
        ``True`` → run inline in Lambda. ``False`` → enqueue to SQS / worker.
    requires_media:
        ``True`` → command must receive an inbound media attachment;
        dispatcher will reject missing media with :class:`UserInputError`.
    description:
        One-line human description, used by ``/help`` (TBD) and docs.
    """

    def _decorator(cls: type[Any]) -> type[Any]:
        if not name.startswith("/"):
            raise ValueError(f"Command name must start with '/', got {name!r}")
        if name in _REGISTRY:
            existing = _REGISTRY[name]
            raise CommandAlreadyRegisteredError(
                f"Command {name!r} already registered to {existing.__name__}; "
                f"cannot also register {cls.__name__}"
            )
        # Attach metadata to the class. ``cls`` is typed loosely (Any) because
        # the base :class:`Command` declares ``name``/``meta`` and subclasses
        # inherit them; but Python's bare ``type`` doesn't know that.
        typed_cls = cast("type[Command]", cls)
        typed_cls.name = name
        typed_cls.meta = CommandMeta(
            name=name,
            sync=sync,
            requires_media=requires_media,
            description=description,
        )
        _REGISTRY[name] = cls
        return cls

    return _decorator


def get(name: str) -> type[Any] | None:
    """Look up a command class by name, or ``None`` if not registered."""
    return _REGISTRY.get(name)


def all() -> dict[str, type[Any]]:
    """Return a copy of the current registry (name → class)."""
    return dict(_REGISTRY)


def names() -> list[str]:
    """Sorted list of all registered command names."""
    return sorted(_REGISTRY.keys())


def clear() -> None:
    """Drop all registrations. Test-only helper."""
    _REGISTRY.clear()


def restore(snapshot: dict[str, type[Any]]) -> None:
    """Replace the live registry with ``snapshot``. Test-only helper.

    Pairs with :func:`clear` to allow test isolation without losing the
    pre-test population of commands (which the worker integration tests
    depend on).
    """
    _REGISTRY.clear()
    _REGISTRY.update(snapshot)


def _snapshot() -> dict[str, type[Command]]:
    """Internal: return the live registry without copying. Test-only."""
    return cast("dict[str, type[Command]]", _REGISTRY)


__all__ = [
    "CommandAlreadyRegisteredError",
    "all",
    "clear",
    "get",
    "names",
    "register",
    "restore",
]
