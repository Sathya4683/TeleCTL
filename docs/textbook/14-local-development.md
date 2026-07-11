# 14 — Local Development

This chapter is the "I just cloned the repo, how do I get it running" guide. It covers installing dependencies, setting up environment variables, running tests, and exercising the Lambda locally.

## 14.1 — Prerequisites

You need:

- **Python 3.12** — pinned in `.python-version`. Most Linux distros have it via `python3.12`; macOS users can use Homebrew.
- **[uv](https://docs.astral.sh/uv/)** — the modern Python package manager. It's a single binary written in Rust; `pip` and `virtualenv` are subsumed. Install it once:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **Node.js 20+** — only for the `web/` site. Install via `nvm`, Homebrew, or the official installer.
- **Docker** (optional) — only needed to build the worker tarball locally. CI does this in GitHub Actions.
- **AWS CLI** (optional) — for interacting with your deployed environment.

That's it. You don't need to install `boto3`, `pytest`, `mypy`, `ruff`, or any of the runtime deps — `uv` handles that.

## 14.2 — Clone and install

```bash
git clone https://github.com/sathya-narayanan/wactl.git
cd wactl
uv sync
```

`uv sync` reads `uv.lock` and installs every runtime + dev dependency into `.venv/`. The lock file is committed to the repo, so this is deterministic — every dev gets the same versions.

Activate the venv in your shell (optional — most `uv` commands can auto-activate):

```bash
source .venv/bin/activate
```

Or run commands via `uv run`:

```bash
uv run pytest
uv run python -c "import wactl; print(wactl.__file__)"
```

`uv run` is the recommended pattern: it activates the venv for a single command without polluting your shell.

## 14.3 — Environment variables

The app reads from environment variables (or a `.env` file in the project root). For local development, copy the example file:

```bash
cp .env.example .env
```

The example file (also worth reading for documentation) lists every variable. The full list:

| Variable | Default | What it does |
|---|---|---|
| `WACTL_ENV` | `dev` | One of `dev`, `staging`, `prod`. Affects log verbosity and some validation. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `AWS_REGION` | `us-east-1` | The region for AWS API calls. |
| `WHATSAPP_API_VERSION` | `v21.0` | Pinned Meta Graph API version. |
| `WHATSAPP_PHONE_NUMBER_ID` | (empty) | The WABA phone number id. |
| `WHATSAPP_WABA_ID` | (empty) | Informational only. |
| `WHATSAPP_ACCESS_TOKEN_SECRET` | `wactl/whatsapp/access-token` | SSM param name for the access token. |
| `WHATSAPP_APP_SECRET_SECRET` | `wactl/whatsapp/app-secret` | SSM param name for the app secret. |
| `WHATSAPP_VERIFY_TOKEN_SECRET` | `wactl/whatsapp/verify-token` | SSM param name for the verify token. |
| `S3_MEDIA_BUCKET` | (empty) | Media bucket name. |
| `S3_RELEASES_BUCKET` | (empty) | Releases bucket name. |
| `SQS_JOBS_QUEUE_URL` | (empty) | Jobs queue URL. |
| `DYNAMODB_DEDUP_TABLE` | `wactl-dedup` | Dedup table name. |
| `DEDUP_TTL_SECONDS` | `604800` (7 days) | TTL for dedup entries. |
| `GEMINI_API_KEY_SECRET` | `wactl/gemini/api-key` | SSM param name for the Gemini key. |
| `GEMINI_TEXT_MODEL` | `gemini-2.0-flash` | Gemini model for text. |
| `GEMINI_TTS_VOICE` | `en-US-Journey-D` | Default voice for `/pdf-audio`. |
| `HTTP_TIMEOUT_SECONDS` | `30.0` | httpx timeout. |
| `HTTP_MAX_RETRIES` | `3` | tenacity retry attempts. |
| `AUDIO_CHUNK_CHAR_LIMIT` | `2000` | TTS chunk size. |
| `IMAGE_MAX_INPUT_BYTES` | `10485760` (10 MB) | Inbound image size cap. |
| `PDF_MAX_INPUT_BYTES` | `52428800` (50 MB) | Inbound PDF size cap. |

### Where are secrets loaded from?

`src/wactl/config.py` defines the `Settings` class via pydantic-settings. pydantic-settings reads:

1. Environment variables (case-insensitive).
2. The `.env` file (if present).
3. Defaults from the class definition.

The actual secret *values* (access token, app secret) are NOT loaded by pydantic-settings. The config holds the **names** of SSM parameters; the values are fetched lazily by `src/wactl/integrations/aws/secrets.py` and cached for 5 minutes.

For local development, you have two options:

1. **Mock everything.** Set `WHATSAPP_ACCESS_TOKEN_SECRET=fake-token` etc. Tests do this.
2. **Point at your real AWS account.** Run `aws sso login` (or set `AWS_PROFILE=...` or `AWS_ACCESS_KEY_ID=...`) and let boto3 + SSM fetch the real values from your account.

The unit tests don't need any of this — they construct `WebhookDeps` with explicit fakes.

## 14.4 — Running the tests

```bash
uv run pytest                     # run everything
uv run pytest tests/unit          # only unit tests
uv run pytest -k "test_webhook"   # by name pattern
uv run pytest --cov=src/wactl     # with coverage
```

The pytest config is in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
minversion = "8.0"
testpaths = ["tests"]
pythonpath = [".", "src", "tests"]
asyncio_mode = "auto"
addopts = [
    "-ra",
    "--strict-markers",
    "--strict-config",
    "--tb=short",
]
```

Three things to note:

- **`pythonpath = [".", "src", "tests"]`** — pytest adds these to `sys.path` so we can `from wactl import ...` (the package in `src/`) and `from conftest_helpers import ...` (test helpers in `tests/unit/`).
- **`asyncio_mode = "auto"`** — every `async def test_...` is automatically treated as `pytest-asyncio`'s `async def`. No need for `@pytest.mark.asyncio` decorators.
- **`--strict-markers`** — every marker (e.g. `@pytest.mark.integration`) must be declared in the `markers` list, otherwise the test run errors. Prevents typos.

The test tree is in chapter 04. There are ~230 tests; the full suite runs in ~10 seconds.

### Test isolation

The test suite uses `moto` to mock AWS and `respx` to mock HTTP. There are no live AWS calls in any test; you don't need AWS credentials to run the tests.

A few fixtures in `tests/conftest.py` and `tests/unit/conftest.py` provide the standard fakes:

```python
@pytest.fixture
def fake_s3():
    """A moto-backed S3 client with a media bucket pre-created."""
    ...

@pytest.fixture
def fake_whatsapp():
    """An AsyncMock that records send_text / send_image / etc."""
    ...

@pytest.fixture
def make_context(fake_whatsapp, fake_s3):
    """Build a CommandContext with sensible defaults."""
    ...
```

See chapter 15 for the test patterns in detail.

## 14.5 — Linting and type-checking

```bash
uv run ruff check .            # lint
uv run ruff format .           # format (in-place)
uv run mypy src/wactl          # type-check
uv run mypy src/wactl tests    # type-check everything
```

The ruff config is opinionated: line length 110, modern Python 3.12 idioms, "E" + "F" + "I" + "B" + "UP" + "SIM" + "ASYNC" + "RUF" + many more rule families. The `ignore` list is small (a couple of "we know what we're doing" cases).

Mypy is in `strict` mode with `disallow_untyped_defs` and `warn_return_any`. This means every function has type annotations on every parameter and return value. The pydantic plugin is enabled so pydantic models get strict validation.

Both tools are run in CI (`.github/workflows/ci.yaml`). The local runs are the same commands; what passes locally passes CI.

## 14.6 — Running the Lambda locally

You can run the Lambda's `lambda_handler` from your laptop without AWS — it's just a Python function that takes a dict and returns a dict:

```python
from lambda.webhook.handler import lambda_handler

# A sample API Gateway proxy event:
event = {
    "httpMethod": "POST",
    "headers": {"X-Hub-Signature-256": "sha256=..."},
    "body": '{"entry": [...]}',
    "isBase64Encoded": False,
}

response = lambda_handler(event, None)
print(response)
```

But there's a complication: the function calls `secrets.get_secret()` which calls SSM. In local development, you'd need AWS credentials or a moto mock.

The cleanest local dev approach is to **use pytest with the existing integration tests**. The `tests/integration/test_webhook_end_to_end.py` test exercises the full webhook flow with mocked AWS; you can run just that one test:

```bash
uv run pytest tests/integration/test_webhook_end_to_end.py -v
```

If you need to *actually* hit a local Lambda (e.g. for an end-to-end test against the real AWS account), use [AWS SAM](https://aws.amazon.com/serverless/sam/) or [LocalStack](https://github.com/localstack/localstack). Both are out of scope for this chapter; the project doesn't currently use either.

## 14.7 — Building the worker image

The worker is built as a Docker image and extracted to a tarball. To build it locally:

```bash
./worker/build.sh
```

This runs `docker build` using `worker/Dockerfile` and produces `dist/worker.tar.gz` + `dist/worker.tar.gz.sha256`. The build takes ~2 minutes the first time (it compiles wheels for pdf2docx, pymupdf, etc.) and ~30 seconds on subsequent runs (Docker caches layers).

You can also run the build steps by hand to debug:

```bash
docker build -t wactl-worker-builder -f worker/Dockerfile .
mkdir -p dist
docker create --name wactl-worker-extract wactl-worker-builder /bin/true
docker cp wactl-worker-extract:/worker.tar.gz dist/worker.tar.gz
docker rm wactl-worker-extract
```

After the build, you can extract and inspect:

```bash
mkdir -p /tmp/worker-inspect
tar -xzf dist/worker.tar.gz -C /tmp/worker-inspect
ls /tmp/worker-inspect/packages/ | head
# wactl/, boto3/, httpx/, ...
```

The tarball contains every Python dep under `packages/` plus the `worker/` directory. To run the worker locally (against a real SQS queue or a moto mock), extract and run:

```bash
cd /tmp/worker-inspect
PYTHONPATH=packages:. python -m worker.main
```

## 14.8 — Running the worker locally

To run the worker against a real SQS queue (for end-to-end testing), you need:

1. AWS credentials in your environment (`AWS_PROFILE=...` or env vars).
2. A SQS queue URL (set `SQS_JOBS_QUEUE_URL`).
3. A `worker.env` file with the same vars the production systemd unit uses (see `infra/ec2.tf`).

The worker uses `boto3` under the hood; it'll connect to the SQS queue, receive messages, and dispatch.

For local-only testing, use the integration tests — they don't require AWS.

## 14.9 — Running the web site

```bash
cd web
npm install
npm run dev
```

Open <http://localhost:3000>. The dev server has hot reload — edits to `app/*.tsx` are picked up instantly.

The build for production:

```bash
npm run build
npm run start
```

The output is a static site (no server-side logic). You can also export to a static directory if you don't want the Node server:

```bash
# Out of the box, `next build` produces a hybrid output.
# For pure static export, add `output: "export"` to next.config.ts.
```

## 14.10 — Common workflows

### Add a new slash command

1. Create `src/wactl/commands/<name>.py` with the command class.
2. Add an import to `src/wactl/commands/__init__.py`.
3. Add the command to `web/lib/site.ts` `COMMANDS` list.
4. Add a test file `tests/unit/test_command_<name>.py`.
5. Run `uv run pytest tests/unit/test_command_<name>.py`.

See chapter 07 for the full pattern.

### Tweak an existing command

1. Edit the file.
2. Run the relevant test.
3. Run `uv run ruff check . && uv run mypy src/wactl` before committing.

### Change the Terraform

1. Edit the `.tf` file.
2. `cd infra && terraform plan` to see the diff.
3. `terraform apply` to apply (after reviewing the plan).
4. If you've added a new resource, add an output to `outputs.tf` so the new ARN/URL is visible.

### Update a dependency

1. `uv add <package>@<version>` to update `pyproject.toml` + `uv.lock`.
2. Run `uv run pytest` to make sure nothing broke.
3. Commit `uv.lock` (not `pyproject.toml` alone).

To upgrade an existing dep to the latest:

```bash
uv lock --upgrade-package <package>
uv sync
uv run pytest
```

### Switch AWS regions

1. Edit `infra/variables.tf` to change the default region (or pass `-var=region=ap-south-1` to terraform commands).
2. Edit `infra/backend.tf` to switch the state bucket (or use a different `-backend-config` for the new region).
3. Re-create the state bucket in the new region (or use a different state file).
4. Edit `src/wactl/config.py` to change the default `aws_region` (or set `AWS_REGION` in your `.env`).
5. Populate the SSM parameters in the new region.

The state bucket is region-specific; you can't move it without re-creating it.

## 14.11 — When things go wrong

### "Module not found: wactl"

You're running from a directory where `src/` isn't on the path. Use `uv run` (which respects the project's `pythonpath`) or activate the venv with `source .venv/bin/activate`.

### "AWS credentials not found"

You tried to call SSM / S3 / SQS from your local machine. Either:

- Configure AWS credentials: `aws configure`, or set `AWS_PROFILE=...`, or set `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` in your env.
- Use the integration tests, which mock AWS.

### "Signature mismatch" when testing the Lambda

Your test event has the wrong HMAC. The body must be the exact bytes the signature was computed over. Re-compute:

```python
import hmac, hashlib
body = '{"entry": [...]}'.encode("utf-8")
sig = "sha256=" + hmac.new(b"<app-secret>", body, hashlib.sha256).hexdigest()
event = {"headers": {"X-Hub-Signature-256": sig}, "body": body.decode("utf-8"), ...}
```

The tests in `tests/integration/test_webhook_end_to_end.py` do this with the `app_secret` fixture.

### "pytest collection error"

A test file has a syntax error. Run `uv run ruff check tests/ && uv run mypy tests/` to find it.

### The worker is stuck in a loop

`worker/main.py` retries every 5 seconds on errors. If you see log spam, the queue URL is wrong or the IAM role doesn't have `sqs:ReceiveMessage`. Check `SQS_JOBS_QUEUE_URL` and your AWS credentials.

## 14.12 — IDE setup

For VS Code:

- Install the Python extension.
- Set the interpreter to `.venv/bin/python`.
- Install the Ruff extension for inline linting.
- Install the Mypy extension for inline type errors.

For PyCharm:

- Mark `src/` as "Sources Root" and `tests/` as "Test Sources Root."
- Configure the project interpreter as `.venv/bin/python`.
- Enable the Ruff and Mypy plugins.

Both work out of the box; the project doesn't have any IDE-specific config (no `.vscode/`, no `.idea/`).

## Next

→ [`15-testing.md`](15-testing.md) — the test patterns, fixtures, and mocking libraries in detail.
