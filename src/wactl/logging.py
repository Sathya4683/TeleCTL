"""Structured JSON logging via :mod:`structlog`.

Configures a single stdout-bound processor chain that:

1. Adds ISO-8601 timestamps.
2. Coerces exceptions to ``{exception, exception_type}``.
3. Merges bound context (``job_id``, ``command``, ``user_phone``, …).

Application code uses ``get_logger(__name__)`` and calls it like the stdlib
logger::

    from wactl.logging import bind_context, get_logger

    logger = get_logger(__name__)

    with bind_context(job_id="...", command="pdf-docx", user_phone="..."):
        logger.info("starting", file_size=12345)

Every log line is one JSON object per line (suitable for CloudWatch).
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import structlog

from wactl.config import settings

__all__ = [
    "bind_context",
    "configure_logging",
    "get_logger",
    "reset_context",
]


_configured = False


def configure_logging() -> None:
    """Idempotently install structlog + stdlib logging config.

    Safe to call multiple times. Idempotent.
    """
    global _configured  # noqa: PLW0603 — idempotent module-level flag
    if _configured:
        return

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # stdlib logging — CloudWatch captures these too.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
        force=True,
    )

    # Quiet noisy libraries that ship at DEBUG.
    for noisy in ("botocore", "boto3", "s3transfer", "urllib3", "httpx", "asyncio"):
        logging.getLogger(noisy).setLevel(max(level, logging.WARNING))

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )

    _configured = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a bound logger.

    If logging hasn't been configured yet, configure it on first use.
    """
    configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger


@contextmanager
def bind_context(**kwargs: Any) -> Iterator[dict[str, Any]]:
    """Bind ``kwargs`` as log context for the duration of the block.

    Backed by :mod:`structlog.contextvars` so it propagates across
    :func:`asyncio.to_thread` boundaries.
    """
    if not _configured:
        configure_logging()
    structlog.contextvars.bind_contextvars(**kwargs)
    try:
        yield kwargs
    finally:
        # Pop only the keys we set, in case the caller added others.
        for key in kwargs:
            structlog.contextvars.unbind_contextvars(key)


def reset_context() -> None:
    """Clear all bound context — call at start of each invocation."""
    structlog.contextvars.clear_contextvars()


# Configure eagerly on import; the stdlib root logger is configured too.
# (Tests can call configure_logging again to re-pin LOG_LEVEL.)
configure_logging()
