# Architecture Decision Records

Lightweight ADRs for the design decisions in WACTL. Each entry has a
title, status, context, the decision itself, and the consequences.
See [docs/CODEBASE_GUIDE.md §5](CODEBASE_GUIDE.md#5-design-decisions)
for the longer narrative version.

---

## ADR-001 · Plugin architecture via decorator registry

**Status:** accepted · 2026-07-10

**Context.** The product grows by accretion: users want new slash
commands. We need a way to add a command without editing a central
router, dispatcher, or Terraform configuration.

**Decision.** A single `@register(name, *, sync, requires_media)` class
decorator populates a process-global dict. The dispatcher looks up
commands by name at request time. Each command file imports nothing
from `httpx`, `boto3`, or the WhatsApp API directly — it only
consumes dependencies on `CommandContext`.

**Consequences.**

- ✅ Adding a command = 1 new file + 1 line in `commands/__init__.py`.
- ✅ Tests can `monkeypatch.setattr` registry entries cleanly.
- ⚠️ Registry is a process global — make sure workers don't accidentally
  re-import under a fresh interpreter (they don't; cold-start = fresh
  process every time).

---

## ADR-002 · Sync vs async split per command

**Status:** accepted · 2026-07-10

**Context.** Some commands are fast (image resize, web summary); others
take 60+ seconds (PDF→DOCX, audio generation). Lambda's 15-minute
ceiling would force us to choose between two extremes.

**Decision.** Each command declares `sync: bool`. `sync=True` runs in
the Lambda; `sync=False` enqueues to SQS for the EC2 worker. Both
share the same `CommandContext` and dependencies.

**Consequences.**

- ✅ One unified command surface, two execution backends.
- ✅ Capacity planning is per-command, not per-deployment.
- ⚠️ Async commands have 5-min-to-15-min UX latency depending on queue
  depth; sync commands cap at Lambda's 60-s budget.

---

## ADR-003 · REST API Gateway over HTTP API

**Status:** accepted · 2026-07-10

**Context.** Meta's webhook payloads include binary media URLs that
expire in 5 minutes. We need to fetch + upload to S3 quickly.

**Decision.** Use REST API Gateway. It supports `binary_media_types`
natively, which we'd want anyway if we ever expose a `/download`
endpoint for browser clients.

**Consequences.**

- ✅ Native binary media support.
- ⚠️ ~$1/M-request cost premium over HTTP API — negligible at our scale.

---

## ADR-004 · SQS Standard, not FIFO

**Status:** accepted · 2026-07-10

**Context.** Jobs are independent — there's no inter-job ordering
requirement, and at-least-once is sufficient because dedup catches
duplicate wamids.

**Decision.** SQS Standard queue. Single, well-understood primitive.

**Consequences.**

- ✅ Unlimited throughput.
- ⚠️ Occasional duplicate delivery — but our dedup table makes that
  invisible to the user.

---

## ADR-005 · EC2 worker over Lambda or Fargate

**Status:** accepted · 2026-07-10

**Context.** Heavy commands need a long-running process that can pull
SQS, run jobs sequentially, and survive gracefully through redeploys.

**Decision.** Single EC2 t4g.small with `MinSize=1` ASG. systemd unit
starts on boot; cloud-init downloads the release tarball from S3 on
first launch.

**Consequences.**

- ✅ ~$13/mo steady-state cost (or $0/mo on t3.micro during the 12-mo
  free-tier window).
- ✅ No cold-start tax on every job.
- ⚠️ One instance = no horizontal scale-out within an ASG. Burst above
  one concurrent job requires adding capacity manually.

---

## ADR-006 · Secrets Manager, not Parameter Store

**Status:** accepted · 2026-07-10

**Context.** We hold WhatsApp credentials, app secret, verify token,
and (optionally) a Gemini key. Audit and rotation matter even at
small scale.

**Decision.** AWS Secrets Manager for all sensitive values. Env vars
on the Lambda / worker hold only Secrets Manager **names**, not
values.

**Consequences.**

- ✅ Per-secret IAM, rotation hooks, CloudTrail audit.
- ⚠️ ~$0.40/secret/mo = $1.20/mo for the four we use. Recurring, but
  small.

---

## ADR-007 · DynamoDB single-table for dedup

**Status:** accepted · 2026-07-10

**Context.** We need to dedup inbound webhooks against Meta's 7-day
retry window. That's one entity (a wamid), one attribute (an expiry
timestamp).

**Decision.** Single DynamoDB table, partition key `pk = wamid`,
TTL on `expires_at`, pay-per-request billing.

**Consequences.**

- ✅ Zero capacity planning.
- ✅ Stale entries auto-expire.
- ⚠️ If we ever need multi-turn conversation state, that goes in a
  second table — single-table-for-everything is not a hard commitment.

---

## ADR-008 · Direct-from-worker WhatsApp replies

**Status:** accepted · 2026-07-10

**Context.** Outbound messages could theoretically traverse API
Gateway in reverse, but that would couple our delivery path to a
public-facing surface designed for inbound traffic.

**Decision.** Lambda and worker reach the WhatsApp Cloud API directly
with the system-user token. They never send via API Gateway.

**Consequences.**

- ✅ Decoupled delivery path; the webhook URL stays read-only.
- ⚠️ The bearer token is held in memory on every process — Secrets
  Manager + IAM make this acceptable.

---

## ADR-009 · Outbound flow for OIDC / GitHub Actions

**Status:** accepted · 2026-07-10

**Context.** Long-lived AWS access keys in a GitHub repo are a known
supply-chain risk.

**Decision.** Terraform provisions an OIDC provider + a role whose
trust policy restricts the `sub` claim to
`repo:sathya-narayanan/wactl:ref:refs/heads/main`. Workflows use
`aws-actions/configure-aws-credentials@v4` with `role-to-assume`.

**Consequences.**

- ✅ Zero long-lived secrets in the repo or its Actions secrets.
- ⚠️ If you fork, update the trust policy in
  [infra/iam.tf](../infra/iam.tf).

---

## ADR-010 · No real QR code on the landing page

**Status:** accepted · 2026-07-10

**Context.** The QR component renders an SVG with a deterministic
bitmap; it's not a real Reed-Solomon–encoded QR.

**Decision.** Treat it as decorative. The wa.me link itself works on
click. Replace with `qrcode.react` (or any real library) before
publishing a printed card.

**Consequences.**

- ✅ No extra npm dep for what's effectively a placeholder.
- ⚠️ Scanners will not decode the current SVG.