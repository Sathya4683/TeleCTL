"""Tests for :mod:`wactl.commands.web_summary`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import web_summary as cmd_web_summary
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_web_summary_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Fetch → summarize → text reply."""
    called: dict[str, object] = {}

    async def fake_fetch(client, url, **kwargs):
        called["fetch_url"] = url
        called["client"] = client
        from wactl.integrations.web.fetcher import FetchedPage

        return FetchedPage(
            url=url,
            title="Example Title",
            markdown="Some long article body...",
            bytes_downloaded=4096,
        )

    async def fake_summarize(client, body):
        called["summarize_input"] = body
        called["gemini_client"] = client
        return "- bullet one\n- bullet two"

    monkeypatch.setattr(
        "wactl.integrations.web.fetcher.fetch_and_extract",
        fake_fetch,
    )
    monkeypatch.setattr(
        "wactl.integrations.gemini.text.summarize",
        fake_summarize,
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_text",
        _capture_send,
    )

    ctx = make_context(
        args="https://example.com/article",
        whatsapp=fake_whatsapp,
        http=MagicMock(name="http"),
        gemini=MagicMock(name="gemini"),
    )
    resp = await cmd_web_summary.WebSummaryCommand().run(ctx)

    assert resp.success
    assert called["fetch_url"] == "https://example.com/article"
    assert "bullet one" in called["send_kwargs"]["body"]
    assert "Example Title" in called["send_kwargs"]["body"]


@pytest.mark.asyncio
async def test_web_summary_requires_url(fake_whatsapp) -> None:
    ctx = make_context(args="", whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_web_summary.WebSummaryCommand().run(ctx)


@pytest.mark.asyncio
async def test_web_summary_requires_http_and_gemini(fake_whatsapp) -> None:
    ctx = make_context(args="https://example.com", whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_web_summary.WebSummaryCommand().run(ctx)


@pytest.mark.asyncio
async def test_web_summary_rejects_empty_page(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Empty markdown from fetcher → user-facing error."""
    from wactl.integrations.web.fetcher import FetchedPage

    async def fake_fetch(client, url, **kwargs):
        return FetchedPage(url=url, title="", markdown="", bytes_downloaded=0)

    monkeypatch.setattr(
        "wactl.integrations.web.fetcher.fetch_and_extract",
        fake_fetch,
    )

    ctx = make_context(
        args="https://empty.example/",
        whatsapp=fake_whatsapp,
        http=MagicMock(name="http"),
        gemini=MagicMock(name="gemini"),
    )
    with pytest.raises(UserInputError):
        await cmd_web_summary.WebSummaryCommand().run(ctx)
