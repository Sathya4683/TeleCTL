# 07 — Commands: The Plugin Tree

Every slash command in WACTL is a single class in a single file. Adding a new command is the most common change you make to this codebase, and the plugin system is designed to make that change small and obvious.

This chapter walks the registry pattern from the inside, then tours every existing command.

## 7.1 — The plugin shape

A command is:

1. A class that subclasses `wactl.commands.base.Command`.
2. Has a `@register("/name", sync=..., requires_media=..., description=...)` decorator.
3. Implements `async def run(self, ctx: CommandContext) -> CommandResponse`.

That's the whole contract. A complete command fits in 30 lines of code.

```python
# src/wactl/commands/image_resize.py
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.models.command import CommandResponse


@register("/image-resize", sync=True, requires_media=True, description="Resize an image")
class ImageResizeCommand(Command):
    async def run(self, ctx: CommandContext) -> CommandResponse:
        # ... do the work, send the result to WhatsApp
        return CommandResponse(success=True, ...)
```

The decorator registers the class in a module-level dict. The router looks up that dict by command name. The dispatcher instantiates the class, builds a `CommandContext`, and calls `run()`.

## 7.2 — The `@register` decorator

The decorator lives in `src/wactl/commands/registry.py`:

```python
_REGISTRY: dict[str, type[Any]] = {}


def register(
    name: str,
    *,
    sync: bool = True,
    requires_media: bool = False,
    description: str = "",
) -> Callable[[type[Any]], type[Any]]:
    def _decorator(cls: type[Any]) -> type[Any]:
        if not name.startswith("/"):
            raise ValueError(f"Command name must start with '/', got {name!r}")
        if name in _REGISTRY:
            raise CommandAlreadyRegisteredError(
                f"Command {name!r} already registered to {_REGISTRY[name].__name__}; "
                f"cannot also register {cls.__name__}"
            )
        cls.name = name
        cls.meta = CommandMeta(
            name=name,
            sync=sync,
            requires_media=requires_media,
            description=description,
        )
        _REGISTRY[name] = cls
        return cls
    return _decorator
```

Three things it does:

1. **Validates the name.** Must start with `/` — a copy-paste mistake with a typo (`/pdf_docx` instead of `/pdf-docx`) is caught at import time, not at first invocation.
2. **Catches duplicates.** Two classes decorated with the same name raise `CommandAlreadyRegisteredError`. Prevents silent overwrites that are painful to debug.
3. **Attaches metadata.** The `CommandMeta` object is set as a class attribute. The dispatcher reads `cls.meta.sync` to decide whether to run inline or enqueue; the docs page reads `description`.

The metadata is a frozen pydantic model:

```python
class CommandMeta(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str                # "/pdf-docx"
    sync: bool               # True → Lambda, False → SQS
    requires_media: bool = False
    description: str = ""
```

## 7.3 — The `Command` abstract base class

```python
# src/wactl/commands/base.py
class Command(ABC):
    name: str
    meta: CommandMeta

    @abstractmethod
    async def run(self, ctx: CommandContext) -> CommandResponse:
        """Execute the command. Subclasses override."""
```

Two class-level attributes (`name`, `meta`) and one abstract method (`run`). The ABC is the smallest possible interface — Python's `ABC` machinery makes it impossible to instantiate a `Command` subclass without implementing `run`.

## 7.4 — `CommandContext`: the bag of everything a command needs

`CommandContext` is a value object that carries every dependency a command might need. It's constructed by the dispatcher and passed into `run()`.

```python
class CommandContext:
    __slots__ = (
        "_extra", "args", "gemini", "http", "logger", "media_bytes",
        "media_filename", "media_id", "media_mime_type", "raw_body",
        "s3", "secrets", "sqs", "user", "whatsapp",
    )

    def __init__(
        self,
        *,
        user: UserContext,
        args: str = "",
        raw_body: str = "",
        media_id: str | None = None,
        media_bytes: bytes | None = None,
        media_mime_type: str | None = None,
        media_filename: str | None = None,
        whatsapp: WhatsAppClient | None = None,
        secrets: Any | None = None,
        s3: Any | None = None,
        sqs: Any | None = None,
        http: httpx.AsyncClient | None = None,
        gemini: Any | None = None,
        logger: structlog.stdlib.BoundLogger | None = None,
        **extra: Any,
    ):
        # ... set all the slots
```

Why so many fields? **Dependency injection.** A command never constructs a `boto3` client, never calls `httpx`, never imports `google-genai`. The dispatcher hands it everything it needs as constructor args. This means:

- **Tests can swap any dependency for a fake.** Pass a `FakeS3` instead of a real one and the command never knows.
- **Commands stay declarative.** A command reads as "do this with these inputs" — no hidden state, no module-level globals.
- **Lazy instantiation is centralised.** The dispatcher decides whether to build a WhatsApp client (always) vs. an `httpx` client (only if any command uses one).

The `__slots__` declaration makes `CommandContext` memory-efficient — we create a lot of these (one per message).

The `**_extra` catch-all is the escape hatch for ad-hoc fields (like `pending_pdfs` for `/merge-pdf` or `github_token` for `/github-pr`). Production passes these in; tests can ignore them.

## 7.5 — How a command runs

The dispatch flow looks like this:

```text
Lambda: receives webhook
   │
   ├─ webhook.handle() → route(body) → RoutedCommand(name="/image-resize", cls=ImageResizeCommand, args="800x600")
   │
   ├─ dispatcher.dispatch_sync(routed, user, ...)
   │     │
   │     ├─ cmd = routed.cls()                       ← instantiate
   │     ├─ ctx = CommandContext(user=..., args="800x600", media_bytes=..., ...)
   │     │
   │     └─ resp = await cmd.run(ctx)                ← actual work
   │           │
   │           ├─ resizes the image
   │           ├─ uploads to S3
   │           └─ sends the result back via WhatsApp
   │
   └─ return 200 to Meta
```

The command class itself doesn't know about HTTP requests, JSON, API Gateway, or Meta. It just sees: "I have a user, an image, a target size. Send them the result."

## 7.6 — The helper functions

`src/wactl/commands/_helpers.py` has four small functions every command reuses:

```python
def media_bucket(ctx: CommandContext) -> str:
    """Resolve the S3 bucket for outbound artifacts."""
    extra = getattr(ctx, "_extra", None) or {}
    bucket = extra.get("s3_bucket")
    if bucket:
        return str(bucket)
    return settings.s3_media_bucket or "wactl-media-dev"


def output_key(ctx: CommandContext, suffix: str) -> str:
    """Build a deterministic S3 key for the outbound artifact."""
    safe_user = ctx.user.phone[-10:]  # last 10 digits, no PII leak
    return s3.make_key("out", safe_user, f"{ctx.user.message_id}{suffix}")


def suggest_filename(ctx: CommandContext, suffix: str, *, default: str | None = None) -> str:
    """Build a friendly filename; honors media_filename when present."""


def require_whatsapp(ctx: CommandContext) -> WhatsAppClient:
    """Return the WhatsApp client or raise a user-facing error if it's missing."""
```

Two design choices to note:

- **`output_key` uses only the last 10 digits of the phone number.** Full phone numbers in S3 keys would be a minor PII leak; the last 10 digits are unique enough for object lookup.
- **`require_whatsapp` raises `UserInputError` (not `AssertionError`).** `UserInputError` carries a `user_message` field that gets sent to the user as a friendly reply. Assertions would crash the request with a stack trace in the logs and no message to the user.

## 7.7 — The nine commands

Here's the full surface area, with the library each one uses.

### `/image-resize` — Pillow

Resizes an attached image. Sync (Lambda). Requires media.

```python
@register("/image-resize", sync=True, requires_media=True, ...)
class ImageResizeCommand(Command):
    async def run(self, ctx: CommandContext) -> CommandResponse:
        if ctx.media_bytes is None:
            raise UserInputError("...", user_message="Please attach an image...")

        width, height, fit = _parse_args(ctx.args)
        out_bytes = img_resize.resize(ctx.media_bytes, width=width, height=height, fit=fit)
        bucket = media_bucket(ctx)
        key = output_key(ctx, RESIZE_SUFFIX)
        s3.put_object(bucket, key, out_bytes, content_type=mime)
        await messages.send_image(...)
```

**Args:** `WxH`, `W` (width only), `xH` (height only). Optional `:contain` or `:cover` suffix for fit mode.

**Library:** [Pillow](https://pillow.readthedocs.io/) — the de facto Python imaging library. The actual call is in `src/wactl/integrations/converters/image_resize.py` and uses `PIL.Image.thumbnail()` for the contain fit, `PIL.Image.resize()` with `Image.LANCZOS` resampling for the cover fit.

**Why sync:** A typical photo resize is < 2 seconds, well within Lambda's budget.

### `/image-compress` — Pillow

Recompresses an attached image to a smaller JPEG. Sync. Requires media.

**Args:** `q=70` (quality, 1..95, default 75), `max=1600` (optional max width), `target=200000` (optional target byte count).

**Library:** Pillow. The converter picks the right codec based on the input format; for JPEG it sets `quality=` on `Image.save()`.

**Why sync:** Fast.

### `/pdf-docx` — pdf2docx

Converts a PDF to a Word document. Async (worker). Requires media.

**Args:** none.

**Library:** [pdf2docx](https://github.com/dothinking/pdf2docx) — a wrapper around `PyMuPDF` (a.k.a. `fitz`) that walks the PDF's content streams and rebuilds a `.docx`. Handles tables, images, fonts, multi-column layouts.

**Why async:** A 30-page PDF can take 5–30 seconds; a 200-page book can take minutes. Lambda is billed per ms; the worker is a flat hourly rate.

### `/pdf-audio` — Gemini TTS

Converts a PDF to an audio file (an "audiobook"). Async. Requires media.

**Args:** none (v1 always uses the default English voice).

**Library:** [Google Gemini TTS](https://ai.google.dev/gemini-api/docs/speech-generation) via the `google-genai` SDK. Specifically, the `gemini-2.0-flash` model with the `en-US-Journey-D` voice.

**Pipeline:** This command is the only one that delegates to a `services/` module. The full flow is in `src/wactl/services/audiobook.py`:

```text
PDF bytes
   │
   ├─ pdf_text.extract_text(bytes)              →  string
   │
   ├─ tts.split_into_chunks(text, max_chars=2000)  →  list[str]
   │
   ├─ asyncio.gather(*[synthesize(chunk) for chunk in chunks])  →  list[bytes] (WAV)
   │     (semaphore(4) limits concurrent API calls)
   │
   └─ _concat_wavs_to_mp3(wavs)                 →  bytes (MP3)
```

The chunking keeps each TTS call under ~10 seconds. The semaphore caps concurrent API requests at 4 so a 50-chunk book doesn't open 50 sockets. The WAV→MP3 conversion uses `pydub`, lazily imported because of a Python 3.12 regex issue at module load.

**Why async:** A 30-page book is ~30 chunks × 5s/chunk = 150 seconds of wall time. Way over Lambda's reasonable budget.

### `/merge-pdf` — pypdf

Concatenates several PDFs into one. Async. Requires media.

**Args:** none (v1). The command is invoked after each new PDF is uploaded; the worker reads prior PDFs from a session buffer and concatenates.

**Library:** [pypdf](https://github.com/py-pdf/pypdf) — a pure-Python PDF library. The merger is `pypdf.PdfWriter` with `add_page()` from each input.

**Why async:** Multi-file, unbounded size.

### `/split-pdf` — pypdf + pymupdf

Splits a PDF by page range. Async. Requires media.

**Args:** a range spec like `1-3,5,7-9` (defaults to single-page chunks).

**Library:** [pypdf](https://github.com/py-pdf/pypdf) for the actual split (`PdfWriter` with selected pages). [pymupdf](https://pymupdf.readthedocs.io/) (`fitz`) for `page_count` detection (faster than pypdf for whole-doc reads).

**Why async:** Page-count detection and the write-back can be slow on large PDFs.

### `/web-summary` — httpx + BeautifulSoup + markdownify + Gemini

Fetches a URL, strips the chrome, summarizes with Gemini. Sync.

**Args:** the URL (e.g. `/web-summary https://example.com/article`).

**Libraries:**
- [httpx](https://www.python-httpx.org/) — async HTTP client (the only one we use).
- [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/) — HTML parser.
- [markdownify](https://github.com/matthewwithanm/python-markdownify) — HTML → Markdown converter.
- [google-genai](https://github.com/google-gemini/generative-ai-python) — Gemini SDK.

**Why sync:** One URL fetch + one Gemini call. Typical 5-15 seconds.

**Why Gemini:** The summarization quality is much better than any local model at this size. The cost is ~$0.001 per summary at `gemini-2.5-flash` pricing.

### `/github-pr` — httpx + Gemini

Fetches a GitHub PR, summarizes the diff. Sync.

**Args:** the PR URL (e.g. `/github-pr https://github.com/owner/repo/pull/123`).

**Libraries:**
- [httpx](https://www.python-httpx.org/) — GitHub REST API + raw diff download.
- [google-genai](https://github.com/google-gemini/generative-ai-python) — Gemini.

**Auth:** Optional GitHub PAT via `ctx._extra["github_token"]`. Public repos work without one (60 req/hr limit); private repos need a token.

**Why sync:** One API call + one Gemini call.

### `/translate` — pymupdf + Gemini

Translates text or an attached PDF. Sync.

**Args:** `<lang> [text...]`. First token is the target language code (`es`, `fr`, `de`). If no text follows and an attachment is present, extract from the PDF.

**Libraries:**
- [pymupdf](https://pymupdf.readthedocs.io/) — for `extract_text()` on PDFs.
- [google-genai](https://github.com/google-gemini/generative-ai-python) — for translation.

**Why sync:** A 5-page PDF extracted + translated is < 5 seconds.

## 7.8 — The reply pattern

Every command that produces output follows the same final steps:

1. **Upload to S3.** `s3.put_object(bucket, key, bytes, content_type=mime)`. The bucket is the media bucket; the key is a deterministic path under `out/<last-10-digits-of-phone>/<wamid>.<suffix>`.
2. **Generate a presigned URL.** `s3.presigned_get_url(bucket, key)` — a 5-minute URL WhatsApp can fetch from.
3. **Send the result.** `messages.send_image(...)`, `send_document(...)`, `send_audio(...)`, or `send_text(...)`. Each takes the presigned URL, caption, and reply-to message ID (so it shows up as a quoted reply in the user's chat).
4. **Return a CommandResponse.** The dispatcher doesn't use it for anything other than logging; the work is done.

The 5-minute URL is intentional — it matches WhatsApp's outbound media fetch timeout, and the artifact is deleted from S3 within 24 hours anyway (lifecycle policy).

## 7.9 — Adding a new command

The pattern is intentionally short:

```text
1. Create src/wactl/commands/<name>.py
2. Add an import to src/wactl/commands/__init__.py
3. Add the command to the marketing site's COMMANDS list (web/lib/site.ts)
4. Add tests in tests/unit/test_command_<name>.py
5. (Optional) Add to /help output
```

The body of the new file:

```python
"""``/my-command`` — short description.

Runs sync/async because ...

Args: <arg-spec>

Library: <library>
"""

from wactl.commands._helpers import media_bucket, output_key, require_whatsapp
from wactl.commands.base import Command, CommandContext
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.integrations.aws import s3
from wactl.integrations.whatsapp import messages
from wactl.models.command import CommandResponse


@register("/my-command", sync=True, requires_media=False, description="Do my thing")
class MyCommand(Command):
    async def run(self, ctx: CommandContext) -> CommandResponse:
        # 1. validate args
        if not ctx.args:
            raise UserInputError("...", user_message="Please send ...")

        # 2. do the work (call a converter or integration)
        result_bytes = do_the_thing(ctx.args)

        # 3. upload + reply
        bucket = media_bucket(ctx)
        key = output_key(ctx, ".bin")
        s3.put_object(bucket, key, result_bytes, content_type="application/octet-stream")
        await messages.send_document(...)

        # 4. return
        return CommandResponse(success=True, notes={"bytes": len(result_bytes)})
```

That's the whole thing. The decorator handles registration; the dispatcher handles instantiation; the `_helpers` handle the boilerplate.

## 7.10 — Why this pattern

The plugin + registry pattern is overused in some codebases and underused in others. It's right for WACTL because:

- **New commands are the most common change.** Every new feature is a command; the system exists to host them.
- **Commands share almost no logic.** Each one wraps a different library (`pdf2docx`, `Pillow`, `Gemini`); abstracting them into a base class would gain nothing.
- **Adding a command is a one-PR change.** A contributor doesn't have to touch `webhook.py`, `dispatcher.py`, the routing logic, or the docs site structure. One new file + one new import.
- **Testing is trivial.** Each command class takes a `CommandContext`; tests build a context with a fake `S3` and a fake `WhatsApp` and assert the right calls happened.

The cost is the registry's indirection — to find what handles `/image-resize`, you have to know that `commands.image_resize.ImageResizeCommand` exists. The trade-off is worth it for a system that grows by accretion.

## Next

→ [`08-worker.md`](08-worker.md) — the EC2 worker: long-polling SQS, graceful shutdown, the systemd unit, the Docker build.
