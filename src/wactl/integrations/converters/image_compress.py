"""Image compression via :mod:`Pillow`.

Two strategies:

- ``recompress``: re-encode the image at a lower quality. Works for JPEG.
- ``resize_then_recompress``: downscale first, then re-encode. Useful for
  hitting a target byte size on a budget.

If the output is larger than the input (rare, but e.g. PNG-to-PNG with
no quality knob), the original bytes are returned unchanged.
"""

from __future__ import annotations

import io

from PIL import Image

from wactl.exceptions import ConverterError, UserInputError
from wactl.integrations.converters.image_resize import resize


def recompress(
    img_bytes: bytes,
    *,
    quality: int = 75,
    format: str | None = None,
) -> bytes:
    """Re-encode ``img_bytes`` at lower quality.

    ``quality`` is 1..95; default 75. If ``format`` is given (e.g.
    ``"JPEG"``), convert to that format. Otherwise keep the original.
    """
    if not 1 <= quality <= 95:
        raise UserInputError(
            f"quality must be in [1, 95], got {quality}",
            user_message="Quality must be between 1 and 95.",
        )

    try:
        with Image.open(io.BytesIO(img_bytes)) as src_img:
            target_fmt = (format or src_img.format or "JPEG").upper()
            # RGB is required for JPEG; for PNG it doesn't matter.
            out_img = src_img.convert("RGB") if target_fmt == "JPEG" and src_img.mode != "RGB" else src_img
            buf = io.BytesIO()
            save_kwargs: dict[str, object] = {"optimize": True}
            if target_fmt == "JPEG":
                save_kwargs["quality"] = quality
            out_img.save(buf, format=target_fmt, **save_kwargs)
            out = buf.getvalue()
    except UserInputError:
        raise
    except Exception as exc:
        raise ConverterError(f"Image compression failed: {exc}") from exc

    # If the new file is bigger, keep the original (don't pessimize).
    return out if len(out) < len(img_bytes) else img_bytes


def resize_and_compress(
    img_bytes: bytes,
    *,
    max_width: int,
    quality: int = 75,
    target_bytes: int | None = None,
) -> bytes:
    """Resize to ``max_width`` and compress, optionally targeting a byte budget."""
    resized = resize(img_bytes, width=max_width)
    if target_bytes is None:
        return recompress(resized, quality=quality)
    # Binary-search quality to hit target_bytes (best-effort).
    low, high = 10, 95
    best = recompress(resized, quality=quality)
    while low <= high:
        mid = (low + high) // 2
        candidate = recompress(resized, quality=mid)
        if len(candidate) <= target_bytes:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return best


__all__ = ["recompress", "resize_and_compress"]


# Helper for tests — avoid Pillow auto-detection surprises.
def _format_from_mime(mime: str) -> str:
    """Convert a MIME type to a Pillow format name."""
    return {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}.get(mime, "PNG")
