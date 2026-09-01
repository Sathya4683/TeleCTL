"""Tests for :mod:`wactl.integrations.telegram.media`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wactl.integrations.telegram.client import TelegramApiError
from wactl.integrations.telegram.media import download


@pytest.mark.asyncio
async def test_download_two_step_flow() -> None:
    """``download`` calls getFile, then downloads bytes from file_url."""
    client = MagicMock()
    client.get_file = AsyncMock(
        return_value=MagicMock(
            result=MagicMock(file_path="photos/file_0.jpg"),
        )
    )
    client.download_file = AsyncMock(return_value=b"image-bytes")

    data = await download(client, "AgAC123")

    assert data == b"image-bytes"
    client.get_file.assert_awaited_once_with("AgAC123")
    client.download_file.assert_awaited_once_with("photos/file_0.jpg")


@pytest.mark.asyncio
async def test_download_missing_file_path_raises() -> None:
    client = MagicMock()
    client.get_file = AsyncMock(
        return_value=MagicMock(result=MagicMock(file_path=None)),
    )
    with pytest.raises(TelegramApiError):
        await download(client, "X")


@pytest.mark.asyncio
async def test_download_empty_file_id_raises() -> None:
    client = MagicMock()
    with pytest.raises(ValueError):
        await download(client, "")
