---
name: repo-structure
description: Tour of every folder in WACTL — what belongs where and what to never put where
metadata:
  type: project
---

# Repository structure

```
wactl/
├── .claude/                      # Claude Code project memory (this directory)
├── .github/workflows/            # CI + CD GitHub Actions
├── docs/                         # SETUP.md + CODEBASE_GUIDE.md
├── infra/                        # Terraform (one .tf per concern)
├── lambda/                       # Thin Lambda entry points
├── scripts/                      # Local dev utilities (local-webhook.py)
├── src/wactl/                    # SINGLE Python package (shared by Lambda + worker)
│   ├── commands/                 # Plugin commands
│   ├── integrations/             # External-API wrappers
│   ├── models/                   # Pydantic data models
│   ├── services/                 # Multi-integration orchestrations
│   ├── config.py                 # Central settings
│   ├── logging.py                # structlog setup
│   ├── exceptions.py             # Typed error hierarchy
│   ├── constants.py
│   ├── webhook.py                # Shared entry-point logic
│   ├── router.py                 # command name → class
│   └── dispatcher.py             # sync vs async dispatch
├── tests/                        # pytest
├── web/                          # Next.js 16 frontend
└── worker/                       # EC2 worker
```

## Folder responsibilities

### `src/wactl/commands/`

**Only commands.** Each file = one command class. Always `@register` first.
No HTTP / AWS code; only integration calls.

Sub-folders? **No.** Flat is fine for nine commands; revisit if >25.

### `src/wactl/integrations/`

External-API wrappers. One folder per provider:
- `aws/` — S3, SQS, DynamoDB, Secrets Manager clients.
- `whatsapp/` — Meta Cloud API: client, parser, messages, media.
- `converters/` — pdf-docx, pdf-text, merge, split, image-resize, image-compress.
- `github/` — PR fetch.
- `gemini/` — text + TTS.

**Integrations may import other integrations only within the same provider
folder** (e.g., `messages.py` may import `client.py`). Cross-provider
imports are forbidden.

### `src/wactl/services/`

Multi-step orchestrations. **Use sparingly.** If a service has more than
one integration calling one business goal (e.g., PDF → audio =
`pdf_text.extract` + `chunk` + `gemini.tts.synthesize` + `pydub.merge`),
create a service. For one-integration wrappers, just call the
integration from the command directly.

### `src/wactl/models/`

Pydantic models only. One file per topic (webhook, user, job, command).

### `lambda/`

**Lambda entry points only.** Each `handler.py` must be <30 lines — it
imports from `wactl.*` and delegates. No business logic in Lambda code.

### `worker/`

EC2 worker entry point. Same rule: `worker/main.py` is <50 lines and
delegates to `wactl.*`.

### `infra/`

Terraform. **One concern per file** (provider, sqs, lambda, iam, ec2,
...). `README.md` describes each file's purpose.

### `web/`

Next.js 16 + shadcn/ui frontend. Pages: `/`, `/docs`, `/privacy`,
`/terms`. No backend logic. Deploys to Vercel.

### `tests/`

- `unit/` — pure unit tests with mocked I/O.
- `integration/` — multi-module tests.
- `fixtures/` — sample webhook payloads, sample files.
- `conftest.py` — shared fixtures.

### `docs/`

Two long-form docs:
- `SETUP.md` — from-zero onboarding (the only doc a brand-new contributor
  needs first).
- `CODEBASE_GUIDE.md` — architecture tour (read it once before
  contributing).

## What's NOT in this repo

| You'd expect...                | But it's not here because...                                                       |
| ------------------------------ | ---------------------------------------------------------------------------------- |
| `requirements.txt`             | We use `pyproject.toml` + `uv.lock`.                                              |
| `.env`                         | Git-ignored. Use `.env.example` for the template.                                 |
| `tests/conftest.py` (root)     | It's at `tests/conftest.py`.                                                       |
| `Makefile`                     | We use `uv run <cmd>` directly.                                                    |
| `setup.py`                     | We use `hatchling` build backend declared in `pyproject.toml`.                     |
| `utils/`                       | Replaced by helpers integrated into the relevant module. No dumping-ground folder. |

---

Related: [[architecture]], [[conventions]], [[commands]]