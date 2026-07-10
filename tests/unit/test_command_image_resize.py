"""Tests for :mod:`wactl.commands.image_resize`."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import image_resize as cmd_image_resize
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_image_resize_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Image bytes → resize → upload → image reply."""
    called: dict[str, object] = {}

    def fake_resize(img: bytes, *, width, height, fit):
        called["resize_input"] = img
        called["width"] = width
        called["height"] = height
        called["fit"] = fit
        return b"resized-png"

    monkeypatch.setattr(
        "wactl.integrations.converters.image_resize.resize",
        fake_resize,
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_image",
        _capture_send,
    )
    monkeypatch.setattr(
        "wactl.commands.image_resize.s3.put_object",
        lambda *a, **kw: called.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.image_resize.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/img",
    )

    ctx = make_context(
        media_bytes=b"original-png",
        media_mime_type="image/png",
        args="800x600",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_image_resize.ImageResizeCommand().run(ctx)

    assert resp.success
    assert resp.message_id == "wamid.OUT"
    assert called["resize_input"] == b"original-png"
    assert called["width"] == 800
    assert called["height"] == 600
    assert called["send_kwargs"]["link"] == "https://signed.example/img"
    assert called["send_kwargs"]["caption"] == "Resized to 800x600"


@pytest.mark.asyncio
async def test_image_resize_accepts_single_dimension(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """``1024`` (width only) parses correctly."""
    called: dict[str, object] = {}

    def fake_resize(img: bytes, *, width, height, fit):
        called["width"] = width
        called["height"] = height
        return b"resized"

    monkeypatch.setattr(
        "wactl.integrations.converters.image_resize.resize",
        fake_resize,
    )
    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_image",
        AsyncMock(return_value="wamid.OUT"),
    )
    monkeypatch.setattr(
        "wactl.commands.image_resize.s3.put_object",
        lambda *a, **kw: None,
    )
    monkeypatch.setattr(
        "wactl.commands.image_resize.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/x",
    )

    ctx = make_context(
        media_bytes=b"x",
        media_mime_type="image/jpeg",
        args="1024",
        whatsapp=fake_whatsapp,
    )
    resp = await cmd_image_resize.ImageResizeCommand().run(ctx)
    assert resp.success
    assert called["width"] == 1024
    assert called["height"] is None


@pytest.mark.asyncio
async def test_image_resize_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_image_resize.ImageResizeCommand().run(ctx)


@pytest.mark.asyncio
async def test_image_resize_requires_size(fake_whatsapp) -> None:
    ctx = make_context(
        media_bytes=b"x",
        media_mime_type="image/png",
        args="",
        whatsapp=fake_whatsapp,
    )
    with pytest.raises(UserInputError):
        await cmd_image_resize.ImageResizeCommand().run(ctx)
