# 01 — Introduction: What is WACTL?

WACTL is **"WhatsApp Control"** — a small but production-grade platform that turns a WhatsApp chat into a Swiss-army knife for personal tooling. You DM a number, type a slash command like `/pdf-docx`, attach a file, and you get the processed file back in chat.

```text
You                          Meta (WhatsApp)                 WACTL (this codebase)
───                          ───────────────                 ─────────────────────
1. Open chat, type           "Hey, here's an event"
   /image-resize 800x600
   + attach photo.jpg
                             2. POST signed JSON ──────►   3. API Gateway → Lambda
                                                              • verify HMAC
                                                              • dedup by wamid
                                                              • look up /image-resize
                                                              • resize the photo
                                                              • upload to S3
                                                              • send reply
                             4. ◄────── push reply ───────   5. WhatsApp delivers image
6. See the resized image
```

That's the entire product, end-to-end. The codebase is the production plumbing that makes step 3 reliable, fast, and cheap.

## Why does it exist?

Three problems that WACTL solves with one design:

1. **The "no app to install" problem.** Most personal-tooling apps (image resizers, PDF tools, summarisers) force the user to install an app or create an account. WhatsApp is already on every phone with internet. The interface is the chat the user already has open.

2. **The "one workflow" problem.** Common tools (resize, compress, convert, summarise) are scattered across apps. A slash-command surface unifies them with a consistent mental model: `type /x, attach stuff, get result`.

3. **The "cheap to run" problem.** A single EC2 `t4g.nano` (free tier) and a few Lambda invocations a day can serve hundreds of users. The whole platform runs for under $1/month at personal scale.

## What it actually does (the surface area)

A user can do any of the following by sending a WhatsApp message to the WACTL business number:

| Command | What it does | Sync or Async |
|---|---|---|
| `/image-resize 800x600` | Resize an attached image to fit 800×600. | Sync (Lambda) |
| `/image-compress q=70 max=1600` | Recompress an image to a target quality. | Sync (Lambda) |
| `/pdf-docx` | Convert an attached PDF to a Word document. | Async (EC2 worker) |
| `/pdf-audio` | Read a PDF aloud as one audio message. | Async (EC2 worker) |
| `/merge-pdf` | Concatenate several PDFs into one. | Async (EC2 worker) |
| `/split-pdf 1-3,5` | Split a PDF by page ranges. | Async (EC2 worker) |
| `/web-summary <url>` | Fetch a URL and reply with a 400-word summary. | Sync (Lambda) |
| `/github-pr <url>` | Summarise a GitHub PR's diff. | Sync (Lambda) |
| `/translate es <text>` | Translate text or an attached PDF to a target language. | Sync (Lambda) |
| `/help` | List all commands. | (TBD — currently responds with hint) |

The "sync" commands finish within the Lambda's 60-second budget. The "async" commands would exceed that (PDF→audio on a 30-page doc takes 60+ seconds), so they get queued and processed by a long-running worker.

## The technical shape

```text
┌────────────┐   HTTPS   ┌──────────────┐   invoke   ┌─────────────┐
│   Meta     │ ────────► │ API Gateway  │ ────────► │  Lambda     │
│  WhatsApp  │            │  (REST API)  │            │  webhook    │
└────────────┘            └──────────────┘            └──────┬──────┘
     ▲                                                      │
     │                                                      │   sync
     │                                                      │   command?
     │                                                      ▼
     │                          ┌────────────┐         ┌──────────┐
     │                          │  S3 media  │ ◄─────► │ command  │
     │                          │   bucket   │  put/   │   code   │
     │                          └────────────┘  presign└──────────┘
     │                              ▲                  │
     │                              │  presigned URL   │
     │       push media reply       │                  │
     │ ◄────────────────────────────┴──────────────────┘
     │                              ▲
     │       push text reply        │  enqueue
     │ ◄────────────────────────────┘  (async only)
     │                              ┌──────────────┐
     │                              │   SQS jobs   │
     │                              │     queue    │
     │                              └──────┬───────┘
     │                                     │ long-poll
     │                                     ▼
     │                              ┌──────────────┐
     │                              │   EC2 worker │
     │                              │  (t4g.nano)  │
     │                              └──────────────┘
     │
     └───── WhatsApp Cloud API (graph.facebook.com) ──────┘
```

Two compute surfaces (Lambda + EC2), two storage surfaces (S3 for media, DynamoDB for dedup), one queue (SQS) in between, and the WhatsApp Cloud API for both inbound webhooks and outbound replies. That's it. No databases beyond DynamoDB, no container orchestrators, no service mesh.

## Who is this codebase for?

The WACTL project itself is a portfolio piece — see `README.md` and `AUTHORS.md`. As a codebase, it's interesting because it's a clean, idiomatic example of:

- A **serverless + EC2 hybrid** architecture
- The **plugin / decorator registry** pattern for extensibility
- A **strict Python 3.12** project (mypy strict, ruff lint, pytest)
- **CI/CD with OIDC** (no long-lived AWS keys in the repo)
- **Production observability** (structured JSON logs, CloudWatch alarms, a DLQ)

The textbook is meant to let a relative newcomer read every file with confidence.

## Next

→ [`02-concepts-primer.md`](02-concepts-primer.md) — every concept you need to understand before touching the code.
