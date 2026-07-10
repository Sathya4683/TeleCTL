"""Tests for :mod:`wactl.integrations.converters.image_resize`."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from wactl.exceptions import ConverterError, UserInputError
from wactl.integrations.converters.image_resize import FitMode, resize


def _make_png(width: int, height: int, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_resize_requires_dimensions() -> None:
    png = _make_png(100, 100)
    with pytest.raises(UserInputError):
        resize(png)


def test_resize_to_explicit_dimensions_stretch() -> None:
    png = _make_png(100, 100)
    out = resize(png, width=50, height=50, fit=FitMode.STRETCH)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (50, 50)


def test_resize_width_only_preserves_aspect() -> None:
    png = _make_png(200, 100)
    out = resize(png, width=100)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (100, 50)


def test_resize_height_only_preserves_aspect() -> None:
    png = _make_png(200, 100)
    out = resize(png, height=50)
    with Image.open(io.BytesIO(out)) as img:
        assert img.size == (100, 50)


def test_resize_cover() -> None:
    """Cover scales up by the max factor so the result fills at least one side."""
    png = _make_png(200, 100)
    out = resize(png, width=100, height=100, fit=FitMode.COVER)
    with Image.open(io.BytesIO(out)) as img:
        # scale = max(100/200, 100/100) = 1.0 → output is 200x100.
        # The caller would crop to fit the box; we just resize here.
        assert img.size == (200, 100)


def test_resize_contain() -> None:
    png = _make_png(200, 100)
    out = resize(png, width=100, height=100, fit=FitMode.CONTAIN)
    with Image.open(io.BytesIO(out)) as img:
        # Contain fits inside; aspect preserved
        assert img.size == (100, 50)


def test_resize_corrupt_image_raises_converter_error() -> None:
    with pytest.raises(ConverterError):
        resize(b"not an image", width=10)


def test_resize_rgba_mode() -> None:
    """RGBA input must not crash; JPEG fallback handled by Pillow."""
    img = Image.new("RGBA", (50, 50), (255, 0, 0, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    out = resize(buf.getvalue(), width=25)
    assert out.startswith(b"\x89PNG")


def test_fit_mode_string_values() -> None:
    """FitMode values are stable strings used in command parsing."""
    assert FitMode.CONTAIN.value == "contain"
    assert FitMode.COVER.value == "cover"
    assert FitMode.STRETCH.value == "stretch"
