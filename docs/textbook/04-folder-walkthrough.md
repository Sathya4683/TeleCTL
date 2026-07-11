# 04 — Folder Walkthrough

This chapter tours every directory and most files in the repo. It's meant as a reference, not a linear read — come back to it when you need to find something.

```
wactl/
├── src/wactl/                 # the single Python package (Lambda + worker import this)
├── lambda/                    # Lambda entry-point files (thin wrappers around the package)
├── worker/                    # the EC2 worker process
├── infra/                     # Terraform: every AWS resource
├── web/                       # Next.js marketing site
├── tests/                     # unit + integration tests
├── docs/                      # markdown documentation (this file lives here)
├── scripts/                   # one-off shell helpers
├── .github/                   # CI workflows + issue templates
├── pyproject.toml             # Python deps + tool config (ruff, mypy, pytest)
├── uv.lock                    # locked dep versions (commit this)
├── .python-version            # 3.12
├── README.md                  # the public-facing readme
├── LICENSE                    # MIT
├── CHANGELOG.md
├── AUTHORS.md
├── SECURITY.md
├── SUPPORT.md
├── CONTRIBUTING.md
└── CODE_OF_CONDUCT.md
```

The four pillars are `src/`, `lambda/`, `worker/`, and `infra/`. The first three are Python; `infra/` is HCL. `web/` is TypeScript. `tests/` is Python.

---

## 4.1 — `src/wactl/` — the core package

This is the only Python package. Both `lambda/webhook/handler.py` and `worker/main.py` import from it.

```
src/wactl/
├── __init__.py
├── config.py                  # pydantic-settings: env vars → typed Settings
├── logging.py                 # structlog config + bind_context helper
├── exceptions.py              # the WactlError hierarchy
├── constants.py               # magic strings, limits, MIME types
├── webhook.py                 # the core webhook handler (parse, dedup, route, dispatch)
├── router.py                  # text → RoutedCommand
├── dispatcher.py              # sync vs async dispatch + context builder
├── commands/                  # the @register-decorated plugin tree
├── models/                    # pydantic value objects
├── integrations/              # one subpackage per external system
└── services/                  # multi-step workflows (audiobook)
```

### Top-level files

| File | Purpose |
|---|---|
| `__init__.py` | Empty marker. |
| `config.py` | The `Settings` class. Reads env vars via pydantic-settings. Module-level singleton `settings = get_settings()`. |
| `logging.py` | `configure_logging()`, `get_logger()`, `bind_context()`, `reset_context()`. The structlog config produces JSON lines. |
| `exceptions.py` | The `WactlError` tree: `ConfigError`, `WebhookError`, `CommandError`, `IntegrationError`, `ConverterError`. |
| `constants.py` | Magic strings: `DEFAULT_API_VERSION`, `MAX_INBOUND_MEDIA_BYTES`, MIME type sets, retry backoff base. |
| `webhook.py` | The Lambda-side entry point. Verifies HMAC, decodes body, parses envelope, dedups, routes, dispatches. |
| `router.py` | `parse(text) → (command, rest)` and `route(text) → RoutedCommand`. |
| `dispatcher.py` | `dispatch_sync` (run inline) and `dispatch_async` (enqueue to SQS). Also `prepare_context` (downloads media if needed). |

### `src/wactl/commands/` — the plugin tree

This is where every slash command lives. Each command is one file with one class.

| File | Command | Sync? | Needs media? | Library |
|---|---|---|---|---|
| `__init__.py` | (imports every command module to fire the @register decorators) | — | — | — |
| `registry.py` | The `@register` decorator + the `_REGISTRY` dict | — | — | — |
| `base.py` | `Command` ABC + `CommandContext` value object | — | — | — |
| `_helpers.py` | `media_bucket`, `output_key`, `require_whatsapp`, `suggest_filename` | — | — | — |
| `image_resize.py` | `/image-resize` | sync | yes | Pillow |
| `image_compress.py` | `/image-compress` | sync | yes | Pillow |
| `pdf_docx.py` | `/pdf-docx` | async | yes | pdf2docx |
| `pdf_audio.py` | `/pdf-audio` | async | yes | Gemini TTS (via `services.audiobook`) |
| `merge_pdf.py` | `/merge-pdf` | async | yes | pypdf |
| `split_pdf.py` | `/split-pdf` | async | yes | pypdf + pymupdf |
| `web_summary.py` | `/web-summary` | sync | no | httpx + BeautifulSoup + markdownify + Gemini |
| `github_pr.py` | `/github-pr` | sync | no | httpx + Gemini |
| `translate.py` | `/translate` | sync | optional | pymupdf + Gemini |

Adding a new command = drop a file in this folder + add an import to `__init__.py`. See [Chapter 7 — Commands](07-commands.md) for the full pattern.

### `src/wactl/models/` — pydantic value objects

| File | What's in it |
|---|---|
| `__init__.py` | Re-exports. |
| `user.py` | `UserContext` (phone, name, message_id, waba_id, phone_number_id). |
| `webhook.py` | The full Meta envelope: `WhatsAppEnvelope`, `Entry`, `Change`, `Value`, `TextMessage`, `MediaMessage`, plus content types. All `frozen=True`. |
| `command.py` | `CommandMeta` (name, sync, requires_media, description), `CommandRequest`, `CommandResponse`. |
| `job.py` | `Job` — the SQS envelope. Job_id, command, args, user, media_id, enqueued_at, meta. |

### `src/wactl/integrations/` — one subpackage per external system

```
integrations/
├── aws/                       # boto3 wrappers — S3, SQS, DynamoDB, SSM
├── whatsapp/                  # the WhatsApp Cloud API client + parsers
├── converters/                # PDF/image libraries
├── gemini/                    # Google Gemini (text + TTS)
├── github/                    # GitHub API
└── web/                       # public web page fetcher
```

| Subpackage | Files | Purpose |
|---|---|---|
| `aws/` | `s3.py`, `sqs.py`, `dynamodb.py`, `secrets.py`, `__init__.py` | One module per AWS service. Each module has a module-level boto3 client singleton + thin wrapper functions. Errors are caught and re-raised as `AWSIntegrationError`. |
| `whatsapp/` | `client.py`, `messages.py`, `media.py`, `signature.py`, `parser.py` | `WhatsAppClient` is the async HTTP wrapper with retry/backoff. `messages` has the outbound helpers (`send_text`, `send_image`, `send_document`, `send_audio`, `send_video`, `send_reaction`). `media` has inbound media URL resolution + download. `signature` is the HMAC verify. `parser` is the envelope-to-internal-model mapper. |
| `converters/` | `image_resize.py`, `image_compress.py`, `merge_pdf.py`, `split_pdf.py`, `pdf_text.py`, `pdf_docx.py` | Pure functions: `bytes → bytes`. Each command delegates to one of these. |
| `gemini/` | `client.py`, `text.py`, `tts.py`, `__init__.py` | `GeminiClient` is a thin wrapper over `google-genai`. `text` has the high-level prompts (summarize, translate, summarise_github_pr). `tts` is the audio generation. |
| `github/` | `pr_summary.py`, `__init__.py` | `fetch_pr` (the metadata + diff download) and `PullRequestSummary` (the parsed result). |
| `web/` | `fetcher.py`, `__init__.py` | `fetch_and_extract` — fetch a URL, strip scripts/styles, return Markdown. |

### `src/wactl/services/` — multi-step workflows

| File | Purpose |
|---|---|
| `__init__.py` | Re-exports. |
| `audiobook.py` | The `/pdf-audio` pipeline: PDF → text → chunks → parallel TTS calls → WAV concat → MP3. |

If a command needs more than one integration to cooperate, it goes in `services/` instead of `commands/`.

---

## 4.2 — `lambda/` — the Lambda entry points

```
lambda/
├── webhook/                   # the webhook Lambda
│   ├── __init__.py
│   └── handler.py             # `lambda_handler` — the AWS entry point
└── scheduler/                 # the (placeholder) EventBridge-triggered Lambda
    ├── __init__.py
    └── handler.py             # `lambda_handler` — currently a no-op
```

The `webhook/handler.py` is intentionally tiny — it imports `wactl.webhook` and forwards the event. The same code is callable from tests, from a local `sam local invoke`, and from AWS.

`scheduler/handler.py` is a stub. The EventBridge rule in `infra/eventbridge.tf` is created but disabled (`is_enabled = false`) because the cleanup job isn't implemented yet.

---

## 4.3 — `worker/` — the EC2 worker process

```
worker/
├── __init__.py
├── main.py                    # the long-poll + dispatch loop
├── shutdown.py                # SIGTERM/SIGINT handlers
├── build.sh                   # the Docker build entry point
├── Dockerfile                 # the build recipe
└── systemd/
    └── wactl-worker.service   # the systemd unit file (copied to /etc/systemd/system/ on boot)
```

`main.py` runs a `while not shutdown.is_set()` loop. Each iteration long-polls SQS (20s wait), receives up to 10 messages, and dispatches each. The dispatch flow re-uses `wactl.dispatcher.prepare_context` and the registered command class. On success, the message is deleted from SQS. On failure, it's logged and left to re-deliver (and eventually DLQ after 5 attempts).

`shutdown.py` hooks `SIGTERM` (from systemd `stop`) and `SIGINT` (Ctrl-C) to set an asyncio event the loop checks at every iteration. This gives a graceful drain — the in-flight job finishes before the process exits.

`build.sh` + `Dockerfile` are the CI build entry. They produce `worker.tar.gz` (Python + worker code, ~50 MB) and a `.sha256` sidecar. See [Chapter 8 — Worker](08-worker.md) for the full build flow.

`systemd/wactl-worker.service` is copied to `/etc/systemd/system/wactl-worker.service` on first boot by the cloud-init user data. The service runs as the `wactl` user, pulls env vars from `/etc/wactl/worker.env`, and starts the worker.

---

## 4.4 — `infra/` — the Terraform

```
infra/
├── README.md                  # the infra-specific quickstart
├── provider.tf                # AWS provider + default tags
├── backend.tf                 # S3 backend (state + lockfile)
├── variables.tf               # env, project_name, region, domain
├── locals.tf                  # name suffix, account_id, common ARNs
├── outputs.tf                 # URLs and ARNs to surface
├── data.tf                    # data sources (caller identity, current region)
├── apigateway.tf              # REST API + /webhook resource + GET/POST methods
├── lambda.tf                  # the webhook Lambda + env vars
├── iam.tf                     # all 3 roles + the OIDC provider + the GitHub Actions policy
├── sqs.tf                     # the jobs queue + DLQ
├── dynamodb.tf                # the dedup table
├── s3.tf                      # the media + releases buckets
├── secrets.tf                 # the 3 SSM SecureString parameters
├── ec2.tf                     # the launch template + ASG + security group + user data
├── cloudwatch.tf              # the 2 log groups + 3 alarms
└── eventbridge.tf             # the (disabled) daily cleanup rule
```

Every file is one or two concerns. See [Chapter 11 — Infrastructure as Code](11-infrastructure-as-code.md) for the full walkthrough.

---

## 4.5 — `web/` — the Next.js site

```
web/
├── app/
│   ├── layout.tsx             # root layout (metadata, theme)
│   ├── page.tsx               # landing page
│   ├── docs/page.tsx          # command reference
│   ├── privacy/page.tsx       # privacy notice
│   └── terms/page.tsx         # terms of service
├── components/
│   └── qr-code.tsx            # decorative SVG (NOT a real QR)
├── lib/
│   └── site.ts                # site-wide constants + the COMMANDS list
├── package.json               # Node deps
├── tsconfig.json
├── next.config.ts
├── next-env.d.ts
└── package-lock.json
```

The site is intentionally minimal — a landing page with a wa.me link, a docs page mirroring `COMMANDS`, and two legal pages. See [Chapter 13 — Frontend](13-frontend.md).

---

## 4.6 — `tests/` — pytest tree

```
tests/
├── conftest.py                # top-level fixtures (sample webhooks, app_secret)
├── fixtures/                  # captured webhook payloads (text/image/document/status)
├── unit/                      # one test file per module
│   ├── conftest.py            # re-exports the helpers below
│   ├── conftest_helpers.py    # make_user, make_context, fake_whatsapp, fake_s3
│   ├── test_aws_*.py
│   ├── test_command_*.py
│   ├── test_converters_*.py
│   ├── test_dispatcher.py
│   ├── test_gemini_*.py
│   ├── test_github_*.py
│   ├── test_parser.py
│   ├── test_registry.py
│   ├── test_router.py
│   ├── test_signature.py
│   └── test_whatsapp_*.py
└── integration/
    ├── test_webhook_end_to_end.py   # full webhook flow with mocked AWS
    └── test_worker.py                # worker poll + dispatch loop
```

The convention: one test file per source file. Unit tests are pure (no AWS, no network). Integration tests touch multiple modules but use mocks for external services. See [Chapter 15 — Testing](15-testing.md).

---

## 4.7 — `docs/`

```
docs/
├── README.md                  # the public-facing readme
├── CODEBASE_GUIDE.md          # the 20-min overview
├── SETUP.md                   # bootstrap-from-zero
├── DECISIONS.md               # the ADRs (one per design choice)
├── architectureV1.png         # the architecture diagram
└── textbook/                  # this textbook (you're here)
    ├── README.md
    ├── 01-introduction.md
    ├── 02-concepts-primer.md
    ├── ... (18 chapters)
    └── 18-glossary.md
```

The textbook sits alongside the other docs. The existing files (`CODEBASE_GUIDE.md`, `SETUP.md`, `DECISIONS.md`) remain the "fast" versions; the textbook is the deep version.

---

## 4.8 — `scripts/`

A handful of shell helpers. Currently contains `build_worker.sh` (a thin wrapper around `worker/build.sh`) and similar. These are not exercised by CI; they're for local iteration.

---

## 4.9 — `.github/`

```
.github/
├── dependabot.yml             # auto-PR for new dep versions
├── ISSUE_TEMPLATE/config.yml
└── workflows/
    ├── ci.yaml                # ruff + mypy + pytest on PR/push
    ├── deploy.yaml            # build + upload + terraform apply on push to main
    └── deploy-frontend.yaml   # Vercel deploy on web/** changes
```

See [Chapter 16 — Deployment and CI/CD](16-deployment-and-cicd.md) for the full breakdown.

---

## 4.10 — Root files

| File | Purpose |
|---|---|
| `pyproject.toml` | The single config file for Python. Deps, dev deps, ruff, mypy, pytest, coverage. |
| `uv.lock` | Locked versions of every dep. Commit this. |
| `.python-version` | `3.12` — `uv` uses this automatically. |
| `README.md` | The repo's public readme. Brief; this textbook is the deep version. |
| `LICENSE` | MIT. |
| `CHANGELOG.md` | High-level release notes. |
| `AUTHORS.md` | The author. |
| `SECURITY.md` | How to report a vulnerability. |
| `SUPPORT.md` | Where to ask for help. |
| `CONTRIBUTING.md` | Conventions for PRs. |
| `CODE_OF_CONDUCT.md` | Standard Contributor Covenant. |

---

## Next

→ [`05-end-to-end-flow.md`](05-end-to-end-flow.md) — trace a real message from start to finish.
