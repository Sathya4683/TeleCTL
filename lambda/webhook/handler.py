"""AWS Lambda entry point for the Telegram webhook.

This file is intentionally tiny — everything lives in
:mod:`wactl.webhook`. The handler is the only stable contract between
API Gateway + this codebase.

Lambda event shape (API Gateway HTTP API v2 proxy, ``payload_format_version = "2.0"``):

    {
        "version": "2.0",
        "requestContext": {"http": {"method": "POST"}, ...},
        "headers": {"x-telegram-bot-api-secret-token": "...", ...},
        "body": "<raw webhook JSON>",
        "isBase64Encoded": false
    }

For HTTP API v2 the body always arrives in ``event["body"]`` (string for
JSON payloads, base64-encoded only if the content type is binary).
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
    return wactl_handle(event, context, deps=_get_deps())


__all__ = ["lambda_handler"]
