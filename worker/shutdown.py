"""SIGTERM / SIGINT handling for graceful worker shutdown.

The systemd unit sends ``SIGTERM`` on stop, ``SIGINT`` is for interactive
Ctrl-C. Both must drain the current SQS message in flight before exiting,
otherwise the message becomes invisible for ``VisibilityTimeout`` seconds
(15 min) — wasteful but recoverable.

The minimal API exposed here is :func:`install`, which hooks into the
:mod:`signal` module once and flips a module-level :data:`_stop_event`.
:class:`wactl.worker.main.Worker` polls the flag at every loop boundary.
"""

from __future__ import annotations

import asyncio
import signal
from typing import NoReturn

from wactl.logging import get_logger

_stop_event: asyncio.Event | None = None
_logger = get_logger(__name__)


def _event() -> asyncio.Event:
    """Lazy-init the event — must be created inside a running loop."""
    global _stop_event  # noqa: PLW0603 — process-singleton flag
    if _stop_event is None:
        _stop_event = asyncio.Event()
    return _stop_event


def install() -> None:
    """Register ``SIGTERM`` and ``SIGINT`` handlers that set the stop event."""
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig)


def _signal_handler(sig: int) -> None:
    """Set the stop flag; log which signal we got."""
    _logger.info("worker.signal_received", signal=sig)
    _event().set()


def is_set() -> bool:
    """True when shutdown has been requested."""
    if _stop_event is None:
        return False
    return _stop_event.is_set()


def reset() -> None:
    """Clear the stop flag — used by tests."""
    if _stop_event is not None:
        _stop_event.clear()


async def wait() -> NoReturn:
    """Block until :func:`is_set` becomes true. Always raises ``Cancelled``."""
    await _event().wait()
    raise asyncio.CancelledError("worker shutdown requested")


__all__ = ["install", "is_set", "reset", "wait"]
