<p align="center">
  <img src="https://github.com/user-attachments/assets/8bf73067-7374-4cec-b6fe-5b103a978f26" width="423" height="385" alt="WACTL logo" />
</p>

<h1 align="center">WACTL</h1>
<p align="center"><strong>WhatsApp Control</strong></p>

<p align="center">
  A WhatsApp bot that turns slash commands into file conversions, summaries, and translations, backed by a small AWS serverless and EC2 hybrid.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square" alt="License: MIT" />
  <img src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12" />
  <img src="https://img.shields.io/badge/tests-~230%20passing-2ea44f?style=flat-square" alt="Tests" />
</p>

---

## Contents

- [The problem](#the-problem)
- [The idea](#the-idea)
- [What it can do](#what-it-can-do)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Testing](#testing)
- [Deployment](#deployment)
- [Security](#security)
- [Observability](#observability)
- [Cost](#cost)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## The problem

Most weeks, you run into some version of the following:

- Someone sends you a PDF and you need it as an editable Word doc, but you're on your phone with no app open for that.
- A long article or a wall of screenshots lands in a chat and you just want the two-line summary.
- You want to know if your pull request got reviewed, without opening GitHub.
- A textbook chapter needs to become something you can listen to on a walk.
- A document is in a language you don't read, and you need it translated before a meeting.

Almost all of this shows up as a file, a link, or a message inside WhatsApp itself. Solving it usually means leaving the chat, opening a handful of other apps, and coming back with the result.

## The idea

WACTL turns WhatsApp into the interface. Send a slash command, attach a file if the command needs one, and the bot replies in the same chat. `/pdf-docx` with a PDF attached gets you back a Word document. `/web-summary <url>` gets you a summary. No separate app to install, no new account, no tab switching. If the file or link is already in WhatsApp, the fix stays in WhatsApp too.

Underneath, it's a small production-shaped AWS backend: a webhook Lambda for anything that finishes in a couple of seconds, and a single EC2 worker for anything that doesn't.

## What it can do

| Command | What it does | Runs on |
|---|---|---|
| `/image-resize <WxH>` | Resize an attached image to fit given dimensions | Lambda (sync) |
| `/image-compress q= max= target=` | Recompress an image to a target quality or size | Lambda (sync) |
| `/pdf-docx` | Convert an attached PDF into a Word document | Worker (async) |
| `/pdf-audio` | Turn a PDF into a spoken audio file | Worker (async) |
| `/merge-pdf` | Combine several PDFs into one | Worker (async) |
| `/split-pdf <ranges>` | Split a PDF by page range, e.g. `1-3,5` | Worker (async) |
| `/web-summary <url>` | Fetch a page and reply with a short summary | Lambda (sync) |
| `/github-pr <url>` | Summarize a GitHub pull request's diff | Lambda (sync) |
| `/translate <lang> <text/pdf>` | Translate text or an attached PDF | Lambda (sync) |
| `/help` | List available commands | Lambda (sync) |

Sync commands run inline in the Lambda and finish in a couple of seconds. Anything that would run longer, like converting a 200-page PDF into audio, gets queued and picked up by the worker instead, so the user isn't left waiting on an open HTTP request.

## Architecture

WACTL runs across two compute surfaces (a webhook Lambda and a long-running EC2 worker), two storage surfaces (S3 for media, DynamoDB for webhook dedup) and one queue (SQS) in between. Fast commands are handled inline by the Lambda; slow ones are enqueued and drained by the worker. The WhatsApp Cloud API is the entry and exit point for every message.

<!-- architecture diagram goes here -->

## Tech stack

**Backend**

A single Python 3.12 package shared by the Lambda and the worker, with strict typing and linting enforced in CI.

<p align="center"><img src="https://img.shields.io/badge/Python-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python" /></p>

Notable libraries: pydantic and pydantic-settings for config and validation, structlog for structured logging, httpx with tenacity for retries and backoff, boto3 for AWS access, and Pillow, pdf2docx, PyMuPDF, pypdf, and pydub for the actual file conversions.

**Cloud & infrastructure**

Lambda handles the fast synchronous commands. A single EC2 worker long-polls SQS for everything else. S3 stores media, DynamoDB tracks dedup, and Terraform manages every resource in between.

<p align="center">
  <img src="https://img.shields.io/badge/AWS_Lambda-FF9900?style=flat-square&logo=awslambda&logoColor=white" alt="AWS Lambda" />&nbsp;<img src="https://img.shields.io/badge/Amazon_S3-569A31?style=flat-square&logo=amazons3&logoColor=white" alt="Amazon S3" />&nbsp;<img src="https://img.shields.io/badge/DynamoDB-4053D6?style=flat-square&logo=amazondynamodb&logoColor=white" alt="Amazon DynamoDB" />&nbsp;<img src="https://img.shields.io/badge/Amazon_SQS-FF4F8B?style=flat-square&logo=amazonsqs&logoColor=white" alt="Amazon SQS" />&nbsp;<img src="https://img.shields.io/badge/Amazon_EC2-FF9900?style=flat-square&logo=amazonec2&logoColor=white" alt="Amazon EC2" />&nbsp;<img src="https://img.shields.io/badge/Terraform-7B42BC?style=flat-square&logo=terraform&logoColor=white" alt="Terraform" />&nbsp;<img src="https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker" />
</p>

**Integrations**

Gemini handles summarization, translation, and text-to-speech. The WhatsApp Cloud API is used for both inbound webhooks and outbound replies. GitHub's REST API powers the PR summaries.

<p align="center">
  <img src="https://img.shields.io/badge/Google_Gemini-886FBF?style=flat-square&logo=googlegemini&logoColor=white" alt="Google Gemini" />&nbsp;<img src="https://img.shields.io/badge/WhatsApp_Cloud_API-25D366?style=flat-square&logo=whatsapp&logoColor=white" alt="WhatsApp Cloud API" />&nbsp;<img src="https://img.shields.io/badge/GitHub_API-181717?style=flat-square&logo=github&logoColor=white" alt="GitHub API" />
</p>

**Frontend**

A statically generated marketing site: a landing page, a command reference, and the privacy and terms pages the WhatsApp Business API requires.

<p align="center">
  <img src="https://img.shields.io/badge/Next.js_16-000000?style=flat-square&logo=nextdotjs&logoColor=white" alt="Next.js" />&nbsp;<img src="https://img.shields.io/badge/React_19-20232A?style=flat-square&logo=react&logoColor=61DAFB" alt="React" />&nbsp;<img src="https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white" alt="TypeScript" />&nbsp;<img src="https://img.shields.io/badge/Tailwind_CSS_v4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" alt="Tailwind CSS" />&nbsp;<img src="https://img.shields.io/badge/Vercel-000000?style=flat-square&logo=vercel&logoColor=white" alt="Vercel" />
</p>

**Testing & delivery**

About 230 tests run in roughly 10 seconds with AWS and HTTP fully mocked. GitHub Actions runs CI on every push and deploys on merge to `main`, authenticating to AWS through OIDC instead of long-lived keys.

<p align="center">
  <img src="https://img.shields.io/badge/Pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white" alt="Pytest" />&nbsp;<img src="https://img.shields.io/badge/GitHub_Actions-2088FF?style=flat-square&logo=githubactions&logoColor=white" alt="GitHub Actions" />
</p>

Notable libraries: moto and respx mock AWS and HTTP in tests, freezegun freezes time for TTL checks, and ruff plus mypy (strict mode) enforce lint rules and full type coverage. Dependencies are managed with [uv](https://docs.astral.sh/uv/).

## Project structure

```
wactl/
├── src/wactl/          # the core package (config, logging, webhook, router, dispatcher)
│   ├── commands/        # one file per slash command, registered via a decorator
│   ├── models/          # pydantic value objects
│   ├── integrations/    # aws, whatsapp, gemini, github, converters, web
│   └── services/        # multi-step workflows (e.g. the audiobook pipeline)
├── lambda/webhook/      # the Lambda entry point
├── worker/              # the EC2 worker: long-poll SQS, dispatch, systemd unit
├── infra/               # Terraform for every AWS resource
├── web/                 # the Next.js marketing site
├── tests/               # unit and integration tests (pytest, moto, respx)
├── docs/                # this README, ADRs, and an 18-chapter deep-dive textbook
└── .github/workflows/   # CI, deploy, and frontend-deploy pipelines
```

## Getting started

Prerequisites: Python 3.12, [uv](https://docs.astral.sh/uv/), Node.js 20+ (only needed for `web/`), and Docker if you want to build the worker image locally.

```bash
git clone https://github.com/sathya-narayanan/wactl.git
cd wactl

# install Python dependencies
uv sync

# copy and fill in environment variables
cp .env.example .env

# run the test suite
uv run pytest

# lint and type-check
uv run ruff check .
uv run mypy src/wactl
```

The unit tests don't need AWS credentials. Every AWS and HTTP call is mocked. To run the frontend locally:

```bash
cd web
npm install
npm run dev
```

Deploying to a real AWS account requires Terraform:

```bash
cd infra
terraform init
terraform plan
terraform apply
```

## Testing

Around 230 tests run in about 10 seconds, with no live AWS calls or network requests anywhere in the suite. `moto` mocks AWS, `respx` mocks HTTP, and `freezegun` freezes time where TTL logic depends on it. Every command is tested by constructing a `CommandContext` with fake WhatsApp and S3 clients through dependency injection, so no test needs real credentials.

## Deployment

Three GitHub Actions workflows handle everything:

- `ci.yaml` runs ruff, mypy, and pytest on every push and pull request.
- `deploy.yaml` builds the Lambda package and worker image, uploads them to S3, and runs `terraform apply` on pushes to `main`.
- `deploy-frontend.yaml` builds and deploys the `web/` site to Vercel when files under `web/` change.

CI authenticates to AWS through OIDC: GitHub issues a short-lived token that AWS exchanges for temporary credentials, so no long-lived AWS keys sit in GitHub secrets.

## Security

- Every inbound webhook is verified against Meta's `X-Hub-Signature-256` HMAC header before it's processed.
- IAM roles are scoped per component: the Lambda, the worker, and the CI pipeline each get only the permissions they need.
- WhatsApp and Gemini credentials live in SSM Parameter Store as SecureStrings, never in code or plain environment files.
- Both S3 buckets block all public access.
- The webhook always returns 200 to Meta, even on internal failure, so retries don't leak details about what went wrong.

## Observability

Every log line is a structured JSON object, queryable through CloudWatch Logs Insights instead of grepping plain text. Three CloudWatch alarms watch for a non-empty dead-letter queue, Lambda errors, and sustained worker CPU.

## Cost

The whole platform runs on a single EC2 `t4g.nano` instance (AWS free tier) plus a handful of Lambda invocations a day. At personal scale, that's under a dollar a month.

## Documentation

`docs/textbook/` has an 18-chapter deep dive: the architecture, the folder structure, the webhook and worker in detail, infrastructure as code, security, testing, and deployment. This README is the short version; the textbook is the long one.

## Contributing

See `CONTRIBUTING.md` for conventions on branches, commits, and pull requests. New commands are the most common contribution: drop a file in `src/wactl/commands/`, register it with the `@register` decorator, add a test, and open a PR.

## License

MIT. See `LICENSE`.
