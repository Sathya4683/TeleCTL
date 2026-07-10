"""S3 helpers — uploads, downloads, presigned URLs.

The Lambda uses this for "save the result before sending to WhatsApp"
patterns; the worker uses it for the same, plus reading cached inputs.
"""

from __future__ import annotations

from typing import Any, cast

import boto3
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError

_client: Any = None


def _get_client() -> Any:
    global _client  # noqa: PLW0603 — intentional module-level singleton
    if _client is None:
        _client = boto3.client("s3")
    return _client


def put_object(
    bucket: str,
    key: str,
    body: bytes | str,
    *,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> None:
    """Upload ``body`` to ``s3://{bucket}/{key}``."""
    params: dict[str, Any] = {
        "Bucket": bucket,
        "Key": key,
        "Body": body if isinstance(body, bytes) else body.encode("utf-8"),
    }
    if content_type is not None:
        params["ContentType"] = content_type
    if metadata is not None:
        params["Metadata"] = metadata
    try:
        _get_client().put_object(**params)
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to upload s3://{bucket}/{key}: {exc}",
            retryable=True,
        ) from exc


def get_object(bucket: str, key: str) -> bytes:
    """Download ``s3://{bucket}/{key}`` and return the body as bytes."""
    try:
        resp = _get_client().get_object(Bucket=bucket, Key=key)
        return cast(bytes, resp["Body"].read())
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to read s3://{bucket}/{key}: {exc}",
            retryable=True,
        ) from exc


def object_exists(bucket: str, key: str) -> bool:
    """Return True if the object exists, False if not, raise on other errors."""
    try:
        _get_client().head_object(Bucket=bucket, Key=key)
    except ClientError as exc:
        code = exc.response.get("Error", {}).get("Code")
        if code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise AWSIntegrationError(
            f"Failed to head s3://{bucket}/{key}: {exc}",
            retryable=True,
        ) from exc
    return True


def presigned_get_url(bucket: str, key: str, *, expires_in: int = 900) -> str:
    """Return a presigned GET URL valid for ``expires_in`` seconds."""
    return cast(
        str,
        _get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        ),
    )


def make_key(*parts: str) -> str:
    """Build an S3 object key from ``parts``, ensuring no leading slash."""
    return "/".join(p.strip("/") for p in parts if p)


__all__ = [
    "get_object",
    "make_key",
    "object_exists",
    "presigned_get_url",
    "put_object",
]
