"""Gemini client wrapper.

Initializes :mod:`google.genai` with an API key fetched lazily from
Secrets Manager. Exposes a single :class:`GeminiClient` that hands out
text + TTS helpers.

Note: google-genai's client API is sync-but-async-compatible. We wrap
each call in :func:`asyncio.to_thread` to avoid blocking the worker's
event loop.
"""

from __future__ import annotations

import asyncio
import functools

import structlog
from google import genai
from google.genai import types as genai_types

from wactl.exceptions import ExternalAPIError

logger = structlog.get_logger(__name__)


class GeminiClient:
    """Lazy-initialized Gemini API client."""

    def __init__(
        self,
        api_key: str,
        *,
        text_model: str = "gemini-2.0-flash",
    ) -> None:
        self._api_key = api_key
        self.text_model = text_model
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate_text(
        self,
        prompt: str,
        *,
        system_instruction: str | None = None,
        temperature: float = 0.4,
        max_output_tokens: int = 1024,
    ) -> str:
        """Call Gemini with a single-turn text prompt. Returns the text."""
        config = genai_types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction,
        )

        try:
            response = await asyncio.to_thread(
                functools.partial(
                    self.client.models.generate_content,
                    model=self.text_model,
                    contents=prompt,
                    config=config,
                )
            )
        except Exception as exc:
            raise ExternalAPIError(
                f"Gemini text generation failed: {exc}",
                retryable=True,
            ) from exc

        text = getattr(response, "text", "") or ""
        if not text:
            raise ExternalAPIError("Gemini returned empty text response")
        return text


__all__ = ["GeminiClient"]


# Helper: idempotent model-version lookup for tests.
def default_text_model() -> str:  # pragma: no cover
    return "gemini-2.0-flash"
