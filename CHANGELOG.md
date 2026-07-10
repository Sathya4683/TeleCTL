# Changelog

All notable changes to WACTL are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `docs/DECISIONS.md` — architecture decision records
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `SUPPORT.md`
- `.editorconfig`, `.gitattributes`, `.dockerignore`
- GitHub issue + PR templates
- Top-level `LICENSE` (MIT)

## [0.1.0] — 2026-07-10

Initial release of WACTL — a WhatsApp-first automation platform.

### Added

**Backend (`src/wactl/`)**

- `config.py` — pydantic-settings env loader
- `logging.py` — structlog JSON + bound-context helpers
- `exceptions.py` — `WactlError` hierarchy
- `webhook.py` — Lambda entry: HMAC verify, dedup, route, dispatch
- `router.py` + `dispatcher.py` — text → command, sync vs async split
- `models/` — pydantic models for webhooks, jobs, users, commands
- `integrations/`:
  - `aws/` — Secrets Manager, S3, SQS, DynamoDB
  - `whatsapp/` — async client (HMAC, retry, media upload/download)
  - `converters/` — pdf2docx, pymupdf, pypdf, Pillow
  - `gemini/` — text + TTS
  - `github/` — PR metadata + diff
- `commands/` (registered with `@register`):
  - `/pdf-docx`, `/pdf-audio`, `/merge-pdf`, `/split-pdf`
  - `/image-resize`, `/image-compress`
  - `/translate`, `/web-summary`, `/github-pr`
- `services/audiobook.py` — multi-step PDF→text→chunks→TTS→merge

**Lambda (`lambda/`)**

- `webhook/handler.py` — thin Lambda entry point
- `scheduler/handler.py` — placeholder for EventBridge cleanup

**Worker (`worker/`)**

- `main.py` — SIGTERM-aware long-poll + dispatch loop
- `shutdown.py` — signal handlers
- `systemd/wactl-worker.service` — hardened systemd unit
- `Dockerfile` + `build.sh` — produces `worker.tar.gz`

**Infrastructure (`infra/`)**

- REST API + Lambda + SQS + DLQ + DynamoDB (TTL dedup) + S3 + Secrets
- EC2 launch template + ASG + cloud-init user-data
- CloudWatch log groups + alarms (DLQ depth, errors, CPU)
- GitHub Actions OIDC trust + IAM role (least-privilege)

**CI/CD (`.github/`)**

- `workflows/ci.yaml` — ruff + mypy + pytest
- `workflows/deploy.yaml` — Lambda zip + worker tarball build, S3
  upload, `terraform apply` via OIDC

**Frontend (`web/`)**

- Next.js 16 + Tailwind v4
- Landing page with command reference and decorative QR
- `/docs` — command reference
- `/privacy`, `/terms` — legal pages

**Tests (`tests/`)**

- 232 passing tests across unit + integration
- Coverage of parser, signature, registry, router, dispatcher, every
  command, every integration, end-to-end webhook flow, worker loop

### Notes

- This is a **portfolio / personal-use release**. Designed for ≤15
  users with low traffic. See `docs/CODEBASE_GUIDE.md §5` for the
  rationale behind every architectural decision.
- The `/github-pr` command accepts an optional PAT via context
  injection; the Terraform plumbing for a `wactl/github/token` secret
  is documented but not yet provisioned by default.
- The QR component in `web/components/qr-code.tsx` is decorative —
  it does not encode a real QR matrix. Replace with a real library
  before pointing users at a printed card.