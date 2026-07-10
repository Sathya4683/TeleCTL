"""Tests for :mod:`wactl.integrations.github.pr_summary`."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from wactl.exceptions import ExternalAPIError, UserInputError
from wactl.integrations.github.pr_summary import PR_URL_RE, fetch_pr, parse_pr_url

# ─── parse_pr_url ───────────────────────────────────────────────────────


def test_parse_pr_url_standard() -> None:
    assert parse_pr_url("https://github.com/owner/repo/pull/123") == ("owner", "repo", 123)


def test_parse_pr_url_trailing_dot_diff() -> None:
    assert parse_pr_url("https://github.com/owner/repo/pull/123.diff") == ("owner", "repo", 123)


def test_parse_pr_url_trailing_slash() -> None:
    assert parse_pr_url("https://github.com/owner/repo/pull/123/") == ("owner", "repo", 123)


def test_parse_pr_url_invalid_raises() -> None:
    with pytest.raises(UserInputError):
        parse_pr_url("https://gitlab.com/foo/bar")


def test_parse_pr_url_with_whitespace_strips() -> None:
    assert parse_pr_url("  https://github.com/owner/repo/pull/1  ") == ("owner", "repo", 1)


def test_parse_pr_url_bad_number_raises() -> None:
    with pytest.raises(UserInputError):
        parse_pr_url("https://github.com/o/r/pull/abc")


def test_pr_url_re_constant() -> None:
    assert PR_URL_RE.pattern.startswith("^https?://")


# ─── fetch_pr (with mocked HTTP) ────────────────────────────────────────


@pytest.fixture
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    """AsyncClient that auto-closes at the end of each test."""
    client = httpx.AsyncClient(timeout=5.0)
    try:
        yield client
    finally:
        await client.aclose()


def _meta_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "title": "x",
        "body": "",
        "user": {"login": "u"},
        "head": {"sha": "h"},
        "base": {"sha": "b"},
        "diff_url": "https://github.com/o/r/pull/1.diff",
        "additions": 0,
        "deletions": 0,
        "changed_files": 0,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_fetch_pr_returns_summary(http_client: httpx.AsyncClient) -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*api\.github\.com/repos/.*").mock(
            return_value=httpx.Response(
                200,
                json=_meta_payload(
                    title="Add feature X",
                    body="Implements X",
                    user={"login": "alice"},
                    additions=12,
                    deletions=4,
                    changed_files=3,
                ),
            )
        )
        mock.get("https://github.com/o/r/pull/1.diff").mock(
            return_value=httpx.Response(200, text="--- a\n+++ b\n@@\n-old\n+new")
        )
        summary = await fetch_pr(http_client, "https://github.com/o/r/pull/1")
        assert summary.title == "Add feature X"
        assert summary.author == "alice"
        assert summary.additions == 12
        assert summary.deletions == 4
        assert summary.changed_files == 3
        assert "old" in summary.diff


@pytest.mark.asyncio
async def test_fetch_pr_with_token(http_client: httpx.AsyncClient) -> None:
    captured: dict[str, str] = {}

    def _callback(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(200, json=_meta_payload())

    with respx.mock(assert_all_called=False) as mock:
        mock.get(url__regex=r".*api\.github\.com/repos/.*").mock(side_effect=_callback)
        mock.get("https://github.com/o/r/pull/1.diff").mock(return_value=httpx.Response(200, text=""))
        await fetch_pr(http_client, "https://github.com/o/r/pull/1", token="tok123")
        assert captured["auth"] == "Bearer tok123"


@pytest.mark.asyncio
async def test_fetch_pr_404_raises_user_input_error(http_client: httpx.AsyncClient) -> None:
    with respx.mock() as mock:
        mock.get(url__regex=r".*api\.github\.com/repos/.*").mock(return_value=httpx.Response(404))
        with pytest.raises(UserInputError):
            await fetch_pr(http_client, "https://github.com/o/r/pull/1")


@pytest.mark.asyncio
async def test_fetch_pr_rate_limit_raises_external(http_client: httpx.AsyncClient) -> None:
    with respx.mock() as mock:
        mock.get(url__regex=r".*api\.github\.com/repos/.*").mock(
            return_value=httpx.Response(403, text="API rate limit exceeded")
        )
        with pytest.raises(ExternalAPIError):
            await fetch_pr(http_client, "https://github.com/o/r/pull/1")


@pytest.mark.asyncio
async def test_fetch_pr_diff_fallback_to_body(http_client: httpx.AsyncClient) -> None:
    """If the diff fetch fails, fall back to the PR body."""
    with respx.mock() as mock:
        mock.get(url__regex=r".*api\.github\.com/repos/.*").mock(
            return_value=httpx.Response(200, json=_meta_payload(body="body text"))
        )
        mock.get("https://github.com/o/r/pull/1.diff").mock(return_value=httpx.Response(500))
        summary = await fetch_pr(http_client, "https://github.com/o/r/pull/1")
        assert summary.diff == "body text"
