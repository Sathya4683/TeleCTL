"""Inbound media download for the Telegram Bot API.

Two-step process (per https://core.telegram.org/bots/api#getfile):

1. ``GET /getFile?file_id=<ID>`` → returns ``{"file_path": "photos/..."}``
2. ``GET https://api.telegram.org/file/bot<TOKEN>/<file_path>`` → bytes

This module is the single entry-point. Commands (or the dispatcher) call
:func:`download(client, file_id)` and get bytes back.
"""

from __future__ import annotations

import structlog

from wactl.integrations.telegram.client import TelegramApiError, TelegramClient

logger = structlog.get_logger(__name__)


async def download(client: TelegramClient, file_id: str) -> bytes:
    """Download the bytes for an inbound Telegram ``file_id``.

    Raises :class:`TelegramApiError` if either HTTP step fails. Logs both
    the resolved file path and the byte count for traceability.
    """
    if not file_id:
        raise ValueError("download() requires a non-empty file_id")

    file_path_resp = await client.get_file(file_id)
    result = file_path_resp.result
    if result is None or not getattr(result, "file_path", None):
        raise TelegramApiError(
            f"getFile returned no file_path for file_id={file_id!r}"
        )
    file_path = result.file_path

    logger.info("telegram.file.downloading", file_id=file_id, file_path=file_path)
    data = await client.download_file(file_path)
    logger.info("telegram.file.downloaded", file_id=file_id, bytes=len(data))
    return data


__all__ = ["download"]
