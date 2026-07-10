"""Fetch a public web page and return its main textual content as Markdown.

Used by :class:`wactl.commands.web_summary.WebSummaryCommand`. The function
takes an injected :class:`httpx.AsyncClient` so tests can use ``respx`` to
mock the network round-trip without touching any framework.

Why a separate module? Commands MUST NOT import ``httpx`` directly. This
file is the single boundary between WACTL commands and the open web.

The result is plain Markdown with HTML tags stripped — perfect input for
the Gemini summarizer.
"""

from __future__ import annotations

from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from markdownify import markdownify

from wactl.exceptions import ExternalAPIError, UserInputError


class FetchedPage:
    """What :func:`fetch_and_extract` returns.

    The Markdown body is the main payload; the URL + title + length are
    useful for the summarizer prompt and for log fields.
    """

    __slots__ = ("bytes_downloaded", "markdown", "title", "url")

    def __init__(self, *, url: str, title: str, markdown: str, bytes_downloaded: int) -> None:
        self.url = url
        self.title = title
        self.markdown = markdown
        self.bytes_downloaded = bytes_downloaded


async def fetch_and_extract(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = 5 * 1024 * 1024,
    timeout: float = 20.0,  # noqa: ASYNC109 — passed to httpx, not asyncio
) -> FetchedPage:
    """Fetch ``url`` and return its main text as Markdown.

    ``max_bytes`` is a safety cap — large pages are truncated at the
    download boundary so we don't blow Lambda's memory budget.
    """
    _validate_url(url)
    try:
        # `timeout` is forwarded to httpx, which respects it natively;
        # ASYNC109 is meant for asyncio.timeout (the context-manager form).
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ExternalAPIError(f"Failed to fetch {url}: {exc}", retryable=True) from exc

    if resp.status_code >= 400:
        raise ExternalAPIError(
            f"Fetch {url} returned HTTP {resp.status_code}",
            retryable=False,
        )
    body = resp.content[:max_bytes]

    soup = BeautifulSoup(body, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    # Drop script/style/nav before converting — they add noise to the prompt.
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.body or soup
    # ``strip`` accepts tags-to-strip list; passing an empty list disables
    # markdownify's own stripping (we already pre-stripped via .strip()).
    markdown = markdownify(str(main), heading_style="ATX", strip=[]).strip()

    return FetchedPage(
        url=url,
        title=title,
        markdown=markdown,
        bytes_downloaded=len(body),
    )


def _validate_url(url: str) -> None:
    """Reject non-HTTP(S) schemes; we don't want file:// or javascript: in prompts."""
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        raise UserInputError(
            f"Unsupported URL scheme: {parsed.scheme!r}",
            user_message="Please send an http(s) URL.",
        )
    if not parsed.netloc:
        raise UserInputError(
            f"URL has no host: {url}",
            user_message="That URL doesn't look right.",
        )


__all__ = ["FetchedPage", "fetch_and_extract"]
