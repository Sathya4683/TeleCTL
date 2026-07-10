"""Shared constants — defaults, limits, magic strings.

Anything that's referenced by name from more than one module lives here.
Kept tiny on purpose. If something grows, it graduates to its own module.
"""

from __future__ import annotations

# ─── Graph API ──────────────────────────────────────────────────────────

#: Stable WhatsApp Cloud API version. Bump in lockstep with Meta's
#: deprecation schedule. See https://developers.facebook.com/docs/graph-api/changelog
DEFAULT_API_VERSION = "v21.0"

#: Base URL for all outbound WhatsApp calls (vary the version by env).
GRAPH_API_BASE = "https://graph.facebook.com"

#: Maximum inbound media size accepted by WhatsApp (per message, in bytes).
#: Upstream returns error code 131052 if exceeded.
MAX_INBOUND_MEDIA_BYTES = 100 * 1024 * 1024  # 100 MB

#: Maximum inbound webhook payload size accepted by Meta (whole POST body).
MAX_WEBHOOK_BODY_BYTES = 3 * 1024 * 1024  # 3 MB

# ─── Retry / backoff ────────────────────────────────────────────────────

#: Meta recommends ``4^x seconds`` backoff on 429 (rate limit).
META_BACKOFF_BASE_SECONDS = 4

#: Cap so we never sleep "too long" on a hot loop.
META_BACKOFF_MAX_SECONDS = 60

# ─── Dedup ──────────────────────────────────────────────────────────────

#: Default TTL for the dynamodb dedup entries. Matches Meta's
#: "retried up to 7 days" window.
DEFAULT_DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days

# ─── SQS ────────────────────────────────────────────────────────────────

#: Default visibility timeout for the jobs queue. 15 min = max Lambda
#: timeout, ensures the worker has head-room even on slow jobs.
DEFAULT_VISIBILITY_TIMEOUT_SECONDS = 900

#: Maximum number of times a job is delivered before going to DLQ.
DEFAULT_MAX_RECEIVE_COUNT = 5

# ─── Media bucket lifecycle ────────────────────────────────────────────

#: Expire media objects after 24 hours (we only need them while a job is in
#: flight). Picked conservatively; tune per-command if needed.
MEDIA_OBJECT_TTL_SECONDS = 24 * 60 * 60


# ─── Supported MIME types for outbound operations ──────────────────────
# Incoming types come from the webhook; outbound types must match the
# converter's output. Listed as frozensets so they can be matched cheaply.

IMAGE_MIME_TYPES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/gif",
    }
)

DOCUMENT_MIME_TYPES: frozenset[str] = frozenset(
    {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

AUDIO_MIME_TYPES: frozenset[str] = frozenset(
    {
        "audio/ogg",
        "audio/ogg; codecs=opus",
        "audio/mpeg",
        "audio/mp4",
        "audio/wav",
    }
)
