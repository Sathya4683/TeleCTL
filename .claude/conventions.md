---
name: conventions
description: Code style and rules for WACTL — import order, command layer purity, logging, error handling
metadata:
  type: project
---

# Coding conventions

## Import order (ruff `I`)

Strictly: stdlib → third-party → `wactl.*` → local.

```python
# stdlib
import json
from pathlib import Path

# third-party
import httpx
import structlog

# wactl
from wactl.config import settings
from wactl.integrations.aws.s3 import S3Client

# local (only inside src/wactl/...)
from .registry import get
```

## Command layer purity

Commands in `src/wactl/commands/` MUST NOT import:
- `httpx`, `requests`, `urllib` — use `ctx.whatsapp` or other integrations.
- `boto3` — use integrations in `wactl.integrations.aws.*`.
- Any direct Graph API / S3 / SQS / DynamoDB client.

They SHOULD only import:
- `wactl.commands.base` (for the `Command` base + `CommandContext`).
- `wactl.integrations.*` (which provide all I/O).
- `wactl.models.*` (typed data).

A ruff lint check (`wactl.lint.no_direct_aws_http`) enforces this. Tests
should `grep`-the source to confirm.

## Logging

Use `structlog` everywhere. Never `print`. Never `logging.getLogger(...)`
directly — use `wactl.logging.get_logger(name)`.

Logs are JSON. Bind context once per scope:

```python
from wactl.logging import bind_context

with bind_context(job_id=job.id, command="pdf-docx", user_phone=user.phone):
    logger.info("starting conversion")
```

The bound fields are merged into every subsequent log line.

## Configuration

All env reads happen via `wactl.config.settings` (`pydantic-settings`).
Never call `os.getenv(...)` in application code. Never reach into
`os.environ` — only `settings` does.

If you need a new env var, add it to `Settings` in
`src/wactl/config.py` AND document it in `.env.example`.

## Error handling

Every raised application error extends `WactlError`
(`src/wactl/exceptions.py`). Never raise bare `Exception` from app code.

Integrations translate AWS / Meta errors into typed exceptions at the
boundary (e.g., `botocore.exceptions.ClientError` →
`AWSIntegrationError`). The command layer never sees boto-specific
exceptions.

For expected user errors (e.g., bad file type), raise a typed
`UserInputError` subclass — the dispatcher catches it and replies with a
helpful WhatsApp message instead of a 500.

## Async vs sync

Command `run()` methods are `async`. The webhook handler is `async`.
Integrations that do I/O are `async`; pure-Python converters (Pillow,
pypdf, pdf2docx, pymupdf) are sync but called from inside `async`
methods via `await asyncio.to_thread(...)` to avoid blocking the event
loop. Image and PDF operations are CPU-bound and would otherwise stall
other invocations on the same worker.

## AWS clients

Module-level singletons. Don't construct per call:

```python
# ✅ good
s3 = boto3.client("s3")  # at module top

# ❌ bad
def get_object(key):
    return boto3.client("s3").get_object(Bucket=BUCKET, Key=key)
```

The AWS SDK and connections are designed to be reused.

## Testing

- `pytest` with `pytest-asyncio` (`asyncio_mode = "auto"`).
- Mock external I/O: `respx` for HTTP, `moto` for AWS.
- Each command has a `tests/unit/test_<cmd>.py` with at least one happy
  path and one error path. Mock every integration it calls — never hit
  the real API in unit tests.
- Integration tests live under `tests/integration/` and may exercise the
  full `wactl.webhook.handle()` path with mocked integrations.

## Type hints

Strict mypy. Every public function has full annotations. Use
`from __future__ import annotations` in every module.

Pydantic models are `frozen=True` for value objects, mutable for
aggregates.

## Files

- Aim for ≤200 lines per module. If a module exceeds that, split.
- One class / one purpose per file where practical.
- `__init__.py` re-exports the public surface of its package.

---

Related: [[architecture]], [[repo-structure]], [[commands]]