"""Tests for :mod:`wactl.integrations.gemini.tts`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from wactl.exceptions import ExternalAPIError
from wactl.integrations.gemini import tts as tts_mod
from wactl.integrations.gemini.tts import split_into_chunks, synthesize


def test_empty_text_raises() -> None:
    with pytest.raises(ValueError):
        import asyncio

        asyncio.run(synthesize("", api_key="k"))


# ─── split_into_chunks ──────────────────────────────────────────────────


def test_chunks_empty_returns_empty() -> None:
    assert split_into_chunks("", max_chars=100) == []
    assert split_into_chunks("   \n\n  ", max_chars=100) == []


def test_chunks_under_limit_single_chunk() -> None:
    assert split_into_chunks("hello world", max_chars=100) == ["hello world"]


def test_chunks_paragraph_split() -> None:
    """A two-paragraph input shorter than max_chars stays as a single chunk."""
    text = "First paragraph.\n\nSecond paragraph."
    out = split_into_chunks(text, max_chars=1000)
    assert out == [text]


def test_chunks_respects_max_chars() -> None:
    text = "a. " * 50  # 150 chars
    out = split_into_chunks(text, max_chars=60)
    assert all(len(c) <= 65 for c in out)
    assert len(out) > 1


def test_chunks_handles_long_word() -> None:
    """A word longer than max_chars gets its own chunk (may have trailing period)."""
    text = "x" * 200
    out = split_into_chunks(text, max_chars=50)
    assert len(out) == 1
    assert out[0].rstrip(".") == "x" * 200


def test_chunks_appends_period_if_missing() -> None:
    text = "no period here"
    out = split_into_chunks(text, max_chars=5)
    assert all(c.endswith(".") for c in out if c)


# ─── synthesize (mocked genai) ──────────────────────────────────────────


@pytest.fixture
def patched_genai(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Patch tts_mod.genai to a MagicMock so Client(...).models.generate_content returns our fakes."""
    fake_genai = MagicMock()
    monkeypatch.setattr(tts_mod, "genai", fake_genai)
    return fake_genai


@pytest.mark.asyncio
async def test_synthesize_returns_wav_bytes(patched_genai: MagicMock) -> None:
    fake_part = MagicMock()
    fake_part.inline_data.data = b"FAKE-WAV-DATA"
    fake_candidate = MagicMock()
    fake_candidate.content.parts = [fake_part]
    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]
    patched_genai.Client.return_value.models.generate_content = MagicMock(return_value=fake_response)

    out = await synthesize("hello", api_key="k")
    assert out == b"FAKE-WAV-DATA"


@pytest.mark.asyncio
async def test_synthesize_no_candidates_raises(patched_genai: MagicMock) -> None:
    fake_response = MagicMock()
    fake_response.candidates = []
    patched_genai.Client.return_value.models.generate_content = MagicMock(return_value=fake_response)

    with pytest.raises(ExternalAPIError):
        await synthesize("hi", api_key="k")


@pytest.mark.asyncio
async def test_synthesize_no_audio_in_parts_raises(patched_genai: MagicMock) -> None:
    fake_part = MagicMock()
    fake_part.inline_data = None
    fake_candidate = MagicMock()
    fake_candidate.content.parts = [fake_part]
    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]
    patched_genai.Client.return_value.models.generate_content = MagicMock(return_value=fake_response)

    with pytest.raises(ExternalAPIError):
        await synthesize("hi", api_key="k")


@pytest.mark.asyncio
async def test_synthesize_underlying_error_wrapped(patched_genai: MagicMock) -> None:
    patched_genai.Client.return_value.models.generate_content = MagicMock(side_effect=RuntimeError("boom"))

    with pytest.raises(ExternalAPIError):
        await synthesize("hi", api_key="k")


@pytest.mark.asyncio
async def test_synthesize_picks_first_audio_part(patched_genai: MagicMock) -> None:
    """If the response has multiple parts, the first one with audio wins."""
    fake_text_part = MagicMock()
    fake_text_part.inline_data = None
    fake_audio_part = MagicMock()
    fake_audio_part.inline_data.data = b"GOOD"
    fake_candidate = MagicMock()
    fake_candidate.content.parts = [fake_text_part, fake_audio_part]
    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]
    patched_genai.Client.return_value.models.generate_content = MagicMock(return_value=fake_response)

    out = await synthesize("hi", api_key="k")
    assert out == b"GOOD"


@pytest.mark.asyncio
async def test_synthesize_uses_configured_voice_and_model(patched_genai: MagicMock) -> None:
    fake_part = MagicMock()
    fake_part.inline_data.data = b"x"
    fake_candidate = MagicMock()
    fake_candidate.content.parts = [fake_part]
    fake_response = MagicMock()
    fake_response.candidates = [fake_candidate]
    captured: dict[str, object] = {}

    def capture(**kwargs: object) -> MagicMock:
        captured.update(kwargs)
        return fake_response

    patched_genai.Client.return_value.models.generate_content = MagicMock(side_effect=capture)

    await synthesize("hi", api_key="k", voice="en-US-Studio-O", model="gemini-2.5-pro")
    assert captured["model"] == "gemini-2.5-pro"
