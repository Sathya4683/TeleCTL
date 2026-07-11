# 15 — Testing

WACTL has ~230 tests, all of which run in ~10 seconds and don't require AWS credentials. This chapter explains the architecture: what's mocked, how, and why.

## 15.1 — The test philosophy

Three rules:

1. **No real AWS in unit tests.** Every AWS call is mocked. Unit tests run offline; CI doesn't need AWS credentials.
2. **No real network in any test.** Every HTTP call (WhatsApp, GitHub, the public web) is mocked via `respx`.
3. **No real time.** Code that uses `time.time()` or `datetime.now()` is frozen with `freezegun` when needed.

The result: tests are deterministic, fast, and run on a developer laptop without any external setup.

The trade-off: mocks can drift from the real API behavior. We mitigate this by:
- Using `moto` for AWS (it implements the real API contracts, not just records calls).
- Using `respx` for HTTP (it intercepts at the `httpx` level, so the request format is what we'd actually send).
- Pinning dep versions in `uv.lock` so the mocks and the real code stay in sync.

## 15.2 — The test layout

```
tests/
├── conftest.py                # top-level fixtures (sample webhooks, app_secret)
├── fixtures/                  # captured webhook payloads (text/image/document/status)
│   ├── whatsapp_text_webhook.json
│   ├── whatsapp_image_webhook.json
│   ├── whatsapp_document_webhook.json
│   └── whatsapp_status_webhook.json
├── unit/                      # one test file per module
│   ├── conftest.py            # re-exports the helpers below
│   ├── conftest_helpers.py    # make_user, make_context, fake_whatsapp, fake_s3
│   ├── test_aws_*.py
│   ├── test_command_*.py
│   ├── test_converters_*.py
│   ├── test_dispatcher.py
│   ├── test_gemini_*.py
│   ├── test_github_*.py
│   ├── test_parser.py
│   ├── test_registry.py
│   ├── test_router.py
│   ├── test_signature.py
│   └── test_whatsapp_*.py
└── integration/
    ├── test_webhook_end_to_end.py   # full webhook flow with mocked AWS
    └── test_worker.py                # worker poll + dispatch loop
```

Convention: **one test file per source file.** `src/wactl/integrations/aws/s3.py` has a corresponding `tests/unit/test_aws_s3.py`. This makes it easy to find tests for a given module and to keep coverage high.

The `tests/fixtures/` directory holds *captured* webhook payloads — JSON files of real-looking webhooks that we use across multiple test files. They're checked in; if Meta changes the envelope shape, the fixtures break and we update them.

## 15.3 — The testing tools

Four libraries do most of the work:

### `pytest` + `pytest-asyncio`

`pytest` is the test runner. `pytest-asyncio` lets us write `async def test_...` directly:

```python
async def test_post_runs_sync_command(...):
    ...
    await messages.send_text(...)
    ...
```

The `asyncio_mode = "auto"` setting in `pyproject.toml` means every `async def test_` is auto-marked; no need for `@pytest.mark.asyncio`.

### `moto`

[moto](https://github.com/getmoto/moto) is "AWS mocking library." It replaces the boto3 clients with in-memory implementations of the AWS APIs. You can create a DynamoDB table, put an item, query — and moto handles it like AWS would.

```python
import boto3
from moto import mock_aws

@mock_aws
def test_dedup_claim():
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="test-dedup",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    # ... use the table
```

The `@mock_aws` decorator intercepts all boto3 calls in the test and routes them to moto's in-memory backend. Outside the decorator (or after the test ends), boto3 hits real AWS.

We use `mock_aws` for DynamoDB, S3, SQS, and SSM Parameter Store. The dev dependency is `moto[dynamodb,s3,sqs,secretsmanager]>=5.0` — we install the extras for the services we mock.

### `respx`

[respx](https://github.com/lundberg/respx) is the httpx equivalent of `responses` (for requests). It intercepts HTTP calls and lets you mock the responses:

```python
import respx
import httpx

@respx.mock
async def test_fetch_pr():
    respx.get("https://api.github.com/repos/foo/bar/pulls/1").mock(
        return_value=httpx.Response(200, json={"title": "My PR", ...})
    )
    async with httpx.AsyncClient() as client:
        pr = await fetch_pr(client, "https://github.com/foo/bar/pull/1")
    assert pr.title == "My PR"
```

This is how we mock WhatsApp, GitHub, and the public web.

### `freezegun`

[freezegun](https://github.com/spulec/freezegun) lets us freeze `datetime.now()` and `time.time()`:

```python
from freezegun import freeze_time

@freeze_time("2026-01-01 12:00:00")
def test_ttl_calculation():
    assert int(time.time()) == 1735732800
```

We use this in the dedup tests, where the `expires_at` attribute is computed from the current time.

## 15.4 — The fixtures

There are two conftest files:

- `tests/conftest.py` — top-level fixtures: sample webhook payloads, the test `app_secret`, etc.
- `tests/unit/conftest_helpers.py` — helpers for building test contexts: `make_user`, `make_context`, `fake_whatsapp`, `fake_s3`. This file is intentionally NOT named `test_*.py` so pytest doesn't try to collect it as a test.

### `make_user()`

```python
def make_user() -> UserContext:
    return UserContext(
        phone="15551234567",
        name="alice",
        message_id="wamid.TEST",
        waba_id="waba-1",
        phone_number_id="pn-1",
    )
```

A deterministic user. The `wamid.TEST` shows up in logs; the `15551234567` is a US-format fake number. Every test that needs a user calls this — no need to construct a `UserContext` by hand.

### `make_context(...)`

```python
def make_context(
    *,
    user=None,
    args="",
    media_bytes=None,
    media_mime_type=None,
    media_filename=None,
    whatsapp=None,
    s3=None,
    s3_bucket="wactl-media-test",
    http=None,
    gemini=None,
    extra=None,
) -> CommandContext:
    return CommandContext(
        user=user or make_user(),
        args=args,
        raw_body="",
        media_id="mid.test" if media_bytes is not None else None,
        media_bytes=media_bytes,
        media_mime_type=media_mime_type,
        media_filename=media_filename,
        whatsapp=whatsapp,
        s3=s3,
        http=http,
        gemini=gemini,
        s3_bucket=s3_bucket,
        **(extra or {}),
    )
```

The `make_context` helper builds a `CommandContext` with sensible defaults. Most tests pass only the fields they care about:

```python
def test_image_resize_uses_pillow(monkeypatch, fake_whatsapp, fake_s3):
    ctx = make_context(
        args="800x600",
        media_bytes=b"fake-png-bytes",
        media_mime_type="image/png",
        whatsapp=fake_whatsapp,
    )
    response = await ImageResizeCommand().run(ctx)
    assert fake_s3.put_object.called
    assert fake_whatsapp.send_image.called
```

No boilerplate, no fixture inheritance, no shared state.

### `fake_whatsapp`

```python
@pytest.fixture
def fake_whatsapp() -> MagicMock:
    client = MagicMock(name="whatsapp")
    client.messages_url = "https://graph.facebook.com/v21.0/pn-1/messages"
    client.post_json = AsyncMock(return_value={"messages": [{"id": "wamid.OUT"}]})
    client.get_json = AsyncMock(return_value={"url": "https://look.example/b", "messages": [{"id": "wamid.OUT"}]})
    client.get_bytes = AsyncMock(return_value=b"binary-blob")
    client.send_text = AsyncMock(return_value="wamid.OUT")
    client.send_document = AsyncMock(return_value="wamid.OUT")
    client.send_image = AsyncMock(return_value="wamid.OUT")
    client.send_audio = AsyncMock(return_value="wamid.OUT")
    return client
```

A `MagicMock` that pretends to be a `WhatsAppClient`. All the `send_*` methods are `AsyncMock` returning a fake wamid. Tests assert on the calls:

```python
fake_whatsapp.send_text.assert_called_once()
call_kwargs = fake_whatsapp.send_text.call_args.kwargs
assert "help" in call_kwargs["body"].lower()
```

### `fake_s3`

```python
@pytest.fixture
def fake_s3(monkeypatch) -> MagicMock:
    fake = MagicMock(name="s3")
    fake.put_object = MagicMock()
    fake.presigned_get_url = MagicMock(return_value="https://example.com/presigned")
    fake.make_key = MagicMock(side_effect=lambda *parts: "/".join(parts))
    monkeypatch.setattr("wactl.integrations.aws.s3", fake)
    return fake
```

Patches the `wactl.integrations.aws.s3` module with a mock. Tests don't need to set up S3; the mock records calls and returns a fake presigned URL.

## 15.5 — Common test patterns

### Testing a command

```python
async def test_pdf_docx_converts_attachment(monkeypatch, fake_whatsapp, fake_s3):
    pdf_bytes = b"%PDF-1.4\n..."
    ctx = make_context(
        args="",
        media_bytes=pdf_bytes,
        media_mime_type="application/pdf",
        whatsapp=fake_whatsapp,
    )
    
    # Mock the pdf2docx library
    monkeypatch.setattr("wactl.integrations.converters.pdf_docx.pdf_to_docx", lambda x: b"fake-docx")
    
    response = await PdfDocxCommand().run(ctx)
    
    assert response.success
    assert fake_s3.put_object.called
    assert fake_whatsapp.send_document.called
```

The pattern: build a context, monkeypatch the library, run the command, assert on the fakes.

### Testing a webhook flow

The integration test file `tests/integration/test_webhook_end_to_end.py` is the canonical example. It uses a real `WebhookDeps` (with mocked collaborators) and runs the full flow:

```python
def test_post_runs_sync_command(monkeypatch, fake_deps):
    monkeypatch.setattr("wactl.integrations.aws.secrets.get_secret", lambda name: "secret")
    monkeypatch.setattr("wactl.webhook._is_duplicate", lambda mid: False)
    
    sent = []
    async def _capture(*a, **kw):
        sent.append(kw)
        return "wamid.OUT"
    monkeypatch.setattr("wactl.integrations.whatsapp.messages.send_text", _capture)
    
    # Register a throwaway command and restore the registry after
    saved = registry_all()
    @register("/_test_ping", sync=True)
    class PingCommand(Command):
        async def run(self, ctx):
            return CommandResponse(success=True, message_id="wamid.test")
    
    try:
        env = _text_envelope("/_test_ping")
        raw = json.dumps(env, separators=(",", ":")).encode("utf-8")
        sig = _sign(raw, "secret")
        event = _make_event(env, sig=sig)
        
        resp = webhook.handle(event, deps=fake_deps)
        assert resp == {"statusCode": 200}
    finally:
        registry_restore(saved)
```

Notice three patterns:

1. **`monkeypatch.setattr`** is the universal way to replace a function or method for one test.
2. **`_sign(raw, "secret")`** computes the HMAC over the exact bytes we'll send, so the signature is always valid.
3. **`registry_restore(saved)`** in a `finally` block ensures the throwaway command doesn't leak into other tests.

### Testing with moto

For tests that exercise DynamoDB / S3 / SQS:

```python
from moto import mock_aws

@mock_aws
def test_dedup_claim_first_time_succeeds():
    # Set up a real-looking DynamoDB
    ddb = boto3.client("dynamodb", region_name="us-east-1")
    ddb.create_table(
        TableName="test-dedup",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    
    # Now call our code
    from wactl.integrations.aws import dynamodb
    assert dynamodb.try_claim("test-dedup", "wamid.1", ttl_seconds=60) is True
    assert dynamodb.try_claim("test-dedup", "wamid.1", ttl_seconds=60) is False  # duplicate
```

The `@mock_aws` decorator (and the `@mock_aws` context manager) intercept all boto3 calls in the test scope and route them to moto's in-memory backend.

### Testing with respx

For tests that exercise HTTP calls:

```python
import respx
import httpx

@respx.mock
async def test_web_summary_fetches_and_summarizes():
    # Mock the URL fetch
    respx.get("https://example.com/article").mock(
        return_value=httpx.Response(
            200,
            html="<html><head><title>Hello</title></head><body><p>Content</p></body></html>",
        )
    )
    
    # Mock the Gemini call (via a fake client)
    fake_gemini = AsyncMock()
    fake_gemini.generate_text = AsyncMock(return_value="Summary text")
    
    # Run the command
    ctx = make_context(args="https://example.com/article", gemini=fake_gemini, http=httpx.AsyncClient())
    response = await WebSummaryCommand().run(ctx)
    
    assert response.success
    assert fake_gemini.generate_text.called
```

The `@respx.mock` decorator intercepts all `httpx` calls. Outside it, real network.

## 15.6 — Test isolation

Every test is independent. We don't share state between tests. The patterns that enforce this:

- **No module-level mutable state in tests.** Fixtures create new mocks; monkeypatch is per-test.
- **Registry snapshot/restore.** Integration tests that register a command do `saved = registry_all()` before and `registry_restore(saved)` after.
- **Settings cache reset.** Tests that change env vars call `get_settings.cache_clear()` (the `lru_cache` on `get_settings`).
- **moto per test.** The `@mock_aws` decorator scopes the mock to the test; tables created in one test don't exist in the next.

If a test fails when run in isolation but passes in the full suite (or vice versa), it's a test isolation bug. We've had a few of these; the fix is always to make the test less reliant on implicit state.

## 15.7 — What we don't test (and why)

A few things are deliberately not in the test suite:

- **The actual `sam local invoke` flow.** It's an integration of an integration; we trust that the same code that runs in tests also runs in Lambda.
- **The actual Terraform plan.** We run `terraform plan` in CI as a syntax check, but we don't test the *behavior* of the resources. The right way to test infra is with [Terratest](https://terratest.gruntwork.io/), which is out of scope for v1.
- **The actual Vercel deploy.** Same reason.
- **Real WhatsApp / Gemini / GitHub API behavior.** We mock the responses; the real API can change in ways our mocks don't.

For (1)-(3), the cost of testing the deploy flow is high (needs AWS account, needs to actually deploy) and the value is low (the changes are usually in code we already test).

For (4), we rely on:
- The fixtures in `tests/fixtures/` being kept up to date with Meta's actual envelope shape.
- Manual smoke testing when a Meta API version changes.
- Errors logged and monitored via CloudWatch (chapter 17).

## 15.8 — Coverage

Coverage is informational. The pytest config:

```toml
[tool.coverage.run]
branch = true
source = ["src/wactl"]

[tool.coverage.report]
show_missing = true
skip_covered = false
fail_under = 70
```

`fail_under = 70` means CI fails if coverage drops below 70%. This is a floor, not a target; we aim for ~85% on the core modules and accept lower coverage on the converters (where the test value is low — they're wrappers around well-tested third-party libs).

Run with coverage locally:

```bash
uv run pytest --cov=src/wactl --cov-report=term-missing
```

The `term-missing` flag shows which lines are uncovered in each file.

## 15.9 — Common testing gotchas

### "Why does this test pass locally but fail in CI?"

Common causes:

- **A missing fixture.** CI uses a fresh venv; if you forgot to `uv add` a dev dep, the import fails.
- **An env var.** Tests that rely on env vars need to set them in the test (don't rely on the dev's `.env`).
- **Time zone.** `datetime.now(UTC)` is tz-aware; `datetime.now()` is not. If your test uses naive datetimes and the production code uses aware, the comparison fails.

### "Why is the test so slow?"

Usually because of `moto` cold-start (the first `@mock_aws` test in a session takes ~1 second for the import). After the first test, subsequent ones are fast.

If a single test takes >5 seconds, it's probably doing real I/O. Check for missing mocks.

### "Why does the test see calls it shouldn't?"

You didn't reset the mock. `MagicMock` keeps call history until you call `.reset_mock()`. For shared mocks across tests, this is a footgun. The fix: each test gets its own mock via the `fake_whatsapp` / `fake_s3` fixtures (function scope by default).

## 15.10 — Adding a new test

The pattern is:

1. Find the source file you want to test.
2. Create `tests/unit/test_<module>.py` (or `tests/integration/test_<feature>.py` for end-to-end).
3. Import the relevant fixtures from `conftest_helpers` if needed.
4. Write `def test_...` or `async def test_...` functions.
5. Use `make_user`, `make_context`, `fake_whatsapp`, `fake_s3` for the standard cases.
6. Use `moto` / `respx` for AWS / HTTP mocking.
7. Run `uv run pytest tests/unit/test_<module>.py -v` to verify.
8. Run `uv run pytest --cov` to check coverage.

That's it. Tests are the easiest code to write in this codebase because the patterns are uniform.

## Next

→ [`16-deployment-and-cicd.md`](16-deployment-and-cicd.md) — the GitHub Actions workflows, OIDC, and the deploy flow.
