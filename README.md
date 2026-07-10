# WACTL — WhatsApp Automation Platform

A production-grade WhatsApp Cloud API automation platform built on AWS Lambda,
API Gateway, SQS, DynamoDB, and an EC2 worker. Users DM a WhatsApp Business
number with slash-commands (`/pdf-docx`, `/image-resize`, `/web-summary`, …)
and receive processed results directly in the chat.

## Why it exists

This is a portfolio project that demonstrates:

- **Plugin architecture** — adding a new command is one file + one decorator.
- **Clean separation of concerns** — commands orchestrate, integrations wrap.
- **Production AWS patterns** — HMAC verification, DynamoDB TTL dedup, IAM
  least-privilege, GitHub OIDC, structured logging, graceful worker shutdown.
- **Infrastructure as code** — every AWS resource is Terraform-managed.

## Quickstart

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install deps
uv sync

# Run tests
uv run pytest

# Lint + type check
uv run ruff check src tests
uv run mypy src
```

For end-to-end setup (AWS, Meta, Terraform, deployments), see
[docs/SETUP.md](docs/SETUP.md).

## Architecture

```
User → WhatsApp → Meta → API Gateway → Lambda (webhook)
                                       ↓
                                   Router → Command → Integration ↔ WhatsApp
                                       ↓ (async)
                                    SQS → EC2 worker → Integration ↔ WhatsApp
```

The full architecture, every folder's purpose, and recipes for adding
commands / integrations / Terraform resources are documented in
[docs/CODEBASE_GUIDE.md](docs/CODEBASE_GUIDE.md).

## Tech stack

- **Backend**: Python 3.12, uv, Pydantic v2, httpx, structlog, boto3
- **Frontend**: Next.js 16, React 19, Tailwind v4, shadcn/ui
- **Infrastructure**: Terraform ≥ 1.10, AWS (Lambda, API Gateway, SQS,
  DynamoDB, S3, EC2, IAM, Secrets Manager, CloudWatch, EventBridge)
- **CI/CD**: GitHub Actions with OIDC (no long-lived AWS keys)

## License

MIT