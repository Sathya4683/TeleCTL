"""Tests for :mod:`wactl.commands.github_pr`."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import github_pr as cmd_github_pr
from wactl.exceptions import UserInputError


def _pr_summary():
    from wactl.integrations.github.pr_summary import PullRequestSummary

    return PullRequestSummary(
        url="https://github.com/org/repo/pull/42",
        owner="org",
        repo="repo",
        number=42,
        title="Add new feature",
        body="This PR adds the feature.",
        author="alice",
        head_sha="abc",
        base_sha="def",
        diff="diff --git a/x b/x\n+hello",
        additions=10,
        deletions=2,
        changed_files=3,
    )


@pytest.mark.asyncio
async def test_github_pr_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Fetch → summarize → text reply."""
    called: dict[str, object] = {}

    async def fake_fetch(client, url, *, token):
        called["fetch_url"] = url
        called["token"] = token
        return _pr_summary()

    async def fake_summarize(client, **kwargs):
        called["summarize_kwargs"] = kwargs
        return "This PR introduces a feature with low risk."

    monkeypatch.setattr(
        "wactl.integrations.github.pr_summary.fetch_pr",
        fake_fetch,
    )
    monkeypatch.setattr(
        "wactl.integrations.gemini.text.summarize_github_pr",
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
        args="https://github.com/org/repo/pull/42",
        whatsapp=fake_whatsapp,
        http=MagicMock(name="http"),
        gemini=MagicMock(name="gemini"),
    )
    resp = await cmd_github_pr.GitHubPrCommand().run(ctx)

    assert resp.success
    assert called["fetch_url"] == "https://github.com/org/repo/pull/42"
    assert called["summarize_kwargs"]["title"] == "Add new feature"
    assert called["summarize_kwargs"]["additions"] == 10
    assert "Add new feature" in called["send_kwargs"]["body"]
    assert "low risk" in called["send_kwargs"]["body"]
    assert resp.notes["owner"] == "org"
    assert resp.notes["number"] == 42


@pytest.mark.asyncio
async def test_github_pr_requires_url(fake_whatsapp) -> None:
    ctx = make_context(args="", whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_github_pr.GitHubPrCommand().run(ctx)


@pytest.mark.asyncio
async def test_github_pr_requires_http_and_gemini(fake_whatsapp) -> None:
    ctx = make_context(
        args="https://github.com/org/repo/pull/1",
        whatsapp=fake_whatsapp,
    )
    with pytest.raises(UserInputError):
        await cmd_github_pr.GitHubPrCommand().run(ctx)
