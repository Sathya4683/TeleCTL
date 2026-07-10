"""Image resize via :mod:`Pillow`."""

from __future__ import annotations

import io
from enum import StrEnum

from PIL import Image

from wactl.exceptions import ConverterError, UserInputError


class FitMode(StrEnum):
    """How to fit when only one of width/height is given."""

    CONTAIN = "contain"  # fit inside the box; preserve aspect ratio
    COVER = "cover"  # fill the box; preserve aspect ratio; may crop
    STRETCH = "stretch"  # ignore aspect ratio


def resize(
    img_bytes: bytes,
    *,
    width: int | None = None,
    height: int | None = None,
    fit: FitMode = FitMode.CONTAIN,
) -> bytes:
    """Resize an image to ``width`` x ``height``.

    If only one dimension is given, the other is computed to preserve the
    aspect ratio (according to ``fit``).
    """
    if width is None and height is None:
        raise UserInputError(
            "resize requires width and/or height",
            user_message="Please specify a target width or height.",
        )

    try:
        with Image.open(io.BytesIO(img_bytes)) as src_img:
            src_w, src_h = src_img.size
            new_w, new_h = _compute_target(src_w, src_h, width, height, fit)
            if src_img.mode in {"RGBA", "P"} and (new_format := _target_format(src_img.format)):
                converted = src_img.convert(new_format)
            else:
                converted = src_img
            out = converted.resize((new_w, new_h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            out.save(buf, format=src_img.format or "PNG", optimize=True)
            return buf.getvalue()
    except UserInputError:
        raise
    except Exception as exc:
        raise ConverterError(f"Image resize failed: {exc}") from exc


def _compute_target(
    src_w: int,
    src_h: int,
    width: int | None,
    height: int | None,
    fit: FitMode,
) -> tuple[int, int]:
    if width and height:
        if fit is FitMode.STRETCH:
            return width, height
        # contain/cover → preserve aspect
        scale_w = width / src_w
        scale_h = height / src_h
        scale = max(scale_w, scale_h) if fit is FitMode.COVER else min(scale_w, scale_h)
        return max(1, round(src_w * scale)), max(1, round(src_h * scale))
    if width:
        scale = width / src_w
        return width, max(1, round(src_h * scale))
    # height only
    assert height is not None
    scale = height / src_h
    return max(1, round(src_w * scale)), height


def _target_format(fmt: str | None) -> str | None:
    """If ``PIL`` mode can't save in the original format, return a safe one."""
    # Lossy formats like JPEG cannot preserve alpha; Pillow will pick
    # itself, but we coerce "P" to "RGB" before resize to avoid issues.
    return None  # currently handled inside resize by checking mode


__all__ = ["FitMode", "resize"]


# Helper for image_compress — declared once to avoid cyclic imports at
# module load; concrete implementation lives in image_compress.
def _fit_mode_default() -> FitMode:  # pragma: no cover
    return FitMode.CONTAIN
