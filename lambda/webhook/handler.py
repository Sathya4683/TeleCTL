"""AWS Lambda entry point for the Telegram webhook.

This file is intentionally tiny — everything lives in
:mod:`wactl.webhook`. The handler is the only stable contract between
API Gateway + this codebase.

Lambda event shape (API Gateway HTTP API v2 proxy):

    {
        "version": "2.0",
        "requestContext": {"http": {"method": "POST"}, ...},
        "headers": {"x-telegram-bot-api-secret-token": "...", ...},
        "body": "<raw webhook JSON>",
        "isBase64Encoded": false
    }

We accept both the v2 envelope (``requestContext.http.method``) and the
older REST proxy envelope (``httpMethod``) so the handler works with
either API Gateway type.
"""

from __future__ import annotations

from typing import Any

from wactl.webhook import build_deps
from wactl.webhook import handle as wactl_handle

#: Process-wide deps are built once per container; reuse across invocations.
_DEPS: Any | None = None


def _get_deps() -> Any:
    """Lazy init — keeps cold start small, matches Lambda container reuse."""
    global _DEPS  # noqa: PLW0603 — singleton by design
    if _DEPS is None:
        _DEPS = build_deps()
    return _DEPS


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Wrap :func:`wactl.webhook.handle` for the Lambda runtime."""
    # API Gateway HTTP API v2 puts the body in rawBody; map to the shape
    # :func:`wactl.webhook.handle` expects (which already understands
    # both v1 ``body`` and v2 ``body``).
    if "body" not in event and "rawBody" in event:
        event = {**event, "body": event["rawBody"]}
    return wactl_handle(event, context, deps=_get_deps())


__all__ = ["lambda_handler"]
