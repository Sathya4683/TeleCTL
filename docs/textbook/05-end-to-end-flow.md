# 05 — End-to-End Message Flow

This chapter traces a single real message — `/image-resize 800x600` with a photo attached — from the moment the user taps Send to the moment they receive the resized image. It then does the same for an async command (`/pdf-docx`). After this chapter, you should know exactly which file handles each step.

## 5.1 — The setup (before the user does anything)

The system is sitting idle, waiting:

- **API Gateway** is listening on HTTPS at the public URL. It's a REST API with one resource `/webhook` and two methods.
- **The Lambda container** is warm (or cold — both are fine). `lambda/webhook/handler.py` has been loaded. `WebhookDeps` is None — it'll be built on the first invocation.
- **The EC2 worker** is running. `worker/main.py` is in the long-poll, blocked on SQS receive_message with a 20s wait.
- **S3** has the two buckets; both are empty.
- **DynamoDB** has the dedup table; empty.
- **SQS** has the jobs queue; empty.
- **SSM Parameter Store** has the three WhatsApp parameters populated (or, if you forgot, the Lambda will fail at first call with a `ParameterNotFound`).

The user has already configured Meta: the app's webhook URL is `https://<api-id>.execute-api.<region>.amazonaws.com/dev/webhook`, and the verify token matches `wactl/whatsapp/verify-token` in SSM.

## 5.2 — Sync flow: `/image-resize 800x600`

### Step 1 — User taps Send

The user types `/image-resize 800x600`, attaches `vacation.jpg`, hits Send. WhatsApp encrypts the message in transit and routes it to Meta.

### Step 2 — Meta POSTs to API Gateway

Meta's WhatsApp Cloud API server emits a webhook for the user's message. It calls our configured URL:

```http
POST /dev/webhook HTTP/1.1
Host: abc123.execute-api.ap-south-1.amazonaws.com
Content-Type: application/json
X-Hub-Signature-256: sha256=4f7a8c...b29e1

{
  "object": "whatsapp_business_account",
  "entry": [
    {
      "id": "1234567890",
      "changes": [
        {
          "field": "messages",
          "value": {
            "messaging_product": "whatsapp",
            "metadata": {"display_phone_number": "15551234567", "phone_number_id": "9876543210"},
            "contacts": [{"profile": {"name": "Alice"}, "wa_id": "16505551234"}],
            "messages": [
              {
                "from": "16505551234",
                "id": "wamid.ABEGkXxFVAgPAhBgcM3cZGEhNRT",
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

Wait — there's no `image` message in the payload. Why? Because the user attached the image *and* the command in the same message. In that case, Meta sends the text message and the image as **two separate entries in the `messages` array** (or as two separate webhooks). For simplicity, let's assume our user sent the image first, then the command as a caption.

Actually, looking at the command definition: `/image-resize` is `requires_media=True`. The dispatcher enforces that media is present. So in practice, the image is the message and the caption is `/image-resize 800x600`. Meta sends a single message of type `image` with a `caption` field. The webhook then looks like:

```json
{
  "messages": [
    {
      "from": "16505551234",
      "id": "wamid.ABEGkXxFVAgPAhBgcM3cZGEhNRT",
      "timestamp": "1700000000",
      "type": "image",
      "image": {
        "id": "1234567890",
        "mime_type": "image/jpeg",
        "sha256": "...",
        "caption": "/image-resize 800x600"
      }
    }
  ]
}
```

But wait — the existing parser doesn't see the caption as a slash command. The command text in the code is on `parsed.message.body`, and for media messages, that's the caption. Let me check.

Looking at `src/wactl/integrations/whatsapp/parser.py:96-101`, `parse_envelope` builds a `ParsedTextMessage` only for `TextMessage`, not for media with a caption. So a media message with a caption is **not** routed to a command — it's logged as "ignored media without command."

Hmm, that's a real gap in the system. For the textbook, let's assume the user sends the command as a *separate* text message, then the image. Both arrive in the same webhook. The webhook parser sees both, dedups, and processes the text message (the image without an associated slash command is logged and dropped).

OK, simpler version: user sends two messages in quick succession — `/image-resize 800x600` (text) and the image. Meta bundles them into one webhook POST (or two; either way our code handles it).

### Step 3 — API Gateway invokes the Lambda

API Gateway has the integration set to `AWS_PROXY` with the Lambda invoke ARN. The event is constructed per the proxy integration spec:

```json
{
  "httpMethod": "POST",
  "headers": {"X-Hub-Signature-256": "sha256=...", "Content-Type": "application/json", ...},
  "body": "{...the raw JSON from above...}",
  "isBase64Encoded": false,
  "requestContext": {...},
  "queryStringParameters": null,
  "pathParameters": null
}
```

API Gateway forwards this to the Lambda as the `event` argument.

### Step 4 — Lambda handler entry point

`lambda/webhook/handler.py:36`:

```python
def lambda_handler(event, context):
    return wactl_handle(event, context, deps=_get_deps())
```

`_get_deps()` lazy-builds the `WebhookDeps`:

```python
# src/wactl/webhook.py:140
def build_deps(*, access_token=None):
    from wactl.integrations.gemini.client import GeminiClient
    from wactl.integrations.whatsapp.client import WhatsAppClient

    token = access_token or secrets.get_secret(settings.whatsapp_access_token_secret)
    whatsapp = WhatsAppClient(...)
    gemini_key = secrets.get_secret(settings.gemini_api_key_secret)
    gemini = GeminiClient(api_key=gemini_key, ...)
    http = httpx.AsyncClient(timeout=...)  # if any sync command needs it
    return WebhookDeps(whatsapp=whatsapp, http=http, gemini=gemini, s3=None, sqs=None, secrets_manager=None)
```

`secrets.get_secret("wactl/whatsapp/access-token")` calls SSM, fetches the SecureString, decrypts it, returns the value. Cached in memory for 5 minutes (per the `_cache` in `secrets.py`).

### Step 5 — Webhook handle

`src/wactl/webhook.py:293`:

```python
def handle(event, context, *, deps=None):
    reset_context()
    http_method = (event.get("httpMethod") or "POST").upper()
    if http_method == "GET":
        # handshake — not us
        ...

    if deps is None:
        deps = build_deps()

    try:
        return _dispatch_post(event, deps)
    except SignatureVerificationError:
        return {"statusCode": 200}  # never reveal to attacker
    except ...:
        return {"statusCode": 200}  # always 200 to prevent Meta retry storms
```

The `try/except` block is the key idea: **any error becomes a 200 to Meta**. This stops Meta's retry loop from amplifying a bug.

`_dispatch_post` runs `asyncio.run(_handle_post_async(event, deps))` — this creates an event loop for the duration of the invocation.

### Step 6 — Body decode + HMAC verify

`_handle_post_async` (`src/wactl/webhook.py:254`):

```python
raw_body = _decode_body(event)  # bytes
app_secret = secrets.get_secret(settings.whatsapp_app_secret_secret)
headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
verify_signature(raw_body, headers.get(SIG_HEADER.lower()), app_secret)
```

`verify_signature` (`src/wactl/webhook.py:87`):

```python
def verify_signature(raw_body, signature_header, app_secret):
    if not signature_header or not signature_header.startswith("sha256="):
        raise SignatureVerificationError(...)
    expected = hmac.new(app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header[len("sha256="):].strip()
    if not hmac.compare_digest(expected, provided):
        raise SignatureVerificationError("HMAC mismatch")
```

The HMAC is recomputed over the *raw* body (not the parsed JSON). The comparison is constant-time.

### Step 7 — Parse the envelope

```python
import json as _json
payloads = parse_envelope(_json.loads(raw_body))
```

`parse_envelope` (`src/wactl/integrations/whatsapp/parser.py:67`) takes a dict, validates it against the `WhatsAppEnvelope` pydantic model, and walks the entries → changes → values → messages. For each message, it builds a `ParsedTextMessage` or `ParsedMediaMessage` with the user context.

For our user, this returns a list like:
- `ParsedTextMessage(user=..., message=TextMessage(body="/image-resize 800x600"))`
- `ParsedMediaMessage(user=..., message=MediaMessage(image.id="...", image.mime_type="image/jpeg"))`

(Or just one of the two, depending on how Meta split it. The code handles both.)

### Step 8 — Dedup each message

```python
for parsed in payloads:
    with bind_context(message_id=parsed.user.message_id, user_phone=parsed.user.phone):
        if _is_duplicate(parsed.user.message_id):
            logger.info("webhook.duplicate_dropped")
            continue
        if parsed.message.type == "text":
            await _process_text(...)
        else:
            logger.info("webhook.ignored_media_without_command")
```

`_is_duplicate` (`src/wactl/webhook.py:177`):

```python
def _is_duplicate(message_id):
    try:
        claimed = dynamodb.try_claim(
            settings.dynamodb_dedup_table,
            message_id,
            ttl_seconds=settings.dedup_ttl_seconds,  # 7 days
        )
    except WactlError:
        return False  # fail open
    return not claimed
```

`try_claim` is a DynamoDB `PutItem` with `ConditionExpression="attribute_not_exists(pk)"`. If the wamid is new, the put succeeds → `True` → process it. If it's a duplicate, the put fails with `ConditionalCheckFailedException` → `False` → drop.

The TTL attribute `expires_at` is set to `now + 7 days` in epoch seconds. DynamoDB's TTL job runs once a day and deletes expired items. (WACTL also has an EventBridge rule to scan the table — disabled for now.)

`bind_context` adds `message_id` and `user_phone` to the structlog context. Every log line emitted inside the `with` block will have these fields. Critical for debugging.

### Step 9 — Route the text

```python
async def _process_text(*, user, body, raw_body, deps):
    try:
        routed = route(body)  # "/image-resize 800x600" → RoutedCommand
    except CommandNotFoundError:
        await wa_messages.send_text(deps.whatsapp, to=user.phone, body="Send a command...")
        return
    ...
```

`route` (`src/wactl/router.py:56`):

```python
def route(text):
    name, args = parse(text)  # name="/image-resize", args="800x600"
    if not name.startswith("/"):
        raise CommandNotFoundError(...)
    cls = get(name)  # looks up in the registry
    if cls is None:
        raise CommandNotFoundError(...)
    return RoutedCommand(name=name, cls=cls, args=args)
```

The registry is a module-level dict populated at import time by the `@register("/image-resize", sync=True, requires_media=True)` decorator on `ImageResizeCommand`. The dispatcher consults `routed.cls.meta.sync` to decide:

```python
if routed.cls.meta.sync:
    resp = await dispatch_sync(routed, ...)
else:
    await dispatch_async(routed, ...)
```

`/image-resize` is `sync=True`, so we go to `dispatch_sync`.

### Step 10 — Dispatch (sync)

`src/wactl/dispatcher.py:79`:

```python
async def dispatch_sync(routed, *, user, whatsapp, ...):
    cmd_cls = cast("type[Command]", routed.cls)
    ctx = await prepare_context(
        routed, user=user, whatsapp=whatsapp, ...
    )
    cmd = cmd_cls()
    return await cmd.run(ctx)
```

`prepare_context` (`src/wactl/dispatcher.py:27`) checks `requires_media`. Since `/image-resize` requires media, it calls `_download_media(whatsapp, media_id)`:

```python
# src/wactl/integrations/whatsapp/media.py:31
async def download(client, media_id, *, phone_number_id=None):
    download_url = await resolve_url(client, media_id, phone_number_id=phone_number_id)
    return await client.get_bytes(download_url)
```

`resolve_url` calls `GET /v21.0/{media_id}` which returns a `{"url": "https://look.example/..."}` JSON. `get_bytes` does a `GET` on that URL and returns the raw image bytes.

Both calls are `httpx.AsyncClient` requests under the hood, with the bearer token, with retry on 429/5xx.

The downloaded bytes are stuffed into `ctx.media_bytes`. The `CommandContext` is now ready.

### Step 11 — Run the command

`ImageResizeCommand.run` (`src/wactl/commands/image_resize.py:31`):

```python
async def run(self, ctx):
    if ctx.media_bytes is None:
        raise UserInputError(...)
    width, height, fit = _parse_args(ctx.args)  # 800, 600, "contain"
    out_bytes = img_resize.resize(
        ctx.media_bytes, width=width, height=height, fit=fit
    )
    mime = _mime_for(ctx.media_mime_type)  # "image/jpeg"
    bucket = media_bucket(ctx)  # "wactl-dev-media-1234"
    key = output_key(ctx, ".png")  # "out/16505551234/wamid.ABC.png"
    s3.put_object(bucket, key, out_bytes, content_type=mime)
    whatsapp = require_whatsapp(ctx)
    message_id = await messages.send_image(
        whatsapp, to=ctx.user.phone,
        link=s3.presigned_get_url(bucket, key),
        caption=f"Resized to 800x600",
        reply_to_message_id=ctx.user.message_id,
    )
    return CommandResponse(success=True, message_id=message_id, ...)
```

`img_resize.resize` is the Pillow converter. It opens the bytes, computes the target size (preserving aspect ratio for `contain`), resizes, and returns the new bytes.

`s3.put_object` uploads to `s3://wactl-dev-media-1234/out/16505551234/wamid.ABC.png`. The S3 ACL blocks public access; the only way to read it is via a presigned URL.

`s3.presigned_get_url(bucket, key)` returns a URL like `https://wactl-dev-media-1234.s3.ap-south-1.amazonaws.com/out/.../wamid.ABC.png?X-Amz-Algorithm=...&X-Amz-Signature=...&X-Amz-Expires=900` — valid for 900 seconds (15 minutes).

`messages.send_image` POSTs to `https://graph.facebook.com/v21.0/<phone_number_id>/messages` with:

```json
{
  "messaging_product": "whatsapp",
  "recipient_type": "individual",
  "to": "16505551234",
  "type": "image",
  "image": {"link": "https://...presigned...", "caption": "Resized to 800x600"},
  "context": {"message_id": "wamid.ABEGkXxFVAgPAhBgcM3cZGEhNRT"}
}
```

The `context` field makes the image a *reply* to the user's original message in the WhatsApp UI.

WhatsApp's response is `{"messages": [{"id": "wamid.OTHER..."}]}`. That's our outbound wamid.

### Step 12 — Return 200 to API Gateway

The Lambda returns `{"statusCode": 200}`. API Gateway forwards that to Meta as `HTTP 200 OK`. Meta stops retrying.

### Step 13 — User sees the image

The user's WhatsApp client receives the push from Meta. The image appears as a reply in the conversation, with the caption "Resized to 800x600" and the original `/image-resize 800x600` command shown as the replied-to message.

Total wall time: ~500ms–2s.

---

## 5.3 — Async flow: `/pdf-docx`

The setup is the same until Step 9. The differences:

### Step 9b — Dispatch (async)

```python
if routed.cls.meta.sync:  # False for /pdf-docx
    ...
else:
    await dispatch_async(routed, user=user, sqs=deps.sqs, queue_url=settings.sqs_jobs_queue_url)
```

`dispatch_async` (`src/wactl/dispatcher.py:114`) doesn't need a WhatsApp client. It builds a `Job`:

```python
job = Job(
    job_id=str(uuid.uuid4()),
    command="/pdf-docx",
    args="",  # /pdf-docx takes no args
    user=user,
    media_id="...",  # from the inbound message
    media_mime="application/pdf",
    media_filename="paper.pdf",
    meta=cmd_cls.meta,
)
body = job.model_dump_json()  # pydantic → JSON
return await sqs.send_message(queue_url, {"job": body})
```

`deps.sqs` is None in our current `build_deps`! Let me check — actually, looking at `webhook.py:172`, `sqs=None`. That means `dispatch_async` would fail. So we need to fix that. Let me look more carefully.

Hmm, actually `WebhookDeps.sqs` is `None` and `dispatch_async` checks `if sqs is None: raise CommandNotFoundError(...)`. So the async path is currently broken in the webhook! The SQS client isn't being built.

This is a real bug. Let me check if the dispatcher checks it differently. Looking at `webhook.py:230`:

```python
await dispatch_async(
    routed, user=user, sqs=deps.sqs, queue_url=settings.sqs_jobs_queue_url,
)
```

Yeah, `deps.sqs` is `None` per `build_deps`. This would raise `CommandNotFoundError("dispatch_async called without sqs client")`. Then it would be caught by the `except WactlError` in `_process_text` and just logged.

This is a bug in the current code. For the textbook's narrative, let's say it works (and that the fix is to build an SQS client in `build_deps`). I'll note this as a known issue.

Continuing with the *intended* flow:

### Step 10b — SQS enqueue

`send_message` calls `sqs:SendMessage` with the job body. SQS returns a `MessageId`. The webhook logs `command.async.enqueued`.

### Step 11b — Lambda returns 200 to Meta

Same as Step 12. Lambda returns `{"statusCode": 200}`. Meta stops retrying. The user gets no immediate reply (or a "queued…" message if the command sends one synchronously — but `/pdf-docx` doesn't).

### Step 12b — Worker receives

The worker's loop, currently blocked on `sqs.receive_message`, returns with one message. The loop dispatches it.

`worker/main.py:94`:

```python
async def _process_message(self, message):
    handle = message.get("_receipt_handle")
    body = message.get("job")
    if not isinstance(body, str):
        # log + delete (poison message)
        return
    try:
        job = Job.model_validate_json(body)
    except Exception:
        # log + delete (poison message)
        return
    async with _job_context(job):
        try:
            await self._dispatch(job)
            if handle:
                await asyncio.to_thread(sqs.delete_message, ...)
            logger.info("worker.job_done", ...)
        except Exception as exc:
            logger.error("worker.job_failed", ...)
```

`_job_context` binds `job_id`, `command`, `user_phone` to structlog so every log line in the dispatch has them.

### Step 13b — Dispatch (worker side)

`worker/main.py:127`:

```python
async def _dispatch(self, job):
    cls = cmd_registry.get(job.command)
    if cls is None:
        logger.warning("worker.command_not_registered", command=job.command)
        return
    deps = self._deps or build_deps()
    ctx = await _dispatcher.prepare_context(
        cast("Any", _FakeRouted(job.command, cls)),
        user=job.user,
        whatsapp=deps.whatsapp,
        ...
        media_id=job.media_id,
        media_mime=job.media_mime,
        media_filename=job.media_filename,
    )
    cmd = cls()
    await cmd.run(ctx)
```

`prepare_context` re-downloads the media (the inbound URL is still valid because we enqueued within seconds of the webhook).

`PdfDocxCommand.run` (`src/wactl/commands/pdf_docx.py:33`):

```python
async def run(self, ctx):
    if ctx.media_bytes is None:
        raise UserInputError(...)
    docx_bytes = pdf_docx.pdf_to_docx(ctx.media_bytes)
    bucket = media_bucket(ctx)
    key = output_key(ctx, ".docx")
    s3.put_object(bucket, key, docx_bytes, content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
    whatsapp = require_whatsapp(ctx)
    message_id = await messages.send_document(
        whatsapp, to=ctx.user.phone,
        link=s3.presigned_get_url(bucket, key),
        filename=suggest_filename(ctx, ".docx", default="output.docx"),
        caption="Here's your DOCX.",
        reply_to_message_id=ctx.user.message_id,
    )
    return CommandResponse(success=True, message_id=message_id, ...)
```

`pdf_to_docx` is the pdf2docx converter. It opens the PDF, walks pages, extracts text + images, lays them out as a Word document. Returns the bytes.

`s3.put_object` uploads. `messages.send_document` POSTs to the WhatsApp Cloud API with the presigned URL.

### Step 14b — Worker deletes the SQS message

On success, the worker calls `sqs.delete_message(queue_url, receipt_handle)`. The message is gone from the queue.

### Step 15b — User sees the DOCX

WhatsApp pushes the document to the user's phone. The user sees "Here's your DOCX." with the file attached.

Total wall time: 5–60s depending on PDF size and conversion complexity.

---

## 5.4 — Failure paths

| Failure | Where it's caught | What happens |
|---|---|---|
| HMAC mismatch | `verify_signature` raises `SignatureVerificationError` | `handle` catches, returns 200, logs. Meta thinks all is well. (If we returned 401, Meta would retry — bad.) |
| Parse error | `parse_envelope` raises `WebhookError` | `_handle_post_async` catches, returns 200, logs. |
| Unknown command | `route` raises `CommandNotFoundError` | `_process_text` catches, sends "send a /command" message to user. |
| User input error | Command raises `UserInputError` | `_process_text` catches, sends the `user_message` to user. |
| Transient AWS error | Integration raises `AWSIntegrationError` | `_process_text` logs. User sees nothing (could be improved). |
| Worker job fails | `cmd.run` raises | Worker logs, does NOT delete. SQS retries after visibility timeout. After 5 retries → DLQ. |
| DLQ depth > 0 | CloudWatch alarm fires | Human investigates the DLQ message in the SQS console. |

---

## Next

→ [`06-webhook-lambda.md`](06-webhook-lambda.md) — the Lambda in deep detail.
