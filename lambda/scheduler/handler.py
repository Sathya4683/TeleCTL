"""EventBridge-scheduled Lambda — placeholder for daily cleanup tasks.

Currently a no-op; will house optional DynamoDB TTL sweeps and
S3 lifecycle prune jobs once we have the data to back them.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def lambda_handler(event: dict[str, object], context: object) -> dict[str, object]:
    """Run any periodic maintenance work."""
    logger.info("scheduler.tick", event=str(event)[:200])
    return {"statusCode": 200, "body": "ok"}


__all__ = ["lambda_handler"]
