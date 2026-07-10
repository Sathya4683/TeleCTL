"""Tests for :mod:`wactl.integrations.whatsapp.client`."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from wactl.exceptions import WhatsAppAPIError
from wactl.integrations.whatsapp.client import WhatsAppClient


@pytest.fixture
def wa_client() -> WhatsAppClient:
    return WhatsAppClient(
        api_version="v21.0",
        phone_number_id="12345",
        access_token="test-token",
        max_retries=2,
        sleep=lambda _: asyncio.sleep(0),  # no-op
    )


def test_base_url_and_messages_url(wa_client: WhatsAppClient) -> None:
    assert wa_client.base_url == "https://graph.facebook.com/v21.0"
    assert wa_client.messages_url == "https://graph.facebook.com/v21.0/12345/messages"


def test_custom_graph_api_base() -> None:
    c = WhatsAppClient(
        api_version="v20.0",
        phone_number_id="99",
        access_token="t",
        graph_api_base="https://graph.facebook.com/",  # trailing slash
    )
    assert c.base_url == "https://graph.facebook.com/v20.0"


def test_headers_contain_bearer(wa_client: WhatsAppClient) -> None:
    headers = wa_client._headers()
    assert headers["Authorization"] == "Bearer test-token"
    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_post_json_success(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        route = mock.post("/v21.0/12345/messages").mock(
            return_value=httpx.Response(200, json={"messages": [{"id": "wamid-out"}]})
        )
        out = await wa_client.post_json(wa_client.messages_url, {"to": "1", "type": "text"})
        assert out == {"messages": [{"id": "wamid-out"}]}
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_post_json_retry_on_429(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        route = mock.post("/v21.0/12345/messages").mock(
            side_effect=[
                httpx.Response(429, headers={"Retry-After": "0"}, text="rate limit"),
                httpx.Response(200, json={"messages": [{"id": "ok"}]}),
            ]
        )
        out = await wa_client.post_json(wa_client.messages_url, {})
        assert out["messages"][0]["id"] == "ok"
        assert route.call_count == 2


@pytest.mark.asyncio
async def test_post_json_exhausts_retries_raises(wa_client: WhatsAppClient) -> None:
    """max_retries=2 — after 2 429s we should get WhatsAppAPIError."""
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.post("/v21.0/12345/messages").mock(return_value=httpx.Response(429, text="rl"))
        with pytest.raises(WhatsAppAPIError):
            await wa_client.post_json(wa_client.messages_url, {})


@pytest.mark.asyncio
async def test_post_json_4xx_raises_immediately(wa_client: WhatsAppClient) -> None:
    """A 400 should NOT be retried — it surfaces immediately as an error."""
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        route = mock.post("/v21.0/12345/messages").mock(
            return_value=httpx.Response(
                400,
                json={"error": {"code": 100, "message": "Bad param", "fbtrace_id": "abc"}},
            )
        )
        with pytest.raises(WhatsAppAPIError) as exc_info:
            await wa_client.post_json(wa_client.messages_url, {})
        assert exc_info.value.code == 100
        assert exc_info.value.status == 400
        assert route.call_count == 1


@pytest.mark.asyncio
async def test_get_json_success(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.get("/v21.0/some-media-id").mock(return_value=httpx.Response(200, json={"url": "x"}))
        out = await wa_client.get_json("https://graph.facebook.com/v21.0/some-media-id")
        assert out == {"url": "x"}


@pytest.mark.asyncio
async def test_get_bytes_success(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.get("/v21.0/abc").mock(return_value=httpx.Response(200, content=b"BYTES"))
        out = await wa_client.get_bytes("https://graph.facebook.com/v21.0/abc")
        assert out == b"BYTES"


@pytest.mark.asyncio
async def test_meta_backoff_caps_at_max() -> None:
    """Ensure 4^x grows but caps at the configured maximum."""
    from wactl.integrations.whatsapp.client import _meta_backoff_seconds

    # retry_count is 1-indexed: 4^1, 4^2, 4^3, then cap at MAX (60)
    assert _meta_backoff_seconds(1) == 4
    assert _meta_backoff_seconds(2) == 16
    assert _meta_backoff_seconds(3) == 60  # 4^3 = 64, capped at MAX
    assert _meta_backoff_seconds(10) == 60  # still capped


def test_retry_status_codes_constant() -> None:
    from wactl.integrations.whatsapp.client import RETRY_STATUS_CODES

    assert 429 in RETRY_STATUS_CODES
    assert 500 in RETRY_STATUS_CODES
    assert 502 in RETRY_STATUS_CODES
    assert 400 not in RETRY_STATUS_CODES


@pytest.mark.asyncio
async def test_aclose_closes_http_client() -> None:
    """Ensure aclose() closes the underlying httpx client."""
    import httpx as _httpx

    http = _httpx.AsyncClient()
    c = WhatsAppClient(
        api_version="v21.0",
        phone_number_id="1",
        access_token="t",
        http_client=http,
    )
    assert not http.is_closed
    await c.aclose()
    assert http.is_closed
