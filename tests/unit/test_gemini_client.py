"""Tests for :mod:`wactl.integrations.gemini.client`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from wactl.exceptions import ExternalAPIError
from wactl.integrations.gemini.client import GeminiClient


@pytest.fixture
def client() -> GeminiClient:
    """Return a GeminiClient with an injected fake _client."""
    c = GeminiClient(api_key="test-api-key", text_model="gemini-test")
    c._client = MagicMock()  # type: ignore[assignment]
    return c


@pytest.mark.asyncio
async def test_generate_text_returns_text(client: GeminiClient) -> None:
    """Successful call returns the response text."""
    fake_response = MagicMock()
    fake_response.text = "hello world"
    client._client.models.generate_content = MagicMock(return_value=fake_response)  # type: ignore[attr-defined]

    out = await client.generate_text("hi")
    assert out == "hello world"
    client._client.models.generate_content.assert_called_once()  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_generate_text_with_system_instruction(client: GeminiClient) -> None:
    """system_instruction is passed through to the config."""
    fake_response = MagicMock()
    fake_response.text = "ok"
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return fake_response

    client._client.models.generate_content = MagicMock(side_effect=capture)  # type: ignore[attr-defined]

    await client.generate_text("p", system_instruction="be brief")
    config = captured["config"]
    assert config.system_instruction == "be brief"


@pytest.mark.asyncio
async def test_generate_text_empty_response_raises(client: GeminiClient) -> None:
    fake_response = MagicMock()
    fake_response.text = ""
    client._client.models.generate_content = MagicMock(return_value=fake_response)  # type: ignore[attr-defined]

    with pytest.raises(ExternalAPIError):
        await client.generate_text("p")


@pytest.mark.asyncio
async def test_generate_text_underlying_error_wrapped(client: GeminiClient) -> None:
    """An exception from genai is translated to ExternalAPIError."""
    client._client.models.generate_content = MagicMock(side_effect=RuntimeError("kaboom"))  # type: ignore[attr-defined]

    with pytest.raises(ExternalAPIError):
        await client.generate_text("p")


@pytest.mark.asyncio
async def test_generate_text_uses_text_model(client: GeminiClient) -> None:
    """The configured text_model is passed to generate_content."""
    fake_response = MagicMock()
    fake_response.text = "x"
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return fake_response

    client._client.models.generate_content = MagicMock(side_effect=capture)  # type: ignore[attr-defined]

    await client.generate_text("p")
    assert captured["model"] == "gemini-test"
