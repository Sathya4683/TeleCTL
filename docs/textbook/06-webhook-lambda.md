# 06 — The Webhook Lambda in Detail

The Lambda is the front door of the system. Every inbound message from WhatsApp arrives here, gets authenticated, parsed, deduplicated, routed to a command, and either run inline or enqueued. This chapter walks through that flow line by line.

## 6.1 — Where the Lambda lives

```
lambda/
└── webhook/
    ├── __init__.py
    └── handler.py       # the AWS entry point
```

The file is intentionally tiny:

```python
# lambda/webhook/handler.py
from wactl.webhook import build_deps
from wactl.webhook import handle as wactl_handle

_DEPS: Any | None = None


def _get_deps() -> Any:
    global _DEPS
    if _DEPS is None:
        _DEPS = build_deps()
    return _DEPS


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return wactl_handle(event, context, deps=_get_deps())
```

That's the whole AWS-facing file. The name `lambda_handler` is what AWS looks for. Everything else lives in `src/wactl/webhook.py` so the same code is callable from tests and `sam local invoke` without any AWS SDK in the path.

`build_deps()` constructs the production integrations (WhatsApp HTTP client, Gemini client, boto3 wrappers) **once per Lambda container**. AWS reuses the same container for subsequent invocations, so we get the speedup for free. The `_DEPS` singleton handles that.

## 6.2 — The `handle()` function: the real entry point

The `lambda_handler` is a one-liner. All the actual logic is in `wactl.webhook.handle`:

```python
# src/wactl/webhook.py
def handle(event, context=None, *, deps=None) -> dict[str, Any]:
    reset_context()                                       # 1
    http_method = (event.get("httpMethod") or ...).upper()  # 2

    if http_method == "GET":                              # 3
        verdict = verify_webhook_get(event)
        if verdict is None:
            return {"statusCode": 403, "body": "Forbidden"}
        return {"statusCode": 200, "body": verdict.challenge}

    if deps is None:
        deps = build_deps()                               # 4

    try:
        return _dispatch_post(event, deps)                # 5
    except SignatureVerificationError as exc:
        logger.warning("webhook.signature_invalid", message=str(exc))
        return {"statusCode": 200}                        # 6
    except DuplicateMessageError:
        return {"statusCode": 200}
    except WactlError as exc:
        logger.error("webhook.unhandled", error=type(exc).__name__, message=str(exc))
        return {"statusCode": 200}
    except Exception as exc:
        logger.error("webhook.unexpected_exception", error=type(exc).__name__, message=str(exc))
        return {"statusCode": 200}
```

What each step does:

1. **`reset_context()`** — clears any structlog context vars. Every request gets a clean slate for log binding (wamid, user phone, etc.).
2. **Method detection** — pulls `httpMethod` from the API Gateway event. Falls back to `requestContext.http.method` for HTTP API v2 events; defaults to `"POST"`.
3. **GET handshake** — Meta sends a GET to your webhook URL once when you register it in the developer console. We need to echo `hub.challenge` if the verify token matches.
4. **Lazy dep build** — production only. Tests always inject their own `deps`.
5. **Dispatch the POST** — delegates to `_dispatch_post`, which calls `asyncio.run(_handle_post_async(...))`. All the real work happens there.
6. **Always return 200** — Meta retries on any non-200 status, *up to 7 days*. We log the failure and swallow it; better to drop a real error than to flood the queue with retries.

> **Design rule of thumb:** the Lambda is a "transaction boundary." Anything that happens inside it is either committed (200 to Meta) or retried by Meta forever. There's no in-between.

## 6.3 — The GET handshake

When you register a webhook in the Meta developer portal, Meta sends a GET to your URL with three query params:

```
GET /webhook?hub.mode=subscribe&hub.challenge=12345&hub.verify_token=<your-token>
```

You have to echo `hub.challenge` as the response body, with status 200, to confirm you own the endpoint. We check `hub.verify_token` against the value stored in SSM:

```python
def verify_webhook_get(event):
    params = event.get("queryStringParameters") or {}
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    if mode != "subscribe" or not challenge:
        return None
    expected_token = secrets.get_secret(settings.whatsapp_verify_token_secret)
    if params.get("hub.verify_token") == expected_token:
        return VerificationResult(challenge=challenge)
    return None
```

We return 403 (not 200) for a bad token. The registration is interactive — a human is reading the screen, not a retrying bot — so the loud failure is OK there.

## 6.4 — Body decoding

API Gateway gives us the body as a string by default. We always work with `bytes` because HMAC needs the raw body — JSON-decoding first and re-serializing would produce a different byte string and the signature would fail.

```python
def _decode_body(event):
    body = event.get("body", "")
    if event.get("isBase64Encoded"):
        return base64.b64decode(body)
    if isinstance(body, bytes):
        return body
    return str(body).encode("utf-8")
```

`isBase64Encoded=true` happens when the body is binary (rare for a JSON webhook, but possible if someone configures the API wrong). The function handles all three cases.

## 6.5 — HMAC verification: the security gate

This is the most important security check in the system. Without it, *anyone* could POST to your webhook URL and trigger commands on behalf of your users.

### What HMAC is (in 60 seconds)

**HMAC** = *Hash-based Message Authentication Code*. It's a way to prove "this message came from someone who knows a shared secret" without sending the secret itself.

The recipe:

```
signature = SHA256(secret + message)
```

Both sides know the secret. Meta computes the signature and sends it in a header. We recompute the signature and compare. If they match, the message is authentic — nobody else could have produced the same signature without the secret.

For Meta's webhooks specifically:

```
X-Hub-Signature-256: sha256=<hex(hmac_sha256(app_secret, raw_body))>
```

The `sha256=` prefix tells us the algorithm; the hex part is the signature.

### The verification code

```python
SIG_HEADER = "X-Hub-Signature-256"
SIG_PREFIX = "sha256="

def verify_signature(raw_body: bytes, signature_header: str | None, app_secret: str) -> None:
    if not signature_header or not signature_header.startswith(SIG_PREFIX):
        raise SignatureVerificationError("Missing or malformed signature header")

    expected = hmac.new(
        app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    provided = signature_header[len(SIG_PREFIX):].strip()

    if not hmac.compare_digest(expected, provided):
        raise SignatureVerificationError("HMAC mismatch")
```

Three things to notice:

1. **Constant-time comparison.** We use `hmac.compare_digest(expected, provided)`, not `==`. The built-in `==` is short-circuit — it returns `False` the moment it sees a mismatched byte, which leaks timing information an attacker could exploit to brute-force the signature. `compare_digest` always takes the same time regardless of where the mismatch is.
2. **Raw body, not parsed JSON.** The signature is computed over the exact bytes Meta sent. If we re-serialize the JSON (e.g. via `json.dumps(body, indent=2)`), the bytes change and the signature fails. This is why we never parse the body before verifying.
3. **Fail-closed.** If the header is missing, malformed, or doesn't match, we raise — and the outer `handle()` returns 200 to Meta anyway. This is deliberate: see the failure-mode table in chapter 03.

### Why we still 200 on signature failure

You'd think a bad signature should be a 401 or 403. The reason we don't:

- Meta's retry logic interprets 4xx/5xx as "transient failure — try again." A bad signature will never become good on retry.
- Returning 200 makes Meta stop retrying. The bad request is dropped, the attacker learns nothing from the response, and our queue isn't polluted.
- We log the failure (`webhook.signature_invalid`) so we still see it in CloudWatch.

This is the standard pattern for webhook receivers (Stripe, GitHub, Slack all do the same).

## 6.6 — Parsing the Meta envelope

Once the signature is good, we parse the body as JSON and run it through pydantic models:

```python
import json as _json
payloads = parse_envelope(_json.loads(raw_body))
```

`parse_envelope` (in `src/wactl/integrations/whatsapp/parser.py`) walks the deeply-nested Meta structure and returns a flat list of `ParsedMessage` objects:

```python
def parse_envelope(raw: dict | WhatsAppEnvelope) -> list[ParsedMessage]:
    if isinstance(raw, dict):
        try:
            envelope = WhatsAppEnvelope.model_validate(raw)
        except Exception as exc:
            raise WebhookError(f"Failed to parse webhook envelope: {exc}", user_message="") from exc
    else:
        envelope = raw

    out: list[ParsedMessage] = []
    for message in envelope.all_messages():
        user = _build_user(envelope, message)
        if isinstance(message, TextMessage):
            out.append(ParsedTextMessage(user=user, message=message))
        elif isinstance(message, MediaMessage):
            out.append(ParsedMediaMessage(user=user, message=message))
        else:
            raise WebhookError(f"Unknown message type: {type(message).__name__}")
    return out
```

The pydantic models live in `src/wactl/models/webhook.py` and mirror Meta's actual payload structure:

```text
{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "<WABA-id>",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "...", "phone_number_id": "..."},
            "contacts": [{"profile": {"name": "Alice"}, "wa_id": "919999999999"}],
            "messages": [
              {
                "from": "919999999999",
                "id": "wamid.HBgL...",
                "timestamp": "1700000000",
                "type": "text",
                "text": {"body": "/image-resize 800x600"}
              }
            ]
          }
        }
      ]
    }
  ]
}
```

Notice:

- `Message` is a **discriminated union** of `TextMessage | MediaMessage`, discriminated on the `type` field. Pydantic v2 handles this natively via the `Field(discriminator="type")` annotation.
- `TextMessage` and `MediaMessage` use `frozen=True` (the `_Base` config), so they're immutable and hashable.
- `from_` is renamed from the JSON `from` (a Python keyword) via Pydantic's `Field(alias="from")`.
- The `_Base` config also sets `extra="ignore"` — fields Meta adds in the future that we don't model are silently dropped instead of raising.

For status updates (delivery receipts, read receipts) and errors, the value block has a `statuses` or `errors` list instead of `messages`. `all_messages()` only yields the user messages, so status webhooks parse to an empty list and are silently dropped.

## 6.7 — Dedup with DynamoDB

Meta's webhook spec says: "we retry up to 7 days on non-200." If our Lambda has a transient error (timeout, OOM, network blip), Meta re-sends the same message. Without dedup, the user gets the result twice — annoying for `/image-resize`, expensive for `/pdf-audio`.

The fix is a DynamoDB table keyed by `wamid...` message ID. We do a **conditional write**:

```python
# src/wactl/integrations/aws/dynamodb.py
def try_claim(table, message_id, *, ttl_seconds, metadata=None) -> bool:
    expires_at = int(time.time()) + ttl_seconds
    item = {
        "pk": {"S": message_id},
        "expires_at": {"N": str(expires_at)},
    }
    try:
        _get_client().put_item(
            TableName=table,
            Item=item,
            ConditionExpression="attribute_not_exists(pk)",  # ← the magic
        )
        return True   # first time we've seen this wamid
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False  # already exists → duplicate
        raise AWSIntegrationError(...) from exc
```

The `ConditionExpression="attribute_not_exists(pk)"` makes the `PutItem` atomic: it succeeds only if no item with that primary key exists. If Meta retries, the second `PutItem` fails with `ConditionalCheckFailedException`, and we treat that as "already processed, drop."

The `expires_at` attribute enables DynamoDB's TTL feature: items auto-delete 7 days after creation (matching Meta's retry window). The `infra/dynamodb.tf` file configures TTL on this attribute.

### Fail-open dedup

```python
def _is_duplicate(message_id: str) -> bool:
    try:
        claimed = dynamodb.try_claim(settings.dynamodb_dedup_table, message_id, ttl_seconds=...)
    except WactlError:
        return False  # dedup unavailable → process anyway
    return not claimed
```

If DynamoDB is down, we'd rather process the message twice (a duplicate send to the user) than drop a real user request. The TTL is 7 days; the DynamoDB outage had better be shorter. This is a deliberate "availability over consistency" choice.

## 6.8 — Routing

For text messages, we look up the command:

```python
# src/wactl/webhook.py (inside _process_text)
routed = route(body)  # raises CommandNotFoundError if unknown
```

`route()` (in `src/wactl/router.py`) is the tiniest piece of the system:

```python
def parse(text):
    text = text.strip()
    if not text:
        return "", ""
    parts = text.split(maxsplit=1)
    cmd = parts[0]
    rest = parts[1].strip() if len(parts) > 1 else ""
    return cmd, rest

def route(text):
    name, args = parse(text)
    if not name.startswith("/"):
        raise CommandNotFoundError(f"Message does not start with a command: {text!r}")
    cls = get(name)
    if cls is None:
        raise CommandNotFoundError(f"Unknown command {name!r}")
    return RoutedCommand(name=name, cls=cls, args=args)
```

Two things:

- `parse` splits on the first whitespace, so `/image-resize 800x600` becomes `("/image-resize", "800x600")`. Everything after the first space is the args tail — the command class decides how to interpret it.
- `get(name)` looks up the class in the `_REGISTRY` dict populated by the `@register` decorator. See chapter 07 for the registry pattern.

If `route` raises, we send the user a hint message ("Send a command starting with '/' (e.g. /pdf-docx, /image-resize)") and return 200 to Meta. We never raise past the boundary.

## 6.9 — Sync vs async dispatch

Once we have a `RoutedCommand`, we look at its metadata to decide where it runs:

```python
if routed.cls.meta.sync:
    resp = await dispatch_sync(routed, user=user, whatsapp=deps.whatsapp, ...)
    logger.info("command.sync.complete", command=routed.name, success=resp.success)
else:
    await dispatch_async(routed, user=user, sqs=deps.sqs, queue_url=settings.sqs_jobs_queue_url)
    logger.info("command.async.enqueued", command=routed.name)
```

`routed.cls.meta.sync` is a boolean attached to every command class via the `CommandMeta` dataclass. The `webhook.py` orchestrator doesn't need to know *why* a command is sync or async — it just consults the flag.

The two dispatchers are in `src/wactl/dispatcher.py`:

- **`dispatch_sync`** runs the command inline in the Lambda. The Lambda is billed per ms; a 2-second resize is fine, a 60-second TTS conversion is wasteful.
- **`dispatch_async`** serializes the request to JSON and sends it to SQS. The worker picks it up later. The Lambda returns 200 in ~100ms; the user sees a "queued" message immediately.

Both dispatchers share a common step: `prepare_context`, which downloads the attached media from Meta's servers (since the URL expires in 5 minutes) and stuffs the bytes into the `CommandContext` the command receives. Chapter 08 covers the worker-side equivalent.

### What the command gets

`dispatch_sync` instantiates the command class and calls `.run(context)`:

```python
# from dispatcher.py (simplified)
async def dispatch_sync(routed, *, user, whatsapp, http, gemini, s3, secrets):
    cmd = routed.cls()                         # construct
    ctx = CommandContext(
        user=user, args=routed.args, whatsapp=whatsapp, http=http, gemini=gemini,
        s3=s3, secrets=secrets, ...
    )
    if cmd.meta.requires_media:
        ctx.media_bytes = await _download_media(ctx)
    resp = await cmd.run(ctx)                  # ← the actual work
    return resp
```

The command returns a `CommandResponse` (`success: bool`, optional `error`, optional `reply_text`). On success, the dispatcher sends the reply back to the user via `whatsapp.messages.send_*`. On failure (user error), it sends the user a friendly message. On internal error, it logs and swallows.

## 6.10 — Error handling philosophy

The Lambda's error handling follows one rule: **never let an exception escape the request**. Every `except` clause logs and returns 200. This is unusual — most web frameworks want you to surface 5xx — but it makes sense here because:

| Error type | What Meta sees | What we do |
|---|---|---|
| Signature mismatch | 200 (silent drop) | Log `webhook.signature_invalid` |
| Malformed JSON | 200 (silent drop) | Log `webhook.parse_failed` |
| Duplicate wamid | 200 (silent drop) | Log `webhook.duplicate_dropped` |
| Unknown command | 200 + text reply | Send hint to user |
| User input error | 200 + text reply | Send `exc.user_message` to user |
| Internal exception | 200 (silent drop) | Log `webhook.unexpected_exception`; CloudWatch alarm fires |

The trade-off: we don't tell Meta about failures, so Meta never retries permanently-broken messages. Instead, we rely on CloudWatch alarms (`infra/cloudwatch.tf`) to page us when the error rate spikes. See chapter 17 for the alarm config.

## 6.11 — Structlog context binding

Each request gets its own log context:

```python
for parsed in payloads:
    with bind_context(message_id=parsed.user.message_id, user_phone=parsed.user.phone):
        if _is_duplicate(parsed.user.message_id):
            logger.info("webhook.duplicate_dropped")
            ...
```

`bind_context` is a `contextvars`-based helper. Every log line inside the `with` block automatically gets `message_id` and `user_phone` fields appended to the JSON. This makes CloudWatch queries like "show me all logs for wamid.ABC" trivial.

`reset_context()` at the top of `handle` ensures no context leaks between requests in the same container. Lambda containers can serve many requests, and contextvars persist across invocations.

## 6.12 — What the Lambda does NOT do

To keep the file readable, the Lambda is intentionally thin:

- ❌ It doesn't validate the body schema (pydantic does that).
- ❌ It doesn't know what any command does (the registry does).
- ❌ It doesn't fetch media (the dispatcher does, only if the command needs it).
- ❌ It doesn't send replies (the command or dispatcher does, after success).
- ❌ It doesn't handle retries (SQS does, on the async side).

If you find yourself adding business logic to `webhook.py`, you're probably putting it in the wrong place. The Lambda is plumbing; the commands are the product.

## 6.13 — Common questions

**Q: Why pydantic and not dataclasses?**
A: Pydantic does the JSON→object conversion for us, with type coercion and validation. We also get discriminated unions (the `Message` field), which is impossible with stdlib dataclasses.

**Q: Why does the handler `await` if it can be called from sync code?**
A: All the integrations (`httpx`, the WhatsApp client) are async. Wrapping them in `asyncio.run` lets us keep the function signatures clean.

**Q: What happens if the Lambda is invoked while the container is still initializing?**
A: Cold start. The first request in a new container pays the import cost (~300ms for the whole package). Subsequent invocations reuse the same container, so it's near-instant.

**Q: Why no authentication on the GET handshake?**
A: The verify token *is* the authentication. Meta sends `hub.verify_token=<our-secret>`; we compare to the value in SSM. If they don't match, we return 403 and the registration fails.

**Q: Why is the dispatcher async if the handler is called from sync?**
A: `asyncio.run` is the bridge. The handler is sync (Lambda signature), the body is async, `asyncio.run` is the boundary. This is the standard pattern for sync-to-async conversion.

## Next

→ [`07-commands.md`](07-commands.md) — the @register decorator pattern, the Command ABC, and a walkthrough of every slash command in the system.
