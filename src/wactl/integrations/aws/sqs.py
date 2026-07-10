"""SQS helpers — typed enqueue, typed dequeue, delete.

Used by the webhook handler (enqueue) and the worker (dequeue/delete).
"""

from __future__ import annotations

import json
from typing import Any

import boto3
from botocore.exceptions import ClientError

from wactl.exceptions import AWSIntegrationError

_client: Any = None


def _get_client() -> Any:
    global _client  # noqa: PLW0603 — intentional module-level singleton
    if _client is None:
        _client = boto3.client("sqs")
    return _client


def send_message(
    queue_url: str,
    payload: dict[str, Any],
    *,
    message_group_id: str | None = None,
    delay_seconds: int = 0,
) -> str:
    """Send a JSON-serialized payload to ``queue_url``. Returns the MessageId."""
    params: dict[str, Any] = {
        "QueueUrl": queue_url,
        "MessageBody": json.dumps(payload, separators=(",", ":"), default=str),
        "DelaySeconds": delay_seconds,
    }
    # Only FIFO queues accept MessageGroupId; we pass None otherwise to
    # avoid sending an empty string that AWS rejects.
    if message_group_id is not None:
        params["MessageGroupId"] = message_group_id
    try:
        resp = _get_client().send_message(**params)
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to send SQS message: {exc}",
            retryable=True,
        ) from exc
    return str(resp["MessageId"])


def receive_message(
    queue_url: str,
    *,
    max_messages: int = 10,
    wait_seconds: int = 20,
    visibility_timeout: int = 900,
) -> list[dict[str, Any]]:
    """Long-poll up to ``max_messages`` messages. Returns parsed bodies."""
    try:
        resp = _get_client().receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=max_messages,
            WaitTimeSeconds=wait_seconds,
            VisibilityTimeout=visibility_timeout,
            MessageAttributeNames=["All"],
            AttributeNames=["All"],
        )
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to receive SQS messages: {exc}",
            retryable=True,
        ) from exc

    out: list[dict[str, Any]] = []
    for msg in resp.get("Messages", []):
        body = msg.get("Body", "")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            # Treat as raw; caller will surface the error.
            parsed = {"_raw": body}
        parsed["_receipt_handle"] = msg["ReceiptHandle"]
        parsed["_message_id"] = msg["MessageId"]
        out.append(parsed)
    return out


def delete_message(queue_url: str, receipt_handle: str) -> None:
    """Delete a previously-received message from the queue."""
    try:
        _get_client().delete_message(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
        )
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to delete SQS message: {exc}",
            retryable=True,
        ) from exc


def get_queue_attributes(queue_url: str) -> dict[str, str]:
    """Return all queue attributes (visible messages, DLQ depth, etc.)."""
    try:
        resp = _get_client().get_queue_attributes(
            QueueUrl=queue_url,
            AttributeNames=["All"],
        )
    except ClientError as exc:
        raise AWSIntegrationError(
            f"Failed to read SQS queue attributes: {exc}",
            retryable=True,
        ) from exc
    return {k: str(v) for k, v in resp.get("Attributes", {}).items()}


__all__ = [
    "delete_message",
    "get_queue_attributes",
    "receive_message",
    "send_message",
]
