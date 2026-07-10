"""Tests for :mod:`wactl.integrations.gemini.text`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from wactl.integrations.gemini.text import (
    LANGUAGE_NAME,
    summarize,
    summarize_github_pr,
    translate,
)


def _fake_client(response: str) -> object:
    """Return an object with an async ``generate_text`` matching the call."""
    fake = AsyncMock()
    fake.generate_text = AsyncMock(return_value=response)
    return fake


@pytest.mark.asyncio
async def test_summarize_returns_response() -> None:
    fake = _fake_client("summary here")
    out = await summarize(fake, "long text")  # type: ignore[arg-type]
    assert out == "summary here"
    fake.generate_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_translate_resolves_language_name() -> None:
    fake = _fake_client("hola")
    await translate(fake, "hello", target_language="es")  # type: ignore[arg-type]
    # First arg to generate_text is the prompt, which should mention "Spanish"
    prompt = fake.generate_text.await_args.args[0]
    assert "Spanish" in prompt
    assert "Translate" in prompt


@pytest.mark.asyncio
async def test_translate_passes_through_unknown_language() -> None:
    fake = _fake_client("...")
    await translate(fake, "hi", target_language="Klingon")  # type: ignore[arg-type]
    prompt = fake.generate_text.await_args.args[0]
    assert "Klingon" in prompt


@pytest.mark.asyncio
async def test_translate_empty_language_raises() -> None:
    fake = _fake_client("...")
    with pytest.raises(ValueError):
        await translate(fake, "x", target_language="")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_summarize_github_pr_truncates_diff() -> None:
    """Long diffs are truncated before being sent to Gemini."""
    fake = _fake_client("ok")
    huge_diff = "x" * 10_000
    await summarize_github_pr(  # type: ignore[arg-type]
        fake,
        title="T",
        body="B",
        diff=huge_diff,
        additions=5,
        deletions=5,
        changed_files=2,
    )
    prompt = fake.generate_text.await_args.args[0]
    assert "(truncated)" in prompt


@pytest.mark.asyncio
async def test_summarize_github_pr_no_truncation_for_short_diff() -> None:
    fake = _fake_client("ok")
    await summarize_github_pr(  # type: ignore[arg-type]
        fake,
        title="T",
        body="B",
        diff="short",
        additions=1,
        deletions=0,
        changed_files=1,
    )
    prompt = fake.generate_text.await_args.args[0]
    assert "(truncated)" not in prompt


def test_language_name_dict_has_common_languages() -> None:
    for code in ("es", "fr", "de", "ja", "zh", "hi", "ar"):
        assert code in LANGUAGE_NAME
