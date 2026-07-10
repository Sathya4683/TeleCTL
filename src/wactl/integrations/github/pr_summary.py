"""GitHub PR fetch — for the ``/github-pr`` command."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from wactl.exceptions import ExternalAPIError, UserInputError

#: Matches a GitHub PR or issue URL like https://github.com/owner/repo/pull/123
PR_URL_RE = re.compile(
    r"^https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:\.diff)?/?$",
)


@dataclass(frozen=True)
class PullRequestSummary:
    """Lightweight PR data — title, body, author, head SHA, diff."""

    url: str
    owner: str
    repo: str
    number: int
    title: str
    body: str
    author: str
    head_sha: str
    base_sha: str
    diff: str  # unified diff (may be very long)
    additions: int
    deletions: int
    changed_files: int


def parse_pr_url(url: str) -> tuple[str, str, int]:
    """Extract (owner, repo, number) from a GitHub PR URL."""
    m = PR_URL_RE.match(url.strip())
    if m is None:
        raise UserInputError(
            f"Not a GitHub PR URL: {url}",
            user_message="Please send a URL like https://github.com/owner/repo/pull/123",
        )
    return m["owner"], m["repo"], int(m["number"])


async def fetch_pr(
    client: httpx.AsyncClient,
    url: str,
    *,
    token: str | None = None,
) -> PullRequestSummary:
    """Fetch PR metadata + unified diff.

    ``token`` (optional) is a fine-grained GitHub PAT for higher rate limits
    and access to private repos. Public repos work without a token (60/hr).
    """
    owner, repo, number = parse_pr_url(url)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    try:
        meta_resp = await client.get(base, headers=headers, timeout=20.0)
    except httpx.HTTPError as exc:
        raise ExternalAPIError(f"GitHub metadata request failed: {exc}") from exc
    if meta_resp.status_code == 404:
        raise UserInputError(
            f"PR {url} not found",
            user_message="We couldn't find that PR. Make sure it's public or your token has access.",
        )
    if meta_resp.status_code == 403 and "rate limit" in meta_resp.text.lower():
        raise ExternalAPIError("GitHub rate limit hit") from None
    if meta_resp.status_code >= 400:
        raise ExternalAPIError(f"GitHub metadata error: HTTP {meta_resp.status_code}")
    meta = meta_resp.json()

    diff_url = meta.get("diff_url")
    diff_text = ""
    if diff_url:
        try:
            # Use raw Accept to avoid markdown wrapping.
            raw_headers = {**headers, "Accept": "application/vnd.github.v3.diff"}
            diff_resp = await client.get(diff_url, headers=raw_headers, timeout=60.0)
            diff_text = diff_resp.text if diff_resp.status_code < 400 else (meta.get("body", "") or "")
        except httpx.HTTPError:
            diff_text = meta.get("body", "") or ""

    return PullRequestSummary(
        url=url,
        owner=owner,
        repo=repo,
        number=number,
        title=str(meta.get("title", "")),
        body=str(meta.get("body", "") or ""),
        author=str(meta.get("user", {}).get("login", "")),
        head_sha=str(meta.get("head", {}).get("sha", "")),
        base_sha=str(meta.get("base", {}).get("sha", "")),
        diff=diff_text,
        additions=int(meta.get("additions", 0) or 0),
        deletions=int(meta.get("deletions", 0) or 0),
        changed_files=int(meta.get("changed_files", 0) or 0),
    )


def _compact_meta(meta: dict[str, Any]) -> dict[str, Any]:
    """Strip large fields for short summaries."""
    return {k: v for k, v in meta.items() if k not in {"body", "diff_url"}}


__all__ = ["PR_URL_RE", "PullRequestSummary", "fetch_pr", "parse_pr_url"]


# Internal helper for tests — keep public surface small.
def _smoke() -> bool:  # pragma: no cover
    return parse_pr_url("https://github.com/org/repo/pull/1") == ("org", "repo", 1)
