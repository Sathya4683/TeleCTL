"""Tests for :mod:`wactl.integrations.whatsapp.media`."""

from __future__ import annotations

import httpx
import pytest
import respx

from wactl.integrations.whatsapp.client import WhatsAppClient
from wactl.integrations.whatsapp.media import download, resolve_url


@pytest.fixture
def wa_client() -> WhatsAppClient:
    return WhatsAppClient(
        api_version="v21.0",
        phone_number_id="12345",
        access_token="test-token",
    )


@pytest.mark.asyncio
async def test_resolve_url_returns_url_from_envelope(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.get("/v21.0/mid-1").mock(return_value=httpx.Response(200, json={"url": "https://look.here/x"}))
        url = await resolve_url(wa_client, "mid-1")
        assert url == "https://look.here/x"


@pytest.mark.asyncio
async def test_resolve_url_with_phone_number_id(wa_client: WhatsAppClient) -> None:
    captured: dict[str, str] = {}

    def _callback(request: httpx.Request) -> httpx.Response:
        captured["path"] = str(request.url)
        return httpx.Response(200, json={"url": "https://look.here/x"})

    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.get("/v21.0/mid-2").mock(side_effect=_callback)
        url = await resolve_url(wa_client, "mid-2", phone_number_id="99")
        assert url == "https://look.here/x"
        assert "phone_number_id=99" in captured["path"]


@pytest.mark.asyncio
async def test_download_resolves_then_fetches(wa_client: WhatsAppClient) -> None:
    with respx.mock(base_url="https://graph.facebook.com") as mock:
        mock.get("/v21.0/mid-3").mock(return_value=httpx.Response(200, json={"url": "https://look.here/x"}))
        mock.get("https://look.here/x").mock(return_value=httpx.Response(200, content=b"BINARY"))
        out = await download(wa_client, "mid-3")
        assert out == b"BINARY"
