"""Tests for :mod:`wactl.integrations.converters.image_compress`."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from wactl.exceptions import ConverterError, UserInputError
from wactl.integrations.converters.image_compress import recompress, resize_and_compress


def _make_jpeg(width: int = 400, height: int = 400) -> bytes:
    img = Image.new("RGB", (width, height), (128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _make_png(width: int = 200, height: int = 200) -> bytes:
    img = Image.new("RGB", (width, height), (10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_recompress_jpeg_smaller() -> None:
    src = _make_jpeg()
    out = recompress(src, quality=30)
    assert len(out) < len(src)


def test_recompress_quality_out_of_range_raises() -> None:
    src = _make_jpeg()
    with pytest.raises(UserInputError):
        recompress(src, quality=0)
    with pytest.raises(UserInputError):
        recompress(src, quality=200)


def test_recompress_returns_bytes() -> None:
    src = _make_jpeg()
    out = recompress(src, quality=50)
    assert isinstance(out, bytes)
    assert len(out) > 0


def test_recompress_converts_png_to_jpeg_when_format_given() -> None:
    src = _make_png()
    out = recompress(src, quality=50, format="JPEG")
    # JPEG output starts with FF D8
    assert out[:2] == b"\xff\xd8"


def test_recompress_rgba_png_to_jpeg() -> None:
    """RGBA → JPEG requires mode conversion to RGB; should not crash.

    Note: when the resulting JPEG is larger than the source PNG (e.g. solid
    color), ``recompress`` returns the original bytes unchanged. We just
    verify the call doesn't raise.
    """
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    # Use a busy image so JPEG beats PNG in size.
    busy = Image.effect_noise((200, 200), 90).convert("RGBA")
    busy_buf = io.BytesIO()
    busy.save(busy_buf, format="PNG")
    out = recompress(busy_buf.getvalue(), quality=50, format="JPEG")
    assert out[:2] == b"\xff\xd8"


def test_recompress_corrupt_raises_converter_error() -> None:
    with pytest.raises(ConverterError):
        recompress(b"not an image", quality=50)


def test_resize_and_compress_no_target() -> None:
    src = _make_jpeg(800, 800)
    out = resize_and_compress(src, max_width=400, quality=50)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size[0] == 400


def test_resize_and_compress_target_bytes_attempted() -> None:
    """When target_bytes is set, the result must respect the width and try to fit."""
    src = _make_jpeg(800, 800)
    out = resize_and_compress(src, max_width=400, quality=50, target_bytes=2000)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size[0] == 400
    # Target may not be hit exactly (binary search is best-effort), but should be small
    assert len(out) < len(src)


def test_format_from_mime_helper() -> None:
    from wactl.integrations.converters.image_compress import _format_from_mime

    assert _format_from_mime("image/jpeg") == "JPEG"
    assert _format_from_mime("image/png") == "PNG"
    assert _format_from_mime("image/webp") == "WEBP"
    assert _format_from_mime("unknown/thing") == "PNG"
