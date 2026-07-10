"""WACTL — WhatsApp automation backend.

This package is the single source of truth for both the AWS Lambda webhook
handler and the EC2 worker. Everything is laid out under ``src/wactl/`` so
both consumers install the same wheel.

Layout (high level)::

    src/wactl/
    ├── config.py            # pydantic-settings configuration
    ├── logging.py           # structlog JSON logger
    ├── exceptions.py        # typed exception hierarchy
    ├── constants.py         # defaults and limits
    ├── webhook.py           # entry-point logic shared by Lambda + worker
    ├── router.py            # command name → command class
    ├── dispatcher.py        # sync vs async dispatch
    ├── models/              # pydantic data models
    ├── integrations/        # wrappers around AWS / WhatsApp / etc.
    ├── commands/            # plugin commands (@register decorator)
    └── services/            # multi-step orchestrations

Public re-exports live here so external callers can ``from wactl import X``.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
