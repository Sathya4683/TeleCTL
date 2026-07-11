# WACTL — A Complete Codebase Textbook

> **Audience:** an engineer who has used Python but never touched AWS, Terraform, Docker, or message queues.
> **Goal:** by the time you finish reading these files linearly, you should be able to navigate any file in the repo, predict where a new feature would live, and run the whole stack locally.

---

## How to read this

The chapters are ordered to build up mental model before details. If you already know what AWS Lambda, S3, and SQS are, you can skip Chapter 2 (AWS primer) and skim Chapter 4 (tooling primer). If you've never used Terraform, read Chapter 11 (infrastructure-as-code) before you touch `infra/`.

| # | File | What's in it |
|---|------|--------------|
| 1 | [`01-introduction.md`](01-introduction.md) | What WACTL is, the problem it solves, the user, the value prop. |
| 2 | [`02-concepts-primer.md`](02-concepts-primer.md) | Every concept you need: cloud, AWS services, async Python, HTTP, webhooks, HMAC, queues, Docker, IaC, CI/CD. |
| 3 | [`03-architecture.md`](03-architecture.md) | The system diagram. How Lambda, SQS, the worker, and storage fit together. |
| 4 | [`04-folder-walkthrough.md`](04-folder-walkthrough.md) | Every file in the repo, what it does, and why it lives where it lives. |
| 5 | [`05-end-to-end-flow.md`](05-end-to-end-flow.md) | Trace a real user message — `/image-resize 800x600` with a photo — from "user taps send" to "user receives the resized image." |
| 6 | [`06-webhook-lambda.md`](06-webhook-lambda.md) | The Lambda in detail: HMAC, parsing, dedup, routing, dispatch. |
| 7 | [`07-commands.md`](07-commands.md) | The command registry pattern + a walkthrough of every command. |
| 8 | [`08-worker.md`](08-worker.md) | The EC2 worker: long-polling SQS, graceful shutdown, systemd, the Docker build. |
| 9 | [`09-data-and-storage.md`](09-data-and-storage.md) | S3, DynamoDB, and SSM Parameter Store — what's stored where and why. |
| 10 | [`10-external-services.md`](10-external-services.md) | WhatsApp Cloud API, Gemini (text + TTS), GitHub, the public web. |
| 11 | [`11-infrastructure-as-code.md`](11-infrastructure-as-code.md) | The Terraform setup, every `*.tf` file explained. |
| 12 | [`12-security-and-iam.md`](12-security-and-iam.md) | IAM roles, OIDC for CI/CD, HMAC verification, secret handling. |
| 13 | [`13-frontend.md`](13-frontend.md) | The Next.js site — landing page, docs, privacy/terms. |
| 14 | [`14-local-development.md`](14-local-development.md) | Install deps, run tests, run the worker locally against real AWS. |
| 15 | [`15-testing.md`](15-testing.md) | pytest, moto, respx, the fake helpers, the test patterns. |
| 16 | [`16-deployment-and-cicd.md`](16-deployment-and-cicd.md) | GitHub Actions, OIDC, how a push to `main` reaches production. |
| 17 | [`17-observability.md`](17-observability.md) | Structured logging, CloudWatch, the alarms, the scheduled cleanup. |
| 18 | [`18-glossary.md`](18-glossary.md) | Every acronym and term used elsewhere, defined. |

## Conventions used in these files

- **Code blocks** — every snippet is real code from the repo. Line numbers are shown for longer files so you can jump to the same place in your editor.
- **"What" vs "Why"** — the "what" is the API or behavior; the "why" is the design rationale (cross-referenced with the ADRs in `docs/DECISIONS.md`).
- **Links to source** — paths are relative to the repo root. If you see `src/wactl/webhook.py:87`, that's `webhook.py` line 87.

## When something doesn't make sense

Open `docs/CODEBASE_GUIDE.md` (the original short tour) for a 20-minute overview, or `docs/DECISIONS.md` for the "why we picked X over Y" reasoning on each architectural call. The textbook goes deeper; the guide is the elevator pitch.
