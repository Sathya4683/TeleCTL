"""Inbound media — resolve URL and download bytes.

Outbound media uploads are handled by uploading to S3 and sending a
presigned link to WhatsApp (handled in commands, not here). This module
deals with **inbound** media only.

The two-step process (resolve URL, then GET bytes) is required because
Meta only returns a media_id on the webhook. The URL is **temporary**
(expires after ~5 minutes), so download immediately.
"""

from __future__ import annotations

from wactl.integrations.whatsapp.client import WhatsAppClient


async def resolve_url(
    client: WhatsAppClient,
    media_id: str,
    *,
    phone_number_id: str | None = None,
) -> str:
    """Return the temporary URL for ``media_id``."""
    url = f"{client.base_url}/{media_id}"
    if phone_number_id:
        url += f"?phone_number_id={phone_number_id}"
    payload = await client.get_json(url)
    return str(payload["url"])


async def download(
    client: WhatsAppClient,
    media_id: str,
    *,
    phone_number_id: str | None = None,
) -> bytes:
    """Resolve and download ``media_id`` in one call."""
    download_url = await resolve_url(client, media_id, phone_number_id=phone_number_id)
    return await client.get_bytes(download_url)


__all__ = ["download", "resolve_url"]
