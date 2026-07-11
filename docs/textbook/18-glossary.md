# 18 — Glossary

Every term used in this textbook, defined once. Use Ctrl-F (or your reader's search) to find a term; the definition here is the canonical one.

## A

**API Gateway** — AWS service that exposes HTTP(S) endpoints. WACTL uses it to receive webhooks from Meta and forward them to the Lambda.

**ASG (Auto Scaling Group)** — EC2 feature that maintains a desired number of instances. Replaces unhealthy ones automatically. WACTL uses one for the worker (min 1, max 2).

**Async command** — A slash command that takes too long to run in the Lambda; the Lambda enqueues it to SQS and the worker processes it later. `/pdf-docx`, `/pdf-audio`, `/merge-pdf`, `/split-pdf` are async.

**Async context manager** — Python `async with` statement. Used in WACTL for binding log context (`@asynccontextmanager async def _job_context(job)`).

**Async generator** — A Python function that uses `yield` inside `async def` and is iterated with `async for`. Not used heavily in WACTL.

**Asyncio** — Python's standard library for async I/O. WACTL uses it for the Lambda's webhook handler and the worker's main loop.

**Asyncio.to_thread** — Runs a blocking sync function in a thread pool, returning an awaitable. WACTL uses it to call sync SDKs (boto3's sync methods, google-genai's sync methods) without blocking the event loop.

**Attachment** — A file sent in a WhatsApp message (image, document, audio, video, sticker). The webhook envelope contains a `media_id`; the actual bytes are fetched via a separate API call.

**Audit log** — A record of who did what when. AWS services emit these to CloudTrail. SSM Parameter Store access is logged in CloudTrail.

**Auth (Authentication)** — Proving who you are. In WACTL, the HMAC signature is the auth for inbound webhooks; IAM is the auth for AWS API calls.

**Availability** — The property that a system responds to requests. WACTL favors availability over consistency (e.g. fail-open dedup).

**AWS** — Amazon Web Services. The cloud platform WACTL runs on.

**AWSLambda** — The service that runs WACTL's webhook handler. Billed per ms; max 15-min runtime.

## B

**Bcrypt** — Password hashing algorithm. Not used in WACTL.

**Boto3** — The AWS SDK for Python. WACTL uses it for all AWS service calls (S3, SQS, DynamoDB, SSM).

**Botocore** — The lower-level library boto3 is built on. WACTL uses its `ClientError` exception.

**Build artifact** — The output of a build step. WACTL has two: `lambda.zip` (the Lambda deployment) and `worker.tar.gz` (the worker deployment).

**Bullet points** — Markdown's `-` or `*` lists. Used in WACTL's responses to make summaries scannable.

## C

**Cache** — A local copy of a value to avoid re-fetching. WACTL caches SSM parameters for 5 minutes (`secrets.get_secret`).

**CDK (Cloud Development Kit)** — An alternative to Terraform for AWS IaC. WACTL uses Terraform instead (chapter 11 explains why).

**CLI (Command Line Interface)** — A text-based program. The `aws` CLI, `terraform` CLI, and `gh` CLI are all CLIs.

**Cloud-init** — A standard for first-boot instance configuration. WACTL uses it via `data "cloudinit_config"` in Terraform to set up the EC2 worker.

**CloudWatch** — AWS service for logs, metrics, and alarms. WACTL writes logs here and has alarms for DLQ depth, Lambda errors, and worker CPU.

**CloudWatch Logs** — The log storage service within CloudWatch. WACTL's structured JSON logs are stored here.

**CloudWatch Logs Insights** — A query language for CloudWatch Logs. Used to search the JSON log lines.

**Command** — A slash-prefixed instruction the user sends. Each is a Python class in `src/wactl/commands/`. Examples: `/image-resize`, `/pdf-docx`.

**CommandContext** — The value object passed to a command's `run()` method. Contains the user, args, media, and all integration handles.

**CommandMeta** — Static metadata about a command: name, sync/async, requires_media, description. Attached to the class by the `@register` decorator.

**CommandResponse** — The value object a command returns: success, message_id, notes.

**Concurrency** — How many things are happening at once. WACTL's worker processes one job at a time; the Lambda can have many concurrent invocations.

**Conditional write** — A DynamoDB operation that succeeds only if a condition is met. WACTL uses `PutItem` with `ConditionExpression="attribute_not_exists(pk)"` for dedup.

**Constructor** — A function that creates an object. In Python, `__init__` is the constructor. `CommandContext(...)` constructs a context.

**Contextvars** — Python's mechanism for per-async-task state. Used by structlog for bound context.

**CORS (Cross-Origin Resource Sharing)** — Browser security mechanism. Not relevant to WACTL (no browser clients).

**Cron** — A time-based job scheduler. WACTL's EventBridge rule uses a cron expression (currently disabled).

## D

**Daemon** — A long-running background process. The worker is a daemon, managed by systemd.

**Data source** — A read-only Terraform query to AWS. WACTL uses `aws_caller_identity` and `aws_region`.

**DDL (Data Definition Language)** — SQL commands that define schema. Not relevant to WACTL (no SQL).

**Decorator** — A Python feature that wraps a function or class. WACTL uses `@register` to register commands and `@pytest.fixture` to declare fixtures.

**Dedup (Deduplication)** — Ensuring the same message is processed at most once. WACTL uses a DynamoDB table with conditional writes.

**Default tags** — Tags automatically applied to all AWS resources by the Terraform AWS provider. WACTL sets Project, Environment, ManagedBy.

**Dependency injection** — Passing collaborators into a function/class rather than constructing them inside. WACTL's CommandContext is a dependency-injection container.

**Differential** — The set of changes between two versions. Terraform's `plan` is a differential.

**DLQ (Dead Letter Queue)** — An SQS queue that receives messages that failed too many times. WACTL's `wactl-dev-jobs-dlq` is the DLQ for the jobs queue.

**DNS (Domain Name System)** — The internet's name-to-address lookup. API Gateway provides a DNS name for the webhook URL.

**Docker** — A container runtime. WACTL uses it to build the worker tarball.

**Dockerfile** — A recipe for a Docker image. WACTL has one at `worker/Dockerfile`.

**DTO (Data Transfer Object)** — An object that carries data between layers. Pydantic models in WACTL are DTOs.

**DynamoDB** — AWS's NoSQL key-value store. WACTL uses one table for dedup.

## E

**EC2 (Elastic Compute Cloud)** — AWS's virtual machine service. WACTL runs the worker on `t4g.nano` instances.

**Egress** — Outbound network traffic. WACTL's worker security group is egress-only.

**Elasticsearch** — A search engine. Not used in WACTL.

**Endpoint** — A URL that accepts API calls. The webhook URL is an API Gateway endpoint.

**Env var (Environment variable)** — A string passed to a process. WACTL reads these via pydantic-settings.

**ETag** — A version identifier for an S3 object. Not used by WACTL.

**EventBridge** — AWS's event bus service. WACTL has a disabled rule for daily cleanup.

**Exception** — A runtime error. WACTL has a typed hierarchy (`WactlError` and subclasses).

**External API** — A non-AWS HTTP API. WACTL calls WhatsApp, GitHub, Gemini, and the public web.

## F

**Failure mode** — A way the system can fail. WACTL's design assumes the Lambda is short-lived, the worker can crash, AWS can be unavailable, etc.

**FastAPI** — A Python web framework. Not used in WACTL (we use Lambda + API Gateway instead).

**Fixture** — A pytest function that provides test setup. WACTL's `fake_whatsapp` and `fake_s3` are fixtures.

**Flag** — A boolean config option. WACTL has `sync`, `requires_media`, `is_enabled`, etc.

**Flask** — A Python web framework. Not used in WACTL.

**Frontend** — The user-facing part of a system. WACTL's frontend is the Next.js marketing site, not a UI in the traditional sense.

**Function** — A reusable block of code. WACTL is mostly functions and async functions.

**Fuzzy** — Approximate string matching. Not used in WACTL.

## G

**GHA (GitHub Actions)** — GitHub's CI/CD service. WACTL has three workflows: `ci`, `deploy`, `deploy-frontend`.

**Gemini** — Google's LLM. WACTL uses it for `/web-summary`, `/translate`, `/github-pr`, and `/pdf-audio` TTS.

**Git** — A version control system. WACTL's code is in a Git repo.

**GitHub** — A Git hosting service. WACTL's repo is on GitHub.

**Go** — A programming language. Not used in WACTL.

**Graph API** — Meta's unified API for Facebook, Instagram, WhatsApp. WACTL talks to `https://graph.facebook.com/v21.0/`.

**Gunicorn** — A Python WSGI server. Not used in WACTL (we don't run a web server).

## H

**Handler** — The function AWS Lambda calls. WACTL's handler is `lambda.webhook.handler.lambda_handler`.

**Hash** — A one-way function from arbitrary input to fixed-size output. SHA-256 is the hash used in HMAC.

**Hashable** — A Python object that can be used as a dict key or set element. WACTL's pydantic models are frozen + hashable.

**Hex** — Base-16 encoding. HMAC signatures are hex strings.

**HMAC (Hash-based Message Authentication Code)** — A way to authenticate a message using a shared secret. WACTL verifies the `X-Hub-Signature-256` header with HMAC-SHA256.

**Hot reload** — A development feature where code changes are picked up without restarting the process. The Next.js dev server and pytest both have this.

**HTML (HyperText Markup Language)** — The language of web pages. WACTL fetches HTML and converts to Markdown for `/web-summary`.

**HTTP (HyperText Transfer Protocol)** — The protocol of the web. WACTL uses HTTP for all external APIs.

**HTTPS** — HTTP over TLS. WACTL's API Gateway endpoint is HTTPS.

**httpx** — An async HTTP client for Python. WACTL uses it for all external HTTP calls.

## I

**IAM (Identity and Access Management)** — AWS's permissions system. WACTL has three roles: lambda-exec, worker, and gha-deploy.

**Idempotent** — A property of an operation that can be applied multiple times without changing the result beyond the first application. WACTL's cloud-init is idempotent.

**IMDS (Instance Metadata Service)** — An EC2 endpoint at `169.254.169.254` that returns instance metadata. WACTL enforces IMDSv2 to mitigate SSRF.

**IMDSv2** — The v2 of the Instance Metadata Service, which requires a token. More secure than v1.

**Init** — A constructor (in Python, `__init__`). Or: the first run of Terraform (`terraform init`).

**In-process** — Within the same process. WACTL's command registry is in-process (a module-level dict).

**Integration** — A wrapper around an external service. WACTL has one subpackage per external system.

**Integration test** — A test that exercises multiple modules together. WACTL has them in `tests/integration/`.

**Internal API** — An API used by other code within the same system. WACTL's `WebhookDeps` is an internal API.

**Invoke** — To call a function. WACTL's API Gateway invokes the Lambda.

**Issue** — A bug report or feature request on GitHub. WACTL uses GitHub Issues.

## J

**JSON (JavaScript Object Notation)** — A data interchange format. WACTL uses JSON for webhook payloads, SQS messages, and log lines.

**JWT (JSON Web Token)** — A signed token format. GitHub's OIDC tokens are JWTs.

## K

**KMS (Key Management Service)** — AWS's encryption key service. WACTL uses it transparently for SSM SecureString and S3 encryption.

## L

**Lambda** — AWS's serverless compute service. WACTL runs the webhook handler as a Lambda.

**Lambda zip** — The deployment artifact for a Lambda. A zip file containing the handler code + dependencies.

**Lazy** — Deferred until needed. WACTL lazily initializes boto3 clients and the Gemini client.

**Least privilege** — The principle that every principal should have the minimum permissions needed. WACTL's IAM policies follow this.

**Linting** — Static analysis of code for style and common errors. WACTL uses ruff.

**List** — A Python data type (and a verb for creating one). `[1, 2, 3]` is a list.

**LLM (Large Language Model)** — A machine-learning model trained on text. Gemini is an LLM.

**Lockfile** — A file that pins exact dependency versions. WACTL has `uv.lock` (Python) and `package-lock.json` (JavaScript).

**Long poll** — A SQS receive mode where the connection is held open until a message arrives or a timeout. WACTL uses 20-second long polling.

**LRU cache** — A cache that evicts the least-recently-used entries. `functools.lru_cache` is a Python decorator that creates one.

## M

**MagicMock** — A `unittest.mock` class that auto-creates attributes. WACTL uses it for fake AWS clients and the WhatsApp client.

**Markdown** — A lightweight markup language. WACTL's responses often include Markdown formatting (italic, bold, code).

**Media bucket** — The S3 bucket that holds inbound and outbound files. `wactl-dev-media-<id>`.

**Metadata** — Data about data. WACTL's S3 objects have metadata; the webhook envelope has metadata.

**Method** — A function attached to a class. `WhatsAppClient.send_text` is a method.

**Mock** — A test double that records calls and returns canned values. WACTL uses `unittest.mock`, `moto`, and `respx`.

**Moto** — A library that mocks AWS APIs in-process. WACTL uses it for DynamoDB, S3, SQS, and SSM in tests.

**msgid (or message_id)** — The unique identifier Meta assigns to a message. WACTL uses this for dedup.

**Mutex** — A lock. Not used directly in WACTL (Python's GIL handles thread-safety for simple cases).

**mypy** — A static type checker for Python. WACTL uses strict mode.

## N

**Next.js** — A React framework. WACTL's marketing site uses it.

**NoSQL** — A database that's not relational. DynamoDB is NoSQL.

**Notification** — A message sent to a human (email, Slack). WACTL's alarms don't currently have notifications configured.

**Null** — The absence of a value. WACTL uses `None` in Python for null.

## O

**OIDC (OpenID Connect)** — An identity layer on top of OAuth 2.0. WACTL uses it for GitHub Actions → AWS authentication.

**Open-source** — Code with a license that allows use and modification. WACTL is MIT-licensed.

**Outbound** — Going out. WACTL's outbound messages are the responses to users.

**Outputs (Terraform)** — Values printed after `terraform apply`. WACTL's outputs include the webhook URL and queue URLs.

## P

**Package** — A directory of Python modules. WACTL has one package, `wactl/`.

**Paginator** — An AWS feature for iterating over large result sets. WACTL doesn't currently use one.

**Pattern** — A reusable solution to a common problem. WACTL uses the plugin + registry pattern for commands.

**PDF** — Portable Document Format. WACTL handles PDFs in `/pdf-docx`, `/pdf-audio`, `/merge-pdf`, `/split-pdf`, `/translate`.

**Pillow** — The Python imaging library. WACTL uses it for `/image-resize` and `/image-compress`.

**Pip** — The default Python package manager. WACTL uses `uv` instead (which wraps pip).

**Plugin** — A modular extension. WACTL's commands are plugins.

**Plugin registry pattern** — A way to organize plugins where each module registers itself at import time. WACTL's `@register` decorator + `_REGISTRY` dict is this pattern.

**Polling** — Repeatedly asking for new work. The worker polls SQS.

**PostgreSQL** — A relational database. Not used in WACTL.

**Post-mortem** — A retrospective on a failure. WACTL doesn't currently have a template but should.

**Pre-signed URL** — A URL that grants temporary access to a private S3 object. WACTL uses them so WhatsApp can fetch artifacts.

**Private key** — The secret half of an asymmetric key pair. WACTL doesn't use asymmetric crypto.

**Private subnet** — A VPC subnet without a route to the internet. WACTL's worker should run in private subnets (currently in default subnets).

**Processor (structlog)** — A function that transforms a log event. WACTL has a chain of 6 processors.

**Profile** — A named set of AWS credentials. `AWS_PROFILE=...` selects one.

**pubsub** — A messaging pattern with publishers and subscribers. SQS is similar but not exactly pubsub.

**Pytest** — A Python testing framework. WACTL uses it.

**Python** — The programming language WACTL is written in. Version 3.12.

## Q

**Queue** — A FIFO buffer of messages. SQS is a queue.

**Quickstart** — A short tutorial. WACTL's `docs/SETUP.md` is a quickstart.

## R

**Race condition** — A bug where the result depends on the order of concurrent operations. WACTL's conditional write protects against this in dedup.

**RDS (Relational Database Service)** — AWS's managed relational database. Not used in WACTL.

**React** — A JavaScript UI library. WACTL's marketing site uses it via Next.js.

**Read replica** — A read-only copy of a database. WACTL doesn't use one.

**ReadOnly** — A file system permission mode. WACTL's systemd unit uses `ProtectSystem=strict` to make most of the FS read-only.

**Reconnect** — To re-establish a connection. WACTL's httpx client handles reconnection.

**Redrive** — To retry messages from a dead-letter queue. SQS supports this.

**Region** — A geographical AWS region. WACTL defaults to `us-east-1`; can be changed to any region.

**Registry** — A collection of registered items. WACTL's command registry is `_REGISTRY` in `commands/registry.py`.

**Release** — A published version. WACTL's releases are the Lambda zip and worker tarball uploaded to the releases bucket.

**Repository (repo)** — A Git repository. WACTL's repo is on GitHub.

**respx** — A library that mocks httpx. WACTL uses it in tests.

**Retry** — To do something again after a failure. WACTL's tenacity-based retry is in the WhatsApp client.

**Return code** — The status of a function call. Lambda functions return HTTP status codes (200, 4xx, 5xx).

**Route** — A URL pattern in a web framework. WACTL's API Gateway has one route: `/webhook`.

**Router** — Code that maps a request to a handler. WACTL's `router.py` maps text to a command class.

**Ruby** — A programming language. Not used in WACTL.

**ruff** — A fast Python linter. WACTL uses it.

**Runbook** — A document with steps to follow when an alarm fires. WACTL has a mental one in chapter 17.

**Runtime** — The execution environment for a Lambda. WACTL uses `python3.12`.

## S

**S3 (Simple Storage Service)** — AWS's object storage. WACTL uses two buckets: media and releases.

**SageMaker** — AWS's ML platform. Not used in WACTL.

**SAM (Serverless Application Model)** — A framework for building serverless apps. WACTL doesn't use it.

**Scaffold** — A starting point. WACTL's initial commit was a scaffold.

**Schedule** — A time-based trigger. WACTL's EventBridge rule is a scheduled event (disabled).

**Schema** — The structure of data. WACTL's webhook envelope has a schema defined in pydantic models.

**Scope** — The set of permissions or variables in context. WACTL's IAM scopes are minimal.

**SDK (Software Development Kit)** — A library for using a service. WACTL uses `boto3` (AWS) and `google-genai` (Gemini).

**Secret** — A value that must be kept private. WACTL stores them in SSM Parameter Store.

**SecureString** — An SSM parameter type that encrypts the value with KMS. WACTL uses this for all secrets.

**Security group** — A virtual firewall for AWS resources. WACTL's worker security group is egress-only.

**Serverless** — A model where you write functions and the cloud runs them. Lambda is serverless.

**Service** — A cloud offering. WACTL uses many AWS services.

**Service control policy (SCP)** — An AWS Organizations feature for limiting what accounts can do. Not used in WACTL.

**SHA-256** — A cryptographic hash function. WACTL uses it in HMAC.

**SQS (Simple Queue Service)** — AWS's message queue. WACTL uses one for async jobs.

**SIGINT** — The interrupt signal (Ctrl-C). The worker handles this for graceful shutdown.

**SIGTERM** — The termination signal. The worker handles this for graceful shutdown.

**Slack** — A chat tool. Not used in WACTL (yet).

**SNS (Simple Notification Service)** — AWS's pub/sub service. WACTL would use this for alarm notifications (not currently configured).

**Span** — A unit of work in tracing. WACTL doesn't currently use tracing.

**Spot instance** — A discounted EC2 instance that can be reclaimed. WACTL uses on-demand t4g.nano (not spot).

**SQL** — A query language for relational databases. Not used in WACTL.

**SSL** — Older name for TLS. WACTL uses TLS (same thing).

**SSM (Systems Manager)** — AWS's config and secrets service. WACTL uses it for Parameter Store.

**Stage** — A deployment environment in API Gateway. WACTL uses the env name as the stage.

**State** — Terraform's record of what was created. WACTL stores state in S3.

**Stateful** — Having memory of past interactions. WACTL's Lambda is stateless across invocations.

**Stateless** — Not having memory. WACTL's command classes are stateless.

**Static analysis** — Checking code without running it. WACTL uses ruff and mypy.

**Storage** — Where data lives. WACTL uses S3, DynamoDB, and SSM.

**Stream** — A continuous flow of data. WACTL's logs are streamed to CloudWatch.

**String** — A sequence of characters. WACTL's primary data type for text.

**STS (Security Token Service)** — AWS's service for temporary credentials. WACTL uses it via OIDC.

**Subnet** — A subdivision of a VPC. WACTL's ASG runs in default subnets (could be moved to private subnets).

**Swagger** — An API documentation standard. WACTL's API is not documented with Swagger.

**Sync command** — A slash command that runs inline in the Lambda. `/image-resize`, `/image-compress`, `/web-summary`, `/github-pr`, `/translate`.

**Systemd** — A Linux init system. WACTL uses it to manage the worker process.

## T

**Table** — A DynamoDB container for items. WACTL has one: `wactl-dev-dedup`.

**Tail** — To read the latest lines of a log. `aws logs tail /aws/lambda/wactl-dev-webhook --follow`.

**Tailwind** — A utility-first CSS framework. WACTL's marketing site uses it.

**Task** — A unit of async work. WACTL's `_job_context` is a task-local context manager.

**Telemetry** — Automatic data collection about a running system. WACTL has minimal telemetry (only what structlog and boto3 emit).

**Template** — A string with placeholders. WACTL doesn't use templates heavily.

**tenacity** — A Python library for retry logic. WACTL uses it in the WhatsApp client.

**Test** — A verification that code works. WACTL has ~230 of them.

**Terraform** — HashiCorp's Infrastructure as Code tool. WACTL's infra is all Terraform.

**Text message** — A plain-text WhatsApp message (no attachment). WACTL's commands are triggered by text messages starting with `/`.

**Thread** — An OS thread. WACTL uses `asyncio.to_thread` to run blocking code in threads.

**Timeout** — A maximum time to wait. WACTL has timeouts on httpx calls, SQS visibility, etc.

**Timestamp** — A point in time. WACTL's log lines have ISO-8601 timestamps.

**TLS (Transport Layer Security)** — The protocol that encrypts HTTPS. WACTL uses it for all external API calls.

**Token** — A piece of data representing authorization. WACTL has bearer tokens (WhatsApp), fine-grained PATs (GitHub), API keys (Gemini), and IMDSv2 tokens.

**Tooling** — The supporting software for a project. WACTL's tooling includes uv, ruff, mypy, pytest, moto, respx, freezegun, Terraform.

**Traceback** — A stack trace. WACTL's logs include tracebacks for exceptions.

**TTL (Time To Live)** — A duration after which something is automatically deleted. WACTL's DynamoDB entries have 7-day TTL; SQS messages have 4-day retention; IMDSv2 tokens have a few hours.

**TTY** — A terminal. Not used in WACTL.

**Twilio** — A communications API company. WACTL doesn't use it (Meta's API is free; Twilio charges per message).

**Type hint** — A Python annotation indicating the expected type. WACTL uses mypy strict mode.

## U

**UI (User Interface)** — What the user sees and interacts with. WACTL's UI is the WhatsApp chat (not a separate app).

**Unit test** — A test that exercises a single function or class. WACTL has them in `tests/unit/`.

**Unix** — A family of operating systems. WACTL's worker runs on Amazon Linux 2023 (a Unix).

**uv** — A modern Python package manager. WACTL uses it instead of pip.

**UUID (Universally Unique Identifier)** — A 128-bit identifier. WACTL uses `uuid.uuid4()` for job IDs.

## V

**Validate** — To check that data is well-formed. WACTL uses pydantic for this.

**Variable** — A named value. WACTL's Terraform variables are in `infra/variables.tf`.

**Vercel** — A hosting platform optimized for Next.js. WACTL's marketing site deploys there.

**Versioning** — Keeping track of changes. WACTL uses Git for source versioning; Terraform state for infra versioning.

**Visibility timeout** — The time a message is invisible after being received from SQS. WACTL uses 15 minutes.

**VPC (Virtual Private Cloud)** — A private network within AWS. WACTL uses the default VPC.

**VTL (Velocity Template Language)** — A templating language for API Gateway. WACTL doesn't use it (uses AWS_PROXY integration).

## W

**w3m** — A text-based web browser. Not used in WACTL.

**wactl** — The name of this project. Stands for "WhatsApp Control."

**wamid** — WhatsApp Message ID. The unique identifier Meta assigns to each message.

**Webhook** — An HTTP callback. WACTL's Lambda is invoked by a webhook from Meta.

**Worker** — A long-running process that does async work. WACTL's worker is an EC2 instance.

**Workflow** — A CI/CD pipeline definition. WACTL has three in `.github/workflows/`.

## X

**X-Ray** — AWS's tracing service. Not used in WACTL.

**XML** — A data format. Not used in WACTL (we use JSON).

## Y

**YAML** — A data format. WACTL's GitHub workflows are YAML.

## Z

**Zero-downtime** — A deployment property where users see no interruption. WACTL's Lambda updates are zero-downtime; worker instance refreshes have a brief gap.

**Zsh** — A Unix shell. WACTL doesn't care which shell you use.

---

That's the glossary. For more, see the official AWS docs, the [structlog docs](https://www.structlog.org/), the [pydantic docs](https://docs.pydantic.dev/), and the [Next.js docs](https://nextjs.org/docs).
