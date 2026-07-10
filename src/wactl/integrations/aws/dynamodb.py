"""DynamoDB helpers — idempotent dedup via conditional write.

The webhook uses :func:`try_claim` to atomically reserve a `wamid...`
message ID. If the claim succeeds, the message is processed; if it fails
(matching item already exists), the message is a duplicate and skipped.

The TTL attribute is named ``expires_at`` and stores epoch seconds. The
table has TTL enabled on this attribute so old entries auto-delete.
"""

from __future__ import annotations

import time
from typing import Any

import boto3
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError

_client: Any = None


def _get_client() -> Any:
    global _client  # noqa: PLW0603 — intentional module-level singleton
    if _client is None:
        _client = boto3.client("dynamodb")
    return _client


def try_claim(
    table: str,
    message_id: str,
    *,
    ttl_seconds: int,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Attempt to claim ``message_id`` for processing.

    Returns ``True`` if the claim succeeded (this caller should process
    the message). Returns ``False`` if the message_id is already present
    (duplicate; caller should drop). Raises :class:`AWSIntegrationError`
    on other DynamoDB errors.
    """
    expires_at = int(time.time()) + ttl_seconds
    item: dict[str, Any] = {
        "pk": {"S": message_id},
        "expires_at": {"N": str(expires_at)},
    }
    if metadata:
        for key, value in metadata.items():
            if isinstance(value, bool):
                item[key] = {"BOOL": value}
            elif isinstance(value, int):
                item[key] = {"N": str(value)}
            elif isinstance(value, str):
                item[key] = {"S": value}

    try:
        _get_client().put_item(
            TableName=table,
            Item=item,
            ConditionExpression="attribute_not_exists(pk)",
        )
        return True
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise AWSIntegrationError(
            f"Failed to claim dedup entry '{message_id}': {exc}",
            retryable=True,
        ) from exc


__all__ = ["try_claim"]
