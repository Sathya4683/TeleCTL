"""AWS Lambda entry point for the WhatsApp webhook.

This file is intentionally tiny — everything lives in
:mod:`wactl.webhook`. The handler is the only stable contract between
API Gateway + this codebase.

Lambda event shape (API Gateway REST proxy):

    {
        "httpMethod": "POST",
        "headers": {"X-Hub-Signature-256": "sha256=...", ...},
        "body": "<raw webhook JSON>",
        "isBase64Encoded": false
    }
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
