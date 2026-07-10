"""Tests for :mod:`wactl.commands.image_compress`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import image_compress as cmd_image_compress
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_image_compress_uses_recompress(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Default recompress path is invoked with quality=75."""
    called: dict[str, object] = {"resize_called": False}

    def fake_recompress(img: bytes, *, quality, format):
        called["recompress_called"] = True
        called["quality"] = quality
        called["format"] = format
        return b"compressed-jpg"

    def fake_rac(*_a, **_kw):
        called["resize_called"] = True
        return b""

    monkeypatch.setattr(
        "wactl.integrations.converters.image_compress.recompress",
        fake_recompress,
    )
    monkeypatch.setattr(
        "wactl.integrations.converters.image_compress.resize_and_compress",
        fake_rac,
    )
    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_image",
        AsyncMock(return_value="wamid.OUT"),
    )
    monkeypatch.setattr(
        "wactl.commands.image_compress.s3.put_object",
        lambda *a, **kw: called.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.image_compress.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/c",
    )

    ctx = make_context(
        media_bytes=b"orig",
        media_mime_type="image/jpeg",
        args="",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_image_compress.ImageCompressCommand().run(ctx)

    assert resp.success
    assert called["recompress_called"] is True
    assert called["resize_called"] is False
    assert called["quality"] == 75
    assert called["format"] == "JPEG"
    assert resp.notes["quality"] == 75


@pytest.mark.asyncio
async def test_image_compress_with_max_width(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """``max=1600`` triggers resize_and_compress path."""
    called: dict[str, object] = {}

    def fake_rac(img: bytes, *, max_width, quality, target_bytes):
        called["rac_called"] = True
        called["max_width"] = max_width
        called["quality"] = quality
        return b"shrunk"

    monkeypatch.setattr(
        "wactl.integrations.converters.image_compress.resize_and_compress",
        fake_rac,
    )
    monkeypatch.setattr(
        "wactl.integrations.converters.image_compress.recompress",
        lambda *_a, **_kw: called.update({"recompress_called": True}) or b"",
    )
    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_image",
        AsyncMock(return_value="wamid.OUT"),
    )
    monkeypatch.setattr(
        "wactl.commands.image_compress.s3.put_object",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "wactl.commands.image_compress.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/x",
    )

    ctx = make_context(
        media_bytes=b"x",
        media_mime_type="image/jpeg",
        args="q=60 max=1600",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_image_compress.ImageCompressCommand().run(ctx)

    assert resp.success
    assert called["rac_called"] is True
    assert called["max_width"] == 1600
    assert called["quality"] == 60


@pytest.mark.asyncio
async def test_image_compress_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_image_compress.ImageCompressCommand().run(ctx)


@pytest.mark.asyncio
async def test_image_compress_rejects_garbage(fake_whatsapp) -> None:
    ctx = make_context(
        media_bytes=b"x",
        media_mime_type="image/jpeg",
        args="not-a-flag",
        whatsapp=fake_whatsapp,
    )
    with pytest.raises(UserInputError):
        await cmd_image_compress.ImageCompressCommand().run(ctx)
