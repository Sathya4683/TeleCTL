# 03 — Architecture

This chapter zooms out to show every component of WACTL and how they fit together. If you finish this and `02-concepts-primer.md`, you should be able to draw the system from memory.

## 3.1 — The system at a glance

```text
                                  WACTL platform
                                  ─────────────

   ┌──────────────────────────────────────────────────────────────────┐
   │                                                                  │
   │  ╔═══════════════════╗      ┌─────────────────┐                  │
   │  ║   WhatsApp user   ║      │  Marketing site │  (Vercel)        │
   │  ║ (your phone)      ║      │  (Next.js 16)   │                  │
   │  ╚══════════╤════════╝      └─────────────────┘                  │
   │             │ WhatsApp DM                                           │
   │             ▼                                                       │
   │  ┌─────────────────────┐    POST signed JSON                       │
   │  │  Meta WhatsApp      │ ─────────────────────────┐               │
   │  │  Cloud API          │                          │               │
   │  │  (graph.facebook.)  │                          ▼               │
   │  └─────────────────────┘              ┌────────────────────┐     │
   │             ▲                          │   API Gateway      │     │
   │             │                          │   (REST API)       │     │
   │             │                          └─────────┬──────────┘     │
   │             │                                    │ invoke         │
   │             │                                    ▼                 │
   │             │                          ┌────────────────────┐     │
   │             │                          │  AWS Lambda        │     │
   │             │                          │  "wactl-webhook"   │     │
   │             │                          │                    │     │
   │             │  HMAC verify             │  1. verify sig     │     │
   │             │  parse JSON              │  2. dedup wamid    │     │
   │             │  dedup                   │  3. route command  │     │
   │             │  route                   │  4. dispatch       │     │
   │             │  dispatch                │     ┌── sync: run  │     │
   │             │  ↑                       │     │   inline     │     │
   │             │  │                       │     └── async:     │     │
   │             │  │ reply media/text      │         enqueue    │     │
   │             │  │                       └────┬───────────────┘     │
   │             │  │                            │                      │
   │             │  │  enqueue (async only)      │                      │
   │             │  └──────────────┐             │                      │
   │             │                 ▼             │                      │
   │             │       ┌─────────────────┐     │                      │
   │             │       │  SQS jobs queue │     │                      │
   │             │       │  (Standard)     │     │                      │
   │             │       └────────┬────────┘     │                      │
   │             │                │              │                      │
   │             │                │ long-poll    │                      │
   │             │                ▼              │                      │
   │             │       ┌─────────────────┐     │                      │
   │             │       │  EC2 worker     │     │                      │
   │             │       │  (t4g.nano)     │     │                      │
   │             │       │                 │     │                      │
   │             │       │  systemd-managed │     │                      │
   │             │       │  Python process │     │                      │
   │             │       │  polling SQS    │     │                      │
   │             │       └────────┬────────┘     │                      │
   │             │                │              │                      │
   │             │                │  put/get     │                      │
   │             │                ▼              ▼                      │
   │             │       ┌─────────────────────────────┐               │
   │             │       │  S3 media bucket            │               │
   │             │       │  (presigned URLs)           │               │
   │             │       └─────────────────────────────┘               │
   │             │                                                       │
   │             │       ┌─────────────────────────────┐               │
   │             │       │  DynamoDB dedup table        │               │
   │             │       │  (7-day TTL)                 │               │
   │             │       └─────────────────────────────┘               │
   │             │                                                       │
   │             │       ┌─────────────────────────────┐               │
   │             │       │  SSM Parameter Store         │               │
   │             │       │  (WhatsApp creds)            │               │
   │             │       └─────────────────────────────┘               │
   │             │                                                       │
   │             │       ┌─────────────────────────────┐               │
   │             │       │  CloudWatch                  │               │
   │             │       │  (logs + alarms)             │               │
   │             │       └─────────────────────────────┘               │
   │             │                                                       │
   └─────────────┼───────────────────────────────────────────────────────┘
                 │
                 └── All replies are pushed directly to the WhatsApp Cloud API;
                     the webhook URL is inbound-only.
```

That's the whole system. Five compute surfaces (Meta, API Gateway, Lambda, EC2, plus the marketing site on Vercel), three storage surfaces (S3, DynamoDB, SSM), one queue (SQS), and one observability surface (CloudWatch).

## 3.2 — The request lifecycle

The most important thing to internalise: **there are two execution paths** after a message arrives.

### Path A — sync (Lambda runs the command inline)

```text
   user          Meta           API GW        Lambda              S3           Meta (reply)
    │             │              │              │                  │                 │
    │ /img-rs     │              │              │                  │                 │
    │ 800x600     │              │              │                  │                 │
    │ + photo ───►│              │              │                  │                 │
    │             │ POST signed  │              │                  │                 │
    │             │ ────────────►│ ────────────►│                  │                 │
    │             │              │              │ verify HMAC      │                 │
    │             │              │              │ dedup wamid      │                 │
    │             │              │              │ route "/img-rs"  │                 │
    │             │              │              │ Pillow resize    │                 │
    │             │              │              │ PUT s3://...    ─►│                 │
    │             │              │              │ presigned URL    │                 │
    │             │              │              │ send_image ──────────────────────►│
    │             │ 200 OK ◄─────│ ◄────────────│                  │                 │
    │ ◄── image ──┤              │              │                  │                 │
    │             │              │              │                  │                 │
```

Total wall time: ~500ms–2s.

### Path B — async (Lambda enqueues, worker drains)

```text
   user         Meta       API GW      Lambda       SQS        worker         S3        Meta (reply)
    │            │           │           │           │             │            │             │
    │ /pdf-docx  │           │           │           │             │            │             │
    │ + PDF ────►│           │           │           │             │            │             │
    │            │ POST ────►│ ─────────►│           │             │            │             │
    │            │           │           │ verify    │             │            │             │
    │            │           │           │ dedup     │             │            │             │
    │            │           │           │ route     │             │            │             │
    │            │           │           │ enqueue ──►             │            │             │
    │            │           │           │           │             │            │             │
    │            │           │           │           │ receive (≤20s)          │             │
    │            │           │           │           │ ──────────►│            │             │
    │            │           │           │           │             │ download   │             │
    │            │           │           │           │             │ PDF from   │             │
    │            │           │           │           │             │ Meta      ◄┘             │
    │            │           │           │           │             │ pdf2docx   │             │
    │            │           │           │           │             │ PUT DOCX  ─►             │
    │            │           │           │           │             │ presign URL             │
    │            │           │           │           │             │ send_document ──────────►│
    │            │           │           │           │             │ delete msg │             │
    │            │           │           │           │             │            │             │
    │            │           │           │           │             │            │             │
    │ ◄─ DOCX ────┤           │           │           │             │            │             │
```

Total wall time: 5–60s.

## 3.3 — Why split sync and async this way?

The Lambda is billed per millisecond and has a 15-minute max runtime. Most commands finish in under 2 seconds — perfect for Lambda. PDF→audio on a 30-page book takes ~60 seconds; well within the 15-minute ceiling, but Lambda would charge for 60 seconds of compute per invocation. The worker, by contrast, is a single always-on process that bills by the hour, ~$0.005/hr on `t4g.nano` (free tier). One worker can drain the queue for many users.

The split also has a side benefit: the user gets a **fast 200 OK** on async commands (the Lambda just enqueues), so Meta doesn't retry the webhook. The worker takes 5–60 seconds to actually process and reply, but the user sees a "queued…" message immediately.

## 3.4 — Why dedup?

Meta's webhook delivery spec says "we retry up to 7 days on non-200." If our Lambda has a transient error, Meta re-sends the same message. Without dedup, the user gets their image twice. The DynamoDB table catches it.

```text
incoming wamid = wamid.ABC
       │
       ▼
try_claim(wamid.ABC) ─────► ConditionalCheckFailedException
       │                            │
       │                            └──► duplicate, drop
       │
       └──► True (new), process
```

`try_claim` is `PutItem` with `ConditionExpression="attribute_not_exists(pk)"`. The TTL of 7 days matches Meta's retry window.

## 3.5 — Why an S3 media bucket?

WhatsApp's media URLs expire in **5 minutes**. If the user sends a PDF and the Lambda needs 30 seconds to enqueue + the worker needs 5 minutes to process, the original URL is long dead. So the worker re-downloads from Meta at the moment of processing (the URL is still valid then because re-enqueueing is fast). But for **outbound** results (the converted PDF), the worker needs somewhere to put the file before sending the link. S3 with a presigned URL is the standard pattern.

The media bucket has a 1-day lifecycle: results are only needed while a job is in flight. After 24 hours, they're deleted by S3.

## 3.6 — Why two S3 buckets?

- `wactl-dev-media-<account_id>` — public access blocked, 1-day lifecycle, stores the inputs and outputs of commands. Small, ephemeral.
- `wactl-dev-releases-<account_id>` — public access blocked, holds `lambda.zip` and `worker.tar.gz` that CI uploads. CI is the only writer; the worker and Lambda download from here.

Splitting them lets you wipe media without re-deploying, and prevents the worker's downloads from competing with user-facing uploads.

## 3.7 — Why one SQS queue (not a per-command queue)?

One queue for all async commands. The worker pulls any message and dispatches based on the `command` field. Simpler than N queues, and ordering doesn't matter (each job is independent). The DLQ catches any that fail 5 times in a row.

## 3.8 — What's stored where

| Resource | Lives in | Read by | Written by |
|---|---|---|---|
| Inbound webhook payloads | Nowhere (transient) | Lambda | Meta |
| Inbound media | WhatsApp servers (URL valid 5 min) | Lambda (sync) or worker (async) | User (via WhatsApp) |
| Outbound artifacts | S3 media bucket (1 day TTL) | WhatsApp (via presigned URL) | Lambda or worker |
| Dedup records | DynamoDB (7-day TTL) | Lambda | Lambda |
| Async jobs | SQS jobs queue (4-day retention) | Worker | Lambda |
| Failed jobs | SQS DLQ (14-day retention) | Humans (via alarm) | SQS auto-route |
| Lambda code | S3 releases bucket (or directly inline in Terraform) | Lambda | CI |
| Worker code | S3 releases bucket | Worker (on first boot via cloud-init) | CI |
| WhatsApp credentials | SSM Parameter Store | Lambda, worker | Terraform (placeholder) + `aws ssm put-parameter` by human |
| Logs | CloudWatch log groups | Humans (CloudWatch console) | Lambda, worker |
| Alarms | CloudWatch metric alarms | Humans | Terraform |

## 3.9 — Trust boundaries

There are three trust boundaries WACTL cares about:

```text
   Public internet                 AWS account                 WACTL compute
   ───────────────                 ────────────                 ─────────────
   ┌─────────────┐                 ┌──────────┐                ┌──────────┐
   │ Meta        │ ──HTTPS + HMAC─►│ API GW   │ ──invokes───► │ Lambda   │
   │ (sender)    │                 │ (TLS)    │                │ (Python) │
   └─────────────┘                 └──────────┘                └──────────┘
                                          │                         │
                                          │                         │ IAM role
                                          │                         │ (lambda_exec)
                                          │                         ▼
                                          │                   ┌──────────┐
                                          │                   │ AWS APIs │
                                          │                   │ (S3, DDB,│
                                          │                   │  SQS,SSM)│
                                          │                   └──────────┘
                                          │                         ▲
                                          │                         │ IAM role
                                          │                         │ (worker)
                                          │                   ┌──────────┐
                                          │                   │ EC2      │
                                          │                   │ worker   │
                                          │                   └──────────┘
                                          │
                                          │ IAM role
                                          │ (gha-deploy, OIDC)
                                          │                   ┌──────────┐
                                          │                   │ GitHub   │
                                          │                   │ Actions  │
                                          │                   └──────────┘
```

- **Public internet ↔ AWS:** TLS via API Gateway. HMAC verifies the *content* came from Meta, not just the network.
- **AWS compute ↔ AWS APIs:** IAM roles. Lambda and EC2 have scoped policies that grant only the specific actions they need (least privilege).
- **GitHub ↔ AWS:** OIDC. GitHub issues a JWT signed by its OIDC provider; AWS validates the `sub` claim and issues short-lived STS credentials.

## 3.10 — Failure modes

| Failure | Effect | Recovery |
|---|---|---|
| Meta webhook → 500 | Meta retries for 7 days. | Lambda fixes the bug. |
| Lambda cold start | First request in a while is slow (~300ms). | Acceptable; AWS pre-warms containers that are invoked regularly. |
| Worker dies mid-job | SQS visibility timeout (15 min) expires; message reappears. | ASG launches a replacement; job is retried. |
| Job fails 5 times | SQS moves to DLQ. | CloudWatch alarm fires; humans inspect. |
| DynamoDB unavailable | `try_claim` fails. `_is_duplicate` returns `False` (fail open). | Possible duplicate processing; better than dropping. |
| S3 down | `put_object` raises `AWSIntegrationError`. | User sees "something went wrong" message. |
| WhatsApp API 429 | `tenacity` retries with `4^x` backoff. | Up to 3 attempts, then "try again" message. |
| GitHub Actions fails | Manual redeploy. | `gh workflow run deploy.yaml -f env=dev`. |
| Terraform apply breaks | `terraform plan` shows the diff; `terraform apply` aborts. | Inspect the error; fix; re-apply. |

## Next

→ [`04-folder-walkthrough.md`](04-folder-walkthrough.md) — every file in the repo, what it does.
