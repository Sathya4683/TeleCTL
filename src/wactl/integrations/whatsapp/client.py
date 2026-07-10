"""Async HTTP client for the Meta WhatsApp Cloud API.

Wraps :class:`httpx.AsyncClient` with:
- Bearer-token auth (auto-refreshed from Secrets Manager when needed)
- Retry on 429 with Meta's recommended ``4^x`` backoff
- 5xx retry with exponential backoff
- Conversion of Meta error envelopes into :class:`WhatsAppAPIError`

The client is intentionally a thin wrapper — domain-specific operations
(send_text, send_document, …) live in :mod:`wactl.integrations.whatsapp.messages`.
"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from wactl.constants import META_BACKOFF_BASE_SECONDS, META_BACKOFF_MAX_SECONDS
from wactl.exceptions import WhatsAppAPIError

logger = structlog.get_logger(__name__)

#: HTTP status codes we retry automatically (transient).
RETRY_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


class WhatsAppClient:
    """Async client for the WhatsApp Cloud API.

    Construct one per process (e.g., in the webhook handler at module
    level). The underlying :class:`httpx.AsyncClient` is shared across
    invocations for connection reuse.
    """

    def __init__(
        self,
        *,
        api_version: str,
        phone_number_id: str,
        access_token: str,
        graph_api_base: str = "https://graph.facebook.com",
        timeout: float = 30.0,
        max_retries: int = 3,
        sleep: Any = asyncio.sleep,  # injected for tests
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_version = api_version
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self.graph_api_base = graph_api_base.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    @property
    def base_url(self) -> str:
        return f"{self.graph_api_base}/{self.api_version}"

    @property
    def messages_url(self) -> str:
        return f"{self.base_url}/{self.phone_number_id}/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    async def post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to ``url`` with retry/backoff. Returns the parsed body."""
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(min=1, max=10),
                retry=retry_if_exception_type(_RetryableHTTPError),
                reraise=True,
            ):
                with attempt:
                    return await self._do_post_json(url, body)
        except _RetryableHTTPError as exc:
            raise WhatsAppAPIError(
                f"POST {url} exhausted retries ({exc.status})",
                retryable=True,
                status=exc.status,
            ) from exc
        except RetryError as exc:  # pragma: no cover — defensive
            raise WhatsAppAPIError(
                f"POST {url} exhausted retries",
                retryable=True,
            ) from exc
        # Unreachable — the loop above always either returns or raises.
        raise WhatsAppAPIError("unreachable")  # pragma: no cover

    async def _do_post_json(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._http.post(url, headers=self._headers(), json=body)
        if resp.status_code in RETRY_STATUS_CODES:
            # Honor Retry-After header on 429 if present.
            retry_after = float(resp.headers.get("Retry-After", "0") or "0")
            await self._sleep(retry_after or _meta_backoff_seconds(1))
            raise _RetryableHTTPError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise _meta_error_from_response(resp)
        return cast(dict[str, Any], resp.json())

    async def get_json(self, url: str) -> dict[str, Any]:
        """GET JSON from ``url``. Same retry behavior as POST."""
        try:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(self.max_retries),
                wait=wait_exponential(min=1, max=10),
                retry=retry_if_exception_type(_RetryableHTTPError),
                reraise=True,
            ):
                with attempt:
                    return await self._do_get_json(url)
        except _RetryableHTTPError as exc:
            raise WhatsAppAPIError(
                f"GET {url} exhausted retries ({exc.status})",
                retryable=True,
                status=exc.status,
            ) from exc
        except RetryError as exc:  # pragma: no cover
            raise WhatsAppAPIError(
                f"GET {url} exhausted retries",
                retryable=True,
            ) from exc
        raise WhatsAppAPIError("unreachable")  # pragma: no cover

    async def _do_get_json(self, url: str) -> dict[str, Any]:
        resp = await self._http.get(url, headers=self._headers())
        if resp.status_code in RETRY_STATUS_CODES:
            await self._sleep(_meta_backoff_seconds(1))
            raise _RetryableHTTPError(resp.status_code, resp.text)
        if resp.status_code >= 400:
            raise _meta_error_from_response(resp)
        return cast(dict[str, Any], resp.json())

    async def get_bytes(self, url: str) -> bytes:
        """GET raw bytes from ``url``. No retry on 4xx; retry on 5xx."""
        for attempt in range(self.max_retries):
            resp = await self._http.get(url, headers=self._headers())
            if resp.status_code < 400:
                return resp.content
            if resp.status_code in RETRY_STATUS_CODES and attempt < self.max_retries - 1:
                await self._sleep(_meta_backoff_seconds(attempt + 1))
                continue
            raise _meta_error_from_response(resp)
        raise WhatsAppAPIError("unreachable")  # pragma: no cover

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()


# ─── internal helpers ───────────────────────────────────────────────────


class _RetryableHTTPError(Exception):
    """Internal — raised by the retry helper to trigger a backoff retry."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body[:200]}")


def _meta_backoff_seconds(retry_count: int) -> float:
    """Meta-recommended backoff: ``BASE^(retry_count)`` capped at MAX.

    ``retry_count`` is 1-indexed — first retry waits ``BASE`` seconds.
    """
    exponent = max(0, min(retry_count, 6))
    return float(min(META_BACKOFF_MAX_SECONDS, META_BACKOFF_BASE_SECONDS**exponent))


def _meta_error_from_response(resp: httpx.Response) -> WhatsAppAPIError:
    """Translate a Meta error envelope into :class:`WhatsAppAPIError`."""
    try:
        payload = resp.json()
        err = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = err.get("code")
        message = err.get("message") or f"HTTP {resp.status_code}"
        fbtrace_id = err.get("fbtrace_id")
    except Exception:
        code = None
        message = f"HTTP {resp.status_code}: {resp.text[:200]}"
        fbtrace_id = None

    retryable = code in {130429, 190, 2, 4, 17, 341} or resp.status_code in RETRY_STATUS_CODES
    return WhatsAppAPIError(
        f"WhatsApp API error code={code}: {message} (trace {fbtrace_id})",
        user_message="We couldn't reach WhatsApp. Please try again.",
        retryable=retryable,
        code=code,
        fbtrace_id=fbtrace_id,
        status=resp.status_code,
    )


__all__ = ["RETRY_STATUS_CODES", "WhatsAppClient"]
