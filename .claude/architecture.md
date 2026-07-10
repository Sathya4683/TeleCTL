---
name: architecture
description: High-level architectural decisions for WACTL — why the layout looks the way it does, AWS service choices, sync/async policy
metadata:
  type: project
---

# Architecture decisions

## Single Python package: `src/wactl/`

The backend is **one Python package** importable as `wactl.*`. Both the AWS
Lambda webhook handler and the EC2 worker install the same wheel via
`uv pip install` / `uv sync`. There is no code duplication between them —
only thin entry-point files (`lambda/webhook/handler.py`, `worker/main.py`)
that invoke logic from `wactl.*` modules.

`src/` layout (not flat): prevents accidental imports outside the package,
required by ruff `TID` and mypy strict mode.

## Plugin command system

Commands live in `src/wactl/commands/`. Each command is a class decorated
with `@register(name, *, sync)` which adds it to a global registry at import
time. The router knows nothing about implementations — it only resolves
`command_name → class` from the registry. **Adding a new command is one file
plus one decorator.**

The `commands/__init__.py` imports every command module so that registration
runs at package import. Tests should also ensure the package is imported
before asserting registry contents.

## Sync vs Async

Per-command `sync` flag controls routing:
- `sync=True` → Lambda invokes the command in-process (well under 15-min
  Lambda max). Used for <10s operations: image resize/compress, web
  summary, translate, GitHub PR.
- `sync=False` → Lambda enqueues a job to SQS and returns 200 immediately.
  The EC2 worker picks it up and runs the command. Used for anything that
  may exceed ~10s: PDF→DOCX, PDF→audio, PDF merge/split.

The dispatcher is `src/wactl/dispatcher.py`. The decision lives in the
command's registered metadata — no per-command branching in the webhook.

**Why:** Workloads that may run >10s kill the simple inline Lambda pattern.
SQS + EC2 worker is cheaper than Lambda for steady-state long jobs
(~$13/mo t4g.small vs Lambda GB-s rates) and lets us do bulk work without
worrying about timeout wars.

## AWS service choices

| Service            | Choice                                  | Reason                                                                          |
| ------------------ | --------------------------------------- | ------------------------------------------------------------------------------ |
| API Gateway        | **REST API** (not HTTP API)             | Binary media types, future-proof for `/download` endpoints; ~$1/mo extra OK    |
| SQS                | **Standard queue** (not FIFO)           | Unlimited throughput; idempotent workers; at-least-once is fine with DDB dedup |
| DynamoDB           | **Single table** (dedup only)           | Pay-per-request; TTL matches Meta's 7-day retry window                          |
| Secrets Manager    | **SM** (not Parameter Store)            | Audit trail via CloudTrail; rotation support for short-lived WhatsApp tokens    |
| Worker compute     | **EC2 t4g.small** (ARM64 Graviton)     | ~$13/mo, steady-state cheaper than Lambda; matches "EC2 worker" spec           |
| Lambda             | **Bundled zip** (no layers for v1)      | Single function; layer overhead > benefit; revisit if a second Lambda lands   |
| Lambda architecture| **x86_64**                              | Broader wheel availability for `pdf2docx`, `pymupdf`                           |
| Terraform backend  | **S3 + `use_lockfile = true`** (TF 1.10)| No DynamoDB lock table needed; one less resource to manage                      |
| GHA auth           | **OIDC** (no long-lived AWS keys)       | `sub` claim scoped to `repo:ORG/REPO:ref:refs/heads/main`                      |

**Why these matter:** each choice is the simplest thing that meets the
requirement. Avoiding premature optimization (FIFO, two DDB tables,
Graviton Lambda) keeps the surface area small.

## Data flow

- Inbound: `User → WhatsApp → Meta → API Gateway → Lambda → wactl.webhook
  → router → command → integration ↔ WhatsApp` (sync path)
- Or: `... → dispatcher → SQS → EC2 worker → command → integration ↔
  WhatsApp` (async path)
- Outbound: **never goes back through API Gateway**. Lambda/worker call
  WhatsApp Cloud API directly via `httpx.AsyncClient`.

## Idempotency

Every inbound message is deduped by `messages[].id` (the `wamid...`)
against a DynamoDB table with TTL = 7 days. This matches Meta's webhook
retry window — duplicates that arrive up to 7 days later are ignored.

## Why Terraform, why no Serverless Framework

The spec mandates Terraform. We agree: declarative IaC across the entire
stack (Lambda + API Gateway + SQS + DynamoDB + S3 + EC2 + IAM + CloudWatch
+ EventBridge) is best done in one tool. Serverless Framework would have
been a parallel declaration layer for a subset of resources.

---

Related: [[conventions]], [[repo-structure]], [[commands]]