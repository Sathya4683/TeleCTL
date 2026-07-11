# 02 — Concepts Primer

This chapter defines every concept the rest of the textbook assumes you know. If you've never used AWS, Docker, Terraform, or async Python, read this first. If you have, skim the sections you're fuzzy on.

The order is deliberate: cloud → AWS primitives → network/HTTP → Python async → storage primitives → security → build/dev tooling.

---

## 2.1 — The cloud and AWS

### Cloud computing
Renting someone else's computers instead of buying your own. The provider (Amazon, Google, Microsoft) runs the physical hardware, the network, the power, the cooling, the OS patches — you run your code and pay by the second (or by request). For a personal project, the cost is cents/month; for a startup, it's still cheaper than hiring a data-centre team.

### Amazon Web Services (AWS)
The biggest cloud provider. AWS sells ~200 distinct services, each focused on one job. WACTL uses roughly 10 of them. Each service lives in one or more **regions** — a region is a separate geographic area (e.g. `ap-south-1` for Mumbai, `us-east-1` for Virginia). A region contains multiple **availability zones** (AZs) — physically separate data centres that can fail independently.

You authenticate to AWS with an **access key** (a long-lived secret) or, much better, with **OIDC** (an open standard for short-lived tokens, described later).

### The "free tier"
AWS offers a free usage tier for the first 12 months after you create an account, with smaller free-forever allowances for some services. WACTL is designed to stay within free tier for typical personal use. See [Chapter 9 — Data and storage](09-data-and-storage.md) and the [Chapter 11 — Infrastructure as code](11-infrastructure-as-code.md) notes for the specific allowances.

---

## 2.2 — AWS compute: Lambda and EC2

These are the two flavours of "run some code" on AWS.

### AWS Lambda (serverless)
You upload a zip of your code. AWS starts a tiny container, runs your function, and tears it down. You pay only for the milliseconds your code runs. Cold start (the time to spin up a fresh container) is ~100–500ms. Max run time is 15 minutes. Memory is 128 MB – 10 GB.

**When to use:** short, stateless, infrequent work. A webhook handler is the canonical example.

**The Lambda event:** when AWS invokes your function, it passes a JSON `event` (the request) and a `context` (metadata about the invocation). Your function returns a JSON response. For API Gateway integrations, the event has a specific shape documented in [Chapter 6 — Webhook Lambda](06-webhook-lambda.md).

```python
def lambda_handler(event, context):
    # event is a dict. context has aws_request_id, etc.
    return {"statusCode": 200, "body": "hello"}
```

### EC2 (virtual machines)
A virtual server you control entirely. Pick an instance type (CPU + RAM), pick an AMI (Amazon Machine Image — the OS + base software), and run it 24/7. Pay per hour (or per second, since 2017). Cold start = the boot time of the OS, ~30 seconds.

**When to use:** long-running processes, stateful workloads, jobs that take 10+ minutes.

**AMIs:** disk images. WACTL uses the Amazon Linux 2023 arm64 AMI for the worker (because the `t4g.nano` instance type is Graviton, which is arm64).

**Instance types:** a code like `t4g.nano` means: `t` (burstable CPU), `4g` (4th generation, Graviton), `nano` (smallest size — 2 vCPUs of burst budget, 512 MB RAM). `t4g.nano` is on the AWS free tier; `t4g.small` is not.

**Auto Scaling Group (ASG):** a group of EC2 instances that AWS keeps at a desired count. If one dies, ASG launches a replacement. The group can be told to keep `min=N, desired=N, max=M` instances. ASG pulls instance configuration from a **launch template** (instance type, AMI, security group, user data).

**User data:** a shell script (or cloud-config) that runs once when the instance first boots. WACTL's user data downloads the worker tarball from S3 and starts a `systemd` service.

**systemd:** Linux's init system. It manages long-running services, restarts them on failure, and reacts to `SIGTERM` for clean shutdown. A **unit file** (`/etc/systemd/system/<name>.service`) describes what to run, as which user, and what to do on stop.

### When to use which
- **Lambda:** stateless, < 15 min, spiky traffic, "set and forget" scale.
- **EC2:** stateful, long-lived, or compute-heavy with predictable load.

WACTL uses Lambda for the webhook and short commands, EC2 for the long-running worker that polls a queue.

---

## 2.3 — AWS storage: S3, DynamoDB, and SSM Parameter Store

### S3 (Simple Storage Service)
Object storage. You create **buckets** (names must be globally unique, like domain names). Each bucket holds **objects** identified by a **key** (a string path, e.g. `out/16505551234/wamid.123.png`). Objects are bytes — any type, up to 5 TB each.

You can:
- **PUT** an object (upload).
- **GET** an object (download).
- Generate a **presigned URL** — a temporary URL (valid for N seconds) that anyone can use to GET the object without AWS credentials. WACTL uses these to give WhatsApp a URL it can fetch the result media from.
- Set **lifecycle rules** — e.g. "delete objects after 1 day."
- **Block public access** — by default, no one can read a bucket without credentials. WACTL keeps media private and uses presigned URLs.

### DynamoDB
A key-value NoSQL database. You create **tables**; each table has a **primary key** (one or two attributes: partition key + optional sort key). Each row is an **item** (a JSON object). DynamoDB auto-scales — you don't pick a server size. Two billing modes:

- **On-demand (PAY_PER_REQUEST):** pay per request. Used in WACTL.
- **Provisioned:** pick a read/write capacity. Cheaper at high scale, but you must plan.

Two advanced features WACTL uses:
- **TTL (Time To Live):** a numeric attribute; DynamoDB deletes items whose TTL is in the past. Used for the dedup table — entries auto-expire after 7 days.
- **Conditional writes:** `PutItem` with a `ConditionExpression="attribute_not_exists(pk)"` is an atomic "create if not exists." Used to claim a wamid.

**Primary key in WACTL:** the dedup table has a single partition key `pk` (the wamid). No sort key.

### SSM Parameter Store
A managed key-value store for configuration. Two parameter tiers:
- **Standard:** free up to 10,000 parameters.
- **Advanced:** $0.05/parameter/month, larger size limit, parameter policies.

Each parameter has a **type**: `String`, `StringList`, or `SecureString`. `SecureString` values are encrypted with AWS KMS and decrypted on retrieval. WACTL uses **SecureString** parameters under `wactl/whatsapp/*` for the WhatsApp access token, app secret, and verify token.

SSM is fetched at runtime via `boto3.client("ssm").get_parameter(Name=..., WithDecryption=True)`.

> **Why SSM and not Secrets Manager?** Secrets Manager costs $0.40/secret/month; SSM Standard is free. For a personal project, that's $1.20/month saved for negligible functional difference. See [`docs/DECISIONS.md`](../DECISIONS.md) for the original rationale and the migration history.

---

## 2.4 — AWS networking: API Gateway, OIDC, IAM, CloudWatch

### API Gateway
A managed HTTPS front door. You create a **REST API** or an **HTTP API**, define **resources** (URL paths like `/webhook`), **methods** (HTTP verbs like `GET`/`POST`), and **integrations** (what to do when a method is called — usually invoke a Lambda). API Gateway handles TLS, request validation, and (for REST) binary media support.

WACTL uses REST API specifically for **binary media types** — Meta sometimes sends binary payloads, and REST API can pass them through transparently to Lambda. HTTP API would force base64 encoding.

### IAM (Identity and Access Management)
The AWS auth/authorisation system. Two key concepts:

- **Role** — an identity that AWS services (Lambda, EC2, etc.) can *assume*. A role has a **trust policy** (who can assume it) and one or more **permission policies** (what it can do).
- **Policy** — a JSON document listing `Action`s (e.g. `s3:PutObject`) on `Resource`s (ARNs).

WACTL has three roles: one for the Lambda (`lambda_exec`), one for the worker EC2 instance (`worker`), and one for GitHub Actions CI (`github_actions`).

**Instance profile** — a wrapper around a role that lets an EC2 instance assume it. The instance gets temporary credentials via the Instance Metadata Service (IMDS).

**OIDC (OpenID Connect)** — an open standard for federated identity. Instead of long-lived AWS access keys, a GitHub Actions workflow can ask AWS "I am a job running on the `main` branch of repo `owner/wactl`" and get short-lived credentials (typically valid for 1 hour). WACTL uses this — no AWS keys in the repo or in GitHub Secrets.

### CloudWatch
AWS's logging + metrics + alarms system. WACTL creates:

- **Log groups** — one per Lambda (`/aws/lambda/<name>`) and one for the worker (`/wactl/<env>/worker`). Logs are JSON lines, retained 30 days.
- **Metrics alarms** — e.g. "DLQ depth > 0" or "Lambda errors > 0 in 1 minute." These can send to SNS or just sit in the dashboard.

---

## 2.5 — Messaging: SQS

### SQS (Simple Queue Service)
A managed message queue. The basic abstraction:

- A **queue** holds **messages** (JSON blobs, up to 256 KB each).
- A **producer** *sends* a message.
- A **consumer** *receives* a message, processes it, and either *deletes* it (success) or lets it **time out** (failure → message reappears).

WACTL uses SQS for async commands: the Lambda *sends* a `Job` envelope; the worker *receives*, *processes*, and *deletes* on success.

### Visibility timeout
When a consumer receives a message, SQS marks it as "invisible" for N seconds (the **visibility timeout**). If the consumer doesn't delete it within that window, the message reappears for the next receive. WACTL sets this to 900s (15 min) — the maximum Lambda timeout, giving the worker enough headroom for slow jobs.

### Long polling
The consumer can ask SQS to **wait** up to 20 seconds for messages instead of returning immediately if empty. This is cheaper (fewer API calls) and gives lower average latency. WACTL uses 20s long polling.

### Standard vs FIFO
- **Standard queue:** at-least-once delivery, no ordering, unlimited throughput.
- **FIFO queue:** exactly-once, ordered, capped at 300 messages/sec (with batching).

WACTL uses **Standard** — see [ADR-004](../DECISIONS.md#adr-004--sqs-standard-not-fifo). Duplicates are caught by the dedup table; ordering doesn't matter because each job is independent.

### Dead-letter queue (DLQ)
A secondary queue that receives messages which fail too many times. SQS auto-routes after `maxReceiveCount` (5 in WACTL). WACTL's `wactl-dev-jobs-dlq` is the DLQ for `wactl-dev-jobs`.

---

## 2.6 — HTTP, REST, and webhooks

### HTTP
The protocol the web runs on. A request has:
- A **method** (`GET`, `POST`, `PUT`, `DELETE`, ...).
- A **path** (e.g. `/webhook`).
- **Headers** (key-value metadata like `Content-Type`).
- A **body** (the payload — JSON, form data, binary, etc.).

A response has a **status code** (200 = OK, 4xx = client error, 5xx = server error), headers, and a body.

### REST
A convention for structuring HTTP APIs around "resources" (nouns) and "methods" (verbs). `GET /users/123` reads user 123; `POST /users` creates one. WACTL's API Gateway is a small REST API: one resource `/webhook` with two methods (GET for handshake, POST for messages).

### Webhook
A URL that one service POSTs to when something happens. The receiver should:
1. Be reachable on the public internet.
2. Verify the sender (usually with a signature header).
3. Respond fast (the sender may have a tight timeout).
4. Be idempotent (the sender may retry).

WACTL is a webhook **receiver** — Meta POSTs every WhatsApp message to `/webhook`. WACTL is also a webhook **sender** of sorts, calling the WhatsApp Cloud API to reply.

### JSON
JavaScript Object Notation. The lingua franca of HTTP APIs. WACTL uses `pydantic` models to validate JSON shapes.

---

## 2.7 — HMAC: signature verification

When a webhook needs to prove "this really came from sender X," the sender signs the body with a shared secret and the receiver verifies.

**HMAC-SHA256** (Hash-based Message Authentication Code with SHA-256) is the standard. Both sides know the same secret. To sign:

```python
import hashlib, hmac
sig = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
# Header value: "sha256=" + sig
```

To verify, recompute the HMAC and compare in constant time (so attackers can't time-side-channel the comparison).

```python
expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
hmac.compare_digest(expected, provided)  # constant-time
```

WACTL does this in `src/wactl/webhook.py:87` (and a duplicate helper in `src/wactl/integrations/whatsapp/signature.py`). Meta uses the same scheme — see [Chapter 6](06-webhook-lambda.md) for the wire format.

---

## 2.8 — Async Python

Python has two flavours of concurrency:
- **Threading:** OS threads, one per concurrent task. Subject to the GIL (only one thread runs Python bytecode at a time). Good for I/O-bound work.
- **Async (`asyncio`):** single-threaded, cooperative multitasking. You `await` coroutines; while one is waiting on I/O, another runs. Much cheaper than threads for thousands of concurrent operations.

WACTL uses `asyncio` because most of its work is I/O-bound (HTTP to Meta, S3, SQS, DynamoDB). Every command is an `async def run(self, ctx) -> CommandResponse`.

**Key concepts:**
- `async def` defines a coroutine function.
- `await` yields control until the awaited thing completes.
- `asyncio.run(coro)` is the entry point — it runs the coroutine to completion.
- `asyncio.gather(*coros)` runs many coroutines concurrently.
- `asyncio.to_thread(fn, ...)` runs a blocking function in a thread (WACTL uses this for `boto3` calls, which are synchronous).

**Why this matters in WACTL:**
- The Lambda handler is `asyncio.run(_handle_post_async(...))` — one event loop per invocation.
- The worker has a long-running event loop that sleeps on SQS.
- The same `CommandContext` is passed through both.

---

## 2.9 — Python tooling

### `uv`
A fast Python package manager (replacement for `pip` + `venv` + `poetry`). The repo uses it because it's much faster than pip and handles the dependency lockfile (`uv.lock`) cleanly.

```bash
uv sync                  # install from lockfile into .venv
uv run pytest tests -q   # run a command in the venv
uv add <pkg>             # add a dep
```

### `pyproject.toml`
The standard Python project config file (PEP 621). Holds metadata, dependencies, dev dependencies, and tool configs. WACTL's `pyproject.toml` configures `ruff`, `mypy`, and `pytest`.

### `ruff`
A fast linter + formatter (Rust-based, replaces flake8 + isort + black + pyupgrade). The config in `pyproject.toml` enables ~15 rule families (`E`, `W`, `F`, `I`, `B`, `UP`, `SIM`, `ASYNC`, `RUF`, `C4`, `PIE`, `PT`, `RET`, `PL`, `TID`).

### `mypy`
The reference Python type checker. The config sets `strict = true` — every annotation matters, implicit `Optional` is forbidden, etc. The `pydantic.mypy` plugin validates Pydantic model definitions at type-check time.

### `pytest`
The de-facto Python test framework. WACTL uses:
- `pytest-asyncio` to run `async def` tests.
- `respx` to mock `httpx` calls.
- `moto` to mock AWS services.
- `freezegun` to mock time.

### `boto3`
The official AWS SDK for Python. Synchronous by default; WACTL wraps it in `asyncio.to_thread` for non-blocking calls.

### `pydantic`
The data validation library. You define a class with typed fields; Pydantic validates JSON / dicts into the class. WACTL uses Pydantic v2 with `BaseModel` + `Field` + `ConfigDict(frozen=True)` for immutable models.

### `structlog`
A structured logging library. Logs are JSON objects, not strings. Each line is one event with all its key-value fields. Designed for log aggregators (CloudWatch, Datadog, etc.) that index by field.

---

## 2.10 — Containerisation: Docker

A **Docker container** is a lightweight, portable bundle of code + dependencies + a minimal OS layer. WACTL uses Docker to build the worker release tarball — the Dockerfile compiles a Python virtual environment with all dependencies and packages it as `worker.tar.gz`.

```dockerfile
FROM python:3.12-slim
WORKDIR /src
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv export ... > /tmp/requirements.txt
RUN uv pip install --target /out/packages -r /tmp/requirements.txt
COPY src ./src
RUN cp -r src/wactl /out/packages/wactl
RUN tar -czf /out/worker.tar.gz packages
```

A **Dockerfile** is a recipe. `docker build` runs it; `docker create` makes a stopped container from the image; `docker cp` extracts files. The final `scratch` stage in WACTL's Dockerfile produces an image that contains only the tarball (no OS), which is then extracted to disk.

---

## 2.11 — Infrastructure as Code: Terraform and HCL

### The problem
AWS has hundreds of services, each with dozens of settings. Clicking through the console to set up resources is fine once; it's a disaster the third time (and impossible for a team).

### The solution
Write a declarative description of what you want. A tool applies it and shows you the diff. This is **Infrastructure as Code (IaC)**.

### Terraform
The most popular IaC tool. The language is **HCL (HashiCorp Configuration Language)** — a simple JSON-like syntax.

```hcl
resource "aws_s3_bucket" "media" {
  bucket = "${var.project_name}-${var.env}-media-${data.aws_caller_identity.current.account_id}"
}
```

Key concepts:
- **Resource:** a piece of infrastructure (a bucket, a Lambda, a role).
- **Provider:** the plugin that knows how to talk to a cloud (here, `hashicorp/aws`).
- **State:** Terraform's record of what it created. Stored in S3 for WACTL so the team shares it.
- **Plan:** the diff between current state and desired state. `terraform plan` shows it; `terraform apply` makes it real.
- **Variables / outputs:** parameterise the config; expose values for other tools to use.
- **Locals:** computed values shared across files.
- **Data sources:** read existing infrastructure (like your AWS account ID).

### The workflow
```bash
cd infra
terraform init                              # download providers
terraform plan -var env=dev                 # show what would change
terraform apply -var env=dev -auto-approve  # do it
```

`init` is the one-time setup; `plan` and `apply` are the iterative loop.

---

## 2.12 — CI/CD and OIDC

**CI (Continuous Integration):** every push to GitHub automatically runs lint, type-check, and tests. Catches breakage early.

**CD (Continuous Deployment):** every push to `main` automatically builds the Lambda zip + worker tarball, uploads them to S3, and runs `terraform apply`.

### GitHub Actions
A YAML-defined CI/CD runner. Workflows live in `.github/workflows/`. Each workflow has triggers (`on:`) and jobs (containers that run steps). WACTL has three:
- `ci.yaml` — runs on PR and push to main: ruff, mypy, pytest.
- `deploy.yaml` — runs on push to main: build artifacts, terraform apply.
- `deploy-frontend.yaml` — runs on changes to `web/`: deploy to Vercel.

### OIDC for AWS
GitHub has an OIDC provider. AWS can trust it. WACTL's Terraform creates:
1. An `aws_iam_openid_connect_provider` for `token.actions.githubusercontent.com`.
2. A role whose trust policy says "only allow the role to be assumed if the token's `sub` claim matches `repo:owner/wactl:ref:refs/heads/main`."

In a workflow step:
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::123:role/wactl-dev-gha-deploy
    aws-region: us-east-1
```

GitHub exchanges a JWT for a short-lived AWS access key, valid for 1 hour. No long-lived secrets in the repo.

---

## 2.13 — The front-end: Next.js + Tailwind

WACTL ships a marketing site at the repo root `web/`. It's a **Next.js 16** app (React framework with server components) styled with **Tailwind v4**. The site is a single page with a "Get the bot" link, a list of commands, and a "how it works" section.

It deploys to **Vercel** (Next.js's creator) automatically via a separate GitHub Actions workflow when `web/**` changes.

---

## 2.14 — Other terms you'll see

- **WAMID** — WhatsApp Message ID. A unique string per message, e.g. `wamid.HBgLMTY1MDU1NTEyMzQ1NhUCABEYEjR....`. Used as the dedup key.
- **S3 presigned URL** — a time-limited URL that grants GET/PUT access to a private object without AWS credentials.
- **DTO / value object** — a small class that holds data and is passed between layers. `UserContext`, `Job`, `CommandResponse` are all DTOs in WACTL.
- **Process global / module-level singleton** — a Python object created at import time and shared by the whole process. WACTL uses these for the boto3 clients (one client per process, reused).
- **Decorator** — Python syntax (`@register("/image-resize")`) that wraps a class/function. The registry pattern is just decorators + a dict.
- **Discriminated union** — a type that can be one of several variants, identified by a field. Pydantic's `Field(discriminator="type")` makes `TextMessage | MediaMessage` work cleanly.
- **Conditional write** — a DynamoDB `PutItem` with `ConditionExpression`. The write only succeeds if the condition is met; otherwise the API returns `ConditionalCheckFailedException`.

---

## Next

→ [`03-architecture.md`](03-architecture.md) — the system architecture with the full diagram explained.
