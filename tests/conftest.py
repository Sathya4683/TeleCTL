"""Shared pytest fixtures for WACTL tests.

Use module-level fixtures sparingly — prefer per-test function scopes.
Tests that need moto / respx should declare those fixtures themselves.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def sample_text_webhook() -> dict[str, Any]:
    """Raw text-message webhook payload (with `/pdf-docx` command)."""
    return _load("whatsapp_text_webhook.json")


@pytest.fixture
def sample_image_webhook() -> dict[str, Any]:
    """Raw image-message webhook payload."""
    return _load("whatsapp_image_webhook.json")


@pytest.fixture
def sample_document_webhook() -> dict[str, Any]:
    """Raw document-message webhook payload (PDF attachment)."""
    return _load("whatsapp_document_webhook.json")


@pytest.fixture
def sample_status_webhook() -> dict[str, Any]:
    """Raw status-update webhook payload (no user messages)."""
    return _load("whatsapp_status_webhook.json")


@pytest.fixture
def app_secret() -> str:
    """Deterministic secret for HMAC tests."""
    return "test_app_secret_super_secret_1234"


@pytest.fixture
def raw_body() -> bytes:
    """Sample raw body used in signature tests."""
    return b'{"hello": "world"}'
