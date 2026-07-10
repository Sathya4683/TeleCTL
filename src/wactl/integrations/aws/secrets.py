"""AWS Secrets Manager integration with TTL caching.

Used to fetch sensitive configuration values (WhatsApp access token, app
secret, verify token, Gemini API key) at runtime. Cache the value in
memory for ``cache_ttl_seconds`` to avoid per-invocation API costs and
latency. The cache is per-process; Lambda and worker each have their own.
"""

from __future__ import annotations

import time
from threading import Lock
from typing import Any, cast

import boto3
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError

# Module-level singleton (created lazily on first use).
_client = None

# In-process cache: name -> (value, expires_at_epoch_seconds)
_cache: dict[str, tuple[str, float]] = {}
_cache_lock = Lock()

DEFAULT_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_client() -> Any:
    global _client  # noqa: PLW0603 — intentional module-level singleton
    if _client is None:
        _client = boto3.client("secretsmanager")
    return _client


def get_secret(name: str, *, cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS) -> str:
    """Return the string value of secret ``name``.

    Raises :class:`AWSIntegrationError` if the secret cannot be fetched.
    """
    now = time.monotonic()
    with _cache_lock:
        cached = _cache.get(name)
        if cached is not None and cached[1] > now:
            return cached[0]

    try:
        client = _get_client()
        resp = client.get_secret_value(SecretId=name)
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to fetch secret '{name}': {exc}",
            retryable=True,
        ) from exc

    value = cast(str | None, resp.get("SecretString"))
    if value is None:
        raise AWSIntegrationError(
            f"Secret '{name}' has no SecretString",
        )

    with _cache_lock:
        _cache[name] = (value, now + cache_ttl)
    return value


def clear_cache() -> None:
    """Drop all cached secrets. Test-only helper."""
    with _cache_lock:
        _cache.clear()


__all__ = ["DEFAULT_CACHE_TTL_SECONDS", "clear_cache", "get_secret"]
