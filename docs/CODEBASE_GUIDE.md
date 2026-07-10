# WACTL — Codebase guide

A guided tour of the WACTL architecture for engineers who are new to
the codebase. Reads linearly in ~20 minutes.

---

## 1. What WACTL does

WACTL is a **WhatsApp-first personal-tooling platform**. The user DMs a
WhatsApp Business number, types a slash command (`/pdf-docx`,
`/image-resize`, etc.), optionally attaches a file, and gets the
processed result back in chat.

The backend is split between two AWS consumers:

- **Lambda** runs fast sync commands inline (image resize, web summary,
  translation). It also parses every webhook and dispatches to either
  itself (sync) or SQS (async).
- **EC2 worker** drains SQS for heavy async commands (PDF→DOCX, audio
  generation, merging). The worker is a single long-running process
  per instance; SIGTERM-aware.

Both consumers share one Python package: `src/wactl/`.

---

## 2. Tech stack

| Layer        | Choice                                      |
|--------------|---------------------------------------------|
| Runtime      | Python 3.12 (matches `.python-version`)     |
| HTTP         | `httpx` (async)                             |
| AWS SDK      | `boto3`                                     |
| Models       | `pydantic` v2 + `pydantic-settings`         |
| Logging      | `structlog` (JSON, contextual binding)      |
| LLM / TTS    | `google-genai` (Gemini)                     |
| PDF          | `pdf2docx`, `pymupdf`, `pypdf`              |
| Images       | `Pillow`                                    |
| Markdown/HTML| `markdownify`, `beautifulsoup4`             |
| Audio        | `pydub`                                     |
| Retry        | `tenacity`                                  |
| Lambda pack  | `uv pip install --target` + `zip`           |
| Worker pack  | Docker multi-stage → `tar.gz`               |
| Frontend     | Next.js 16 + Tailwind v4 (deployed to Vercel) |
| IaC          | Terraform 1.10+ (S3 backend, native lock)   |
| CI/CD        | GitHub Actions + OIDC (no long-lived keys)  |

---

## 3. Folder tour

```
wactl/
├── src/wactl/             # the single Python package (Lambda + worker)
│   ├── config.py          # pydantic-settings; reads env vars
│   ├── logging.py         # structlog config + bind_context helper
│   ├── exceptions.py      # WactlError hierarchy
│   ├── constants.py       # version constants, mime types
│   ├── webhook.py         # Lambda entry: parse, dedup, route, dispatch
│   ├── router.py          # text → RoutedCommand
│   ├── dispatcher.py      # sync vs async decision + context builder
│   ├── models/            # pydantic value objects (Job, User, etc.)
│   ├── integrations/
│   │   ├── aws/           # secrets, s3, sqs, dynamodb
│   │   ├── whatsapp/      # client, messages, media, parser
│   │   ├── converters/    # pdf_docx, image_resize, …
│   │   ├── gemini/        # client, text, tts
│   │   └── github/        # pr_summary
│   ├── commands/          # @register-decorated plugins
│   └── services/          # multi-step workflows (audiobook)
├── lambda/                # Lambda entry points (thin wrappers)
│   ├── webhook/handler.py
│   └── scheduler/handler.py
├── worker/                # EC2 worker (separate process)
│   ├── main.py            # long-poll + dispatch loop
│   ├── shutdown.py        # SIGTERM/SIGINT handlers
│   ├── Dockerfile         # builds worker.tar.gz
│   ├── build.sh           # Docker-based builder
│   └── systemd/           # wactl-worker.service
├── infra/                 # Terraform (everything AWS)
│   ├── provider.tf        # AWS provider + default tags
│   ├── backend.tf         # S3 backend w/ use_lockfile
│   ├── variables.tf, locals.tf, outputs.tf
│   ├── apigateway.tf, lambda.tf, iam.tf
│   ├── sqs.tf, dynamodb.tf, s3.tf, secrets.tf
│   ├── ec2.tf, cloudwatch.tf, eventbridge.tf
│   └── README.md
├── web/                   # Next.js 16 + Tailwind v4 (Vercel)
│   ├── app/
│   │   ├── page.tsx       # landing
│   │   ├── docs/page.tsx  # command reference
│   │   ├── privacy/page.tsx
│   │   └── terms/page.tsx
│   ├── components/        # qr-code.tsx (decorative SVG)
│   └── lib/site.ts        # WA_ME_LINK, COMMANDS, etc.
├── tests/
│   ├── unit/              # one file per module, mocked deps
│   └── integration/       # end-to-end webhook + worker
├── docs/                  # this guide + SETUP.md
├── .github/workflows/     # ci.yaml + deploy.yaml
└── pyproject.toml         # all deps + tool configs
```

---

## 4. Data-flow walkthroughs

### Sync command: `/image-resize 1024x768`

1. User sends `image-resize 1024x768` + a photo via WhatsApp.
2. Meta POSTs the envelope to API Gateway → Lambda.
3. `lambda/webhook/handler.lambda_handler` calls
   `wactl.webhook.handle(event)`.
4. `handle()` verifies the HMAC signature, parses the envelope,
   dedups the `wamid` via DynamoDB, and routes the text.
5. `route("/image-resize 1024x768")` returns `RoutedCommand` for the
   `ImageResizeCommand` class.
6. The registry says `sync=True`, so `dispatcher.dispatch_sync` runs
   the command in-process: download → Pillow resize → upload → reply.
7. The Lambda replies via WhatsApp and returns `{"statusCode": 200}`.
8. API Gateway returns 200 to Meta. Done.

### Async command: `/pdf-docx`

1–5. Same as above through route lookup.
6. The registry says `sync=False`, so `dispatcher.dispatch_async`
   serializes a `Job` and calls `sqs.send_message` — fast (<100 ms).
7. Lambda returns 200 immediately. The user sees a "queued…" reply
   (synchronously sent in step 6).
8. The EC2 worker's long-poll picks up the job within 20 seconds.
9. Worker calls `cmd.run(ctx)` with the same dependencies as Lambda,
   replies via WhatsApp, and deletes the SQS message.

### Scheduled cleanup

Currently a no-op: `eventbridge.tf` defines the daily cron but the
target Lambda is commented out. When enabled, it will scan the dedup
table for entries that survived the TTL grace period.

---

## 5. Design decisions

### Why `src/wactl/` (the src layout)

PEP 517 best practice. Forces tests to import the installed package,
catches missing `__init__.py` files, and works cleanly with both
Lambda's bundled zip and the worker's tarball.

### Why the decorator registry (vs explicit routing)

Adding a new command should be one file + one decorator. The registry
flattens into a dict; the dispatcher looks it up by name. No central
configuration to update, no risk of forgetting to wire a command in.

### Why `sync: bool` per command (vs two registries)

Some commands can plausibly be either. `/pdf-docx` is async today
because it's heavy, but a tiny test fixture could easily make it sync.
A single `sync` flag is more flexible than partitioning commands into
two registries that share 90% of their behavior.

### Why REST API Gateway (vs HTTP API)

HTTP API would be ~$1/M cheaper, but REST API gives us native binary
media types — useful if we ever want a `/download` endpoint to proxy
files back to a browser. Cost differential is negligible.

### Why SQS Standard (vs FIFO)

At-least-once is sufficient: jobs are idempotent (we dedup on
`wamid`), and we don't care about ordering (each job is independent).
SQS Standard gives us unlimited throughput; FIFO caps at 300/s.

### Why EC2 (vs Fargate or Lambda)

The plan calls for a long-running worker process. Lambda would mean
either Provisioned Concurrency (expensive) or a cold start per job
(slow). Fargate would work but adds container overhead. EC2 t4g.small
is the cheapest spot for a steady-state worker — ~$13/mo.

### Why Secrets Manager (vs Parameter Store)

- Per-secret access policies in IAM.
- Automatic rotation hooks.
- Audit trail via CloudTrail.
- Free-tier-friendly at our scale.

Parameter Store is fine for non-sensitive config; we use it via
environment variables instead.

### Why DynamoDB single-table for dedup

One table, one row per WAMID, TTL on `expires_at`. Match Meta's 7-day
retry window. Pay-per-request billing; no capacity planning.

---

## 6. Adding a new command

1. **Pick a name** and decide sync/async.
2. **Add the file**:
   ```python
   # src/wactl/commands/my_thing.py
   from wactl.commands.base import Command, CommandContext
   from wactl.commands.registry import register
   from wactl.models.command import CommandResponse

   @register("/my-thing", sync=True, description="Does the thing.")
   class MyThingCommand(Command):
       async def run(self, ctx: CommandContext) -> CommandResponse:
           # ctx.whatsapp.send_text(to=ctx.user.phone, text="done!")
           return CommandResponse(success=True)
   ```
3. **Register the module**: add `from wactl.commands import my_thing` to
   `src/wactl/commands/__init__.py`.
4. **Add a unit test**: `tests/unit/test_my_thing.py` that mocks every
   integration the command uses.
5. **Document**: add an entry to `web/lib/site.ts` (`COMMANDS` array)
   so it appears on the docs page.

That's it — no router changes, no dispatcher changes, no Terraform.

---

## 7. Adding a new integration

Pick the right sub-package (`aws/`, `whatsapp/`, `converters/`,
`gemini/`, `github/`) and add a small file (<200 lines):

```python
# src/wactl/integrations/foo/client.py
class FooClient:
    def __init__(self, http: httpx.AsyncClient, api_key: str) -> None:
        self._http = http
        self._key = api_key

    async def do_the_thing(self, payload: dict) -> dict:
        r = await self._http.post("https://api.foo.com/v1/thing", json=payload)
        r.raise_for_status()
        return r.json()
```

Wire it into `wactl.webhook.WebhookDeps` and `build_deps()`. Tests use
`respx` to mock the HTTP transport.

---

## 8. Adding a new Terraform resource

1. Pick the right `*.tf` file (or create a new one for a new service).
2. Add the resource with a name suffix from `local.suffix`.
3. If it needs an IAM grant, add a statement to the appropriate
   `aws_iam_policy_document` in `iam.tf`.
4. Add an output to `outputs.tf` if it's something callers will need.
5. Document in `infra/README.md`.

---

## 9. Logging & observability

- **Structured logs**: every entry is JSON with `event`, `level`,
  `timestamp`, plus bound context (`job_id`, `command`, `user_phone`).
- **CloudWatch log groups**: `/aws/lambda/wactl-<env>-webhook` for the
  Lambda, `/wactl/<env>/worker` for the worker.
- **Alarms**: DLQ depth, Lambda errors, worker CPU (see
  `cloudwatch.tf`).

The `bind_context()` helper uses `contextvars` so logs from anywhere
in an async task inherit the context — no manual threading.

---

## 10. Local development

```bash
# Install deps
uv sync

# Run all tests (no AWS needed)
uv run pytest tests -q

# Run a specific test
uv run pytest tests/integration/test_webhook_end_to_end.py -q

# Lint / type-check
uv run ruff check src tests worker lambda
uv run mypy src worker lambda

# Frontend
cd web && npm run dev
```

The worker can run locally against the real AWS queue by exporting
`WACTL_JOBS_QUEUE=<url>`. Set `WACTL_ENV=dev` and `AWS_REGION=us-east-1`,
and the worker will authenticate via your default AWS CLI profile.

---

## 11. Deployment walkthrough

See `docs/SETUP.md` for the full bootstrap. The short version:

1. Apply Terraform (`terraform apply -var env=prod -auto-approve`).
2. Populate the three WhatsApp secrets.
3. Build + upload the Lambda zip and worker tarball to S3.
4. Refresh the worker ASG.
5. Configure the Meta webhook with the API Gateway URL.
6. Send `/help` to the bot.

CI/CD does steps 3–5 automatically on push to `main` (via OIDC, no
long-lived keys needed).