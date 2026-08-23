"""Tests for :mod:`wactl.integrations.telegram.client`."""

from __future__ import annotations

import httpx
import pytest

from wactl.integrations.telegram.client import TelegramApiError, TelegramClient

API_BASE = "https://api.telegram.org"
TOKEN = "123456:ABCDEF"


def _client() -> TelegramClient:
    return TelegramClient(TOKEN, api_base=API_BASE)


def test_client_requires_token() -> None:
    with pytest.raises(ValueError):
        TelegramClient("")


def test_url_and_file_url() -> None:
    client = _client()
    assert client._url("sendMessage") == f"{API_BASE}/bot{TOKEN}/sendMessage"
    assert client.file_url("photos/file_0.jpg") == f"{API_BASE}/file/bot{TOKEN}/photos/file_0.jpg"


@pytest.mark.asyncio
async def test_send_message_happy_path(respx_mock) -> None:
    client = _client()
    respx_mock.post(f"{API_BASE}/bot{TOKEN}/sendMessage").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "result": {"message_id": 1001}},
        )
    )
    resp = await client.send_message(chat_id=42, text="hi")
    assert resp.ok is True
    assert resp.result.message_id == 1001


@pytest.mark.asyncio
async def test_send_message_raises_on_ok_false(respx_mock) -> None:
    client = _client()
    respx_mock.post(f"{API_BASE}/bot{TOKEN}/sendMessage").mock(
        return_value=httpx.Response(
            200,
            json={"ok": False, "error_code": 400, "description": "Bad chat_id"},
        )
    )
    with pytest.raises(TelegramApiError):
        await client.send_message(chat_id=42, text="hi")


@pytest.mark.asyncio
async def test_get_file_returns_file_path(respx_mock) -> None:
    client = _client()
    respx_mock.get(f"{API_BASE}/bot{TOKEN}/getFile").mock(
        return_value=httpx.Response(
            200,
            json={"ok": True, "result": {"file_id": "X", "file_path": "photos/x.jpg"}},
        )
    )
    resp = await client.get_file("X")
    assert resp.result.file_path == "photos/x.jpg"


@pytest.mark.asyncio
async def test_download_file_returns_bytes(respx_mock) -> None:
    client = _client()
    respx_mock.get(f"{API_BASE}/file/bot{TOKEN}/photos/x.jpg").mock(
        return_value=httpx.Response(
            200, content=b"binary", headers={"content-type": "application/octet-stream"}
        )
    )
    data = await client.download_file("photos/x.jpg")
    assert data == b"binary"
