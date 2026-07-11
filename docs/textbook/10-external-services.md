# 10 — External Services

WACTL is a glue system. It doesn't do much on its own — it stitches together four external services to give the user a useful product. This chapter walks through each one: what it does for us, what library we use, and what the failure modes look like.

## 10.1 — The four externals

| Service | What we use it for | Library | Auth |
|---|---|---|---|
| **WhatsApp Cloud API** | Inbound webhooks; outbound text + media. | `httpx` (wrapped in `WhatsAppClient`) | System-user access token (SSM). |
| **Google Gemini** | Text summarization, translation, PR summary. | `google-genai` | API key (SSM). |
| **Gemini TTS** | `/pdf-audio` voice synthesis. | `google-genai` (separate model) | Same API key. |
| **GitHub REST API** | `/github-pr` metadata + diff. | `httpx` (raw, no SDK) | Optional PAT. |
| **Public web** | `/web-summary` page fetch. | `httpx` + `BeautifulSoup` + `markdownify` | None. |

Five-ish services, four libraries. No SDKs except for Google.

## 10.2 — WhatsApp Cloud API

### What it is

The [WhatsApp Cloud API](https://developers.facebook.com/docs/whatsapp/cloud-api) is Meta's hosted API for sending and receiving WhatsApp messages at scale. It's the only way to integrate with WhatsApp Business programmatically — there's no "WhatsApp for Developers" self-hosted option.

Two surfaces:

- **Inbound (webhooks).** When a user messages your business number, Meta POSTs a JSON envelope to your webhook URL. You must verify the HMAC and respond within a few seconds.
- **Outbound (REST).** You POST to `https://graph.facebook.com/v<VERSION>/<phone_number_id>/messages` with a JSON body describing the message (text, image, document, etc.). The response is a wamid (message id) and the message is delivered.

Both directions flow through the same Graph API host. We use the same `httpx.AsyncClient` for both.

### Our client wrapper

`src/wactl/integrations/whatsapp/client.py` wraps `httpx.AsyncClient` with retry/backoff:

```python
class WhatsAppClient:
    def __init__(
        self,
        *,
        api_version: str,
        phone_number_id: str,
        access_token: str,
        graph_api_base: str = "https://graph.facebook.com",
        timeout: float = 30.0,
        max_retries: int = 3,
        sleep: Any = asyncio.sleep,
        http_client: httpx.AsyncClient | None = None,
    ):
        ...
        self._http = http_client or httpx.AsyncClient(timeout=timeout)

    @property
    def base_url(self) -> str:
        return f"{self.graph_api_base}/{self.api_version}"

    @property
    def messages_url(self) -> str:
        return f"{self.base_url}/{self.phone_number_id}/messages"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
```

The `messages_url` is `https://graph.facebook.com/v20.0/<phone_number_id>/messages`. The `api_version` is configurable so we can pin a known-good version (currently `v20.0`) and not get surprised by silent breaking changes.

### Retry and backoff

Meta's API has two kinds of failure:

- **Transient** (429, 5xx) — retry with backoff. The retry policy is "Meta-recommended `4^x` backoff": first retry waits 4s, second 16s, third 64s (capped at `META_BACKOFF_MAX_SECONDS = 60`). 429 responses also honor the `Retry-After` header.
- **Permanent** (4xx other than 429) — fail fast. A bad payload isn't going to get better with retries.

We use `tenacity` for the retry loop:

```python
async for attempt in AsyncRetrying(
    stop=stop_after_attempt(self.max_retries),
    wait=wait_exponential(min=1, max=10),
    retry=retry_if_exception_type(_RetryableHTTPError),
    reraise=True,
):
    with attempt:
        return await self._do_post_json(url, body)
```

After all retries are exhausted, the `_RetryableHTTPError` is converted to a `WhatsAppAPIError` with `retryable=True` so the caller knows the failure was transient.

### Outbound message types

`src/wactl/integrations/whatsapp/messages.py` has one function per message type:

| Function | API type | Use case |
|---|---|---|
| `send_text` | `text` | Command hints, summaries, translations. |
| `send_image` | `image` | Resized/compressed images, page screenshots. |
| `send_document` | `document` | Converted PDFs, DOCX files. |
| `send_audio` | `audio` | The `/pdf-audio` output. |
| `send_video` | `video` | Reserved for future use. |
| `send_reaction` | `reaction` | Reserved for future use. |

Each takes the recipient phone, the media (either a pre-uploaded `media_id` or a public `link`), an optional caption, and an optional `reply_to_message_id` (which makes the message appear as a quoted reply in the user's chat).

The payload construction is the only place that knows about Meta's wire format. Commands call `send_image(...)` without ever seeing the JSON.

### Inbound media URLs

When a user sends an image or PDF, the webhook envelope contains a `media_id` — not a URL. The URL is **temporary** (expires in 5 minutes) and must be fetched separately:

```python
# in src/wactl/integrations/whatsapp/media.py
async def resolve_url(client, media_id, *, phone_number_id=None) -> str:
    url = f"{client.base_url}/{media_id}"
    if phone_number_id:
        url += f"?phone_number_id={phone_number_id}"
    payload = await client.get_json(url)
    return str(payload["url"])

async def download(client, media_id, *, phone_number_id=None) -> bytes:
    download_url = await resolve_url(client, media_id, phone_number_id=phone_number_id)
    return await client.get_bytes(download_url)
```

The two-step process (`GET /<media_id>` to get the URL, then `GET <url>` to get the bytes) is required because Meta only returns a media_id on the webhook. The URL itself is signed and short-lived.

The 5-minute expiration is the main reason the worker re-downloads from Meta at the moment of processing (chapter 08): if a job sits in the queue for 6 minutes, the URL is dead.

### Error envelopes

Meta returns errors in a structured envelope:

```json
{
  "error": {
    "message": "Invalid parameter",
    "type": "OAuthException",
    "code": 100,
    "error_subcode": 33,
    "fbtrace_id": "AbCdEf123"
  }
}
```

The `_meta_error_from_response` function translates these into a `WhatsAppAPIError`:

```python
retryable = code in {130429, 190, 2, 4, 17, 341} or resp.status_code in RETRY_STATUS_CODES
return WhatsAppAPIError(
    f"WhatsApp API error code={code}: {message} (trace {fbtrace_id})",
    user_message="We couldn't reach WhatsApp. Please try again.",
    retryable=retryable,
    code=code,
    fbtrace_id=fbtrace_id,
    status=resp.status_code,
)
```

`fbtrace_id` is the most useful field for debugging: include it when filing a support ticket with Meta. The `code` distinguishes transient errors (rate limit, expired token) from permanent ones (bad parameter).

### What can go wrong

| Failure | What we see | What we do |
|---|---|---|
| Rate limit (429) | tenacity backs off and retries | Up to 3 attempts; eventual 200. |
| 5xx | tenacity backs off and retries | Same. |
| Bad token (401) | Permanent error | Log + alert. Token rotation needed. |
| Bad parameter (400) | Permanent error | Log; almost certainly a code bug. |
| Network blip (connection reset) | httpx raises; tenacity retries | Same as 5xx. |
| Meta outage | All calls fail | Users see "try again" replies; CloudWatch alarm fires. |

## 10.3 — Google Gemini (text)

### What it is

[Google Gemini](https://ai.google.dev/gemini-api/docs) is a hosted LLM. We use two models:

- **`gemini-2.0-flash`** for text — fast, cheap, good enough for summarization and translation.
- **`gemini-2.0-flash` with `response_modalities=["AUDIO"]`** for TTS — same model, different modality.

The Python SDK is `google-genai`. The high-level pattern:

```python
from google import genai
from google.genai import types as genai_types

client = genai.Client(api_key=api_key)
resp = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=prompt,
    config=genai_types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=1024,
        system_instruction=SYSTEM_SUMMARIZER,
    ),
)
text = resp.text
```

### Our client wrapper

`src/wactl/integrations/gemini/client.py` wraps the SDK:

```python
class GeminiClient:
    def __init__(self, api_key, *, text_model="gemini-2.0-flash"):
        self._api_key = api_key
        self.text_model = text_model
        self._client = None  # lazy

    @property
    def client(self):
        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate_text(self, prompt, *, system_instruction=None, temperature=0.4, max_output_tokens=1024) -> str:
        config = genai_types.GenerateContentConfig(...)
        try:
            response = await asyncio.to_thread(
                functools.partial(
                    self.client.models.generate_content,
                    model=self.text_model,
                    contents=prompt,
                    config=config,
                )
            )
        except Exception as exc:
            raise ExternalAPIError(f"Gemini text generation failed: {exc}", retryable=True) from exc
        ...
```

The `asyncio.to_thread` is the key detail. The `google-genai` SDK is sync (it uses `requests` under the hood). Calling it directly from async code would block the event loop. `asyncio.to_thread` pushes the blocking call to a thread-pool worker, so the event loop stays free.

The lazy `_client` initialization is for cold-start latency. The `genai.Client(api_key=...)` constructor is non-trivial; we don't want to pay that cost on every command instantiation.

### The three text commands

`src/wactl/integrations/gemini/text.py` has the high-level prompts:

| Function | System instruction | Used by |
|---|---|---|
| `summarize` | "You are a concise summarizer. Produce a clear, bullet-pointed summary..." | `/web-summary`. |
| `translate` | "You are a professional translator. Translate the user's content into the target language..." | `/translate`. |
| `summarize_github_pr` | Same as `summarize`. | `/github-pr`. |

Each builds a single-turn prompt:

```python
async def summarize(client, text, *, max_words=400) -> str:
    prompt = (
        f"Summarize the following content in under {max_words} words. "
        "Use bullet points. Preserve links and key facts.\n\n"
        f"---\n{text}\n---"
    )
    return await client.generate_text(
        prompt,
        system_instruction=SYSTEM_SUMMARIZER,
        temperature=0.2,
        max_output_tokens=min(2048, max_words * 3),
    )
```

The `temperature=0.2` keeps outputs deterministic-ish; the `max_output_tokens` bounds the cost per call.

### Why Gemini specifically

Three reasons:

1. **Quality.** Gemini 2.0 Flash produces coherent summaries of long inputs. Smaller open models I've tested (Llama-3-8B) lose coherence on 5000-word articles.
2. **Cost.** At ~$0.075/1M input tokens (Flash pricing), a 5000-word article summary costs ~$0.0004. Self-hosting an equivalent model would be hundreds per month in GPU time.
3. **Latency.** A single-turn call returns in 1-3 seconds. Streaming is faster to first-token but doesn't help our use case (we send one shot, get one shot back).

The downside: the API key in SSM is a long-lived secret. Rotation is manual. If the key leaks, anyone can run up our bill.

### What can go wrong

| Failure | Effect | Recovery |
|---|---|---|
| Rate limit | `ExternalAPIError(retryable=True)` | Currently no retry; the user gets an error. Future: add tenacity backoff. |
| Long input | Truncation by Gemini or OOM on our side | The 30k char cap in `/web-summary` keeps inputs bounded. |
| Bad prompt | Empty response | `_clean` is a no-op safety belt. |
| API outage | User sees "try again" | CloudWatch alarm fires. |

## 10.4 — Google Gemini TTS

### What it is

Same Gemini API, different config:

```python
config = genai_types.GenerateContentConfig(
    response_modalities=["AUDIO"],
    speech_config=genai_types.SpeechConfig(
        voice_config=genai_types.VoiceConfig(
            prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                voice_name="en-US-Journey-D",
            )
        )
    ),
)
```

The response carries the audio bytes inline:

```python
candidates = resp.candidates
parts = candidates[0].content.parts
for part in parts:
    inline = part.inline_data
    if inline and inline.data:
        return bytes(inline.data)
```

The bytes are WAV at the model-default sample rate. The audiobook service (chapter 07) stitches multiple chunks together and converts to MP3 for delivery.

### Voice options

`en-US-Journey-D` is a single English voice. Gemini supports ~30 voices across many languages; the v1 implementation hardcodes the default. Adding voice selection is a one-line change.

### Cost

TTS is the most expensive thing WACTL does. A 30-page book is ~30 chunks × 2000 chars; each chunk is ~2-5 seconds of synthesis. At Gemini TTS pricing, that's ~$0.05-0.10 per audiobook. A few audiobooks a day adds up.

Mitigation: the `max_chunks=80` cap in `services/audiobook.py` refuses to synthesize more than 80 chunks. That's a soft limit to prevent a 1000-page book from costing $5 in API fees.

## 10.5 — GitHub REST API

### What we use it for

The `/github-pr` command. We need:

1. **PR metadata** — title, body, additions, deletions, changed files.
2. **Unified diff** — for the actual code changes.

Both come from the GitHub REST API v3:

```text
GET https://api.github.com/repos/{owner}/{repo}/pulls/{number}
GET https://github.com/{owner}/{repo}/pull/{number}.diff
```

The first is the structured JSON metadata. The second is the raw diff (which is more useful for summarization than the JSON-patch-style representation).

### Auth

Public repos work without a token, but you're limited to 60 requests/hour per IP. Private repos need a token.

The token is optional; if `ctx._extra["github_token"]` is set, we send it; otherwise we don't. We use a fine-grained PAT in production (scoped to `public_repo` for public repos or the specific private repos we want to support).

### The fetcher

`src/wactl/integrations/github/pr_summary.py` is straightforward:

```python
async def fetch_pr(client, url, *, token=None) -> PullRequestSummary:
    owner, repo, number = parse_pr_url(url)
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    base = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    meta_resp = await client.get(base, headers=headers, timeout=20.0)
    ...
    diff_resp = await client.get(diff_url, headers=raw_headers, timeout=60.0)
    ...
```

The `parse_pr_url` is a strict regex match — we only accept `https://github.com/<owner>/<repo>/pull/<number>`. This rejects issue URLs, commit URLs, and malicious input that might try to inject query parameters.

### What can go wrong

| Failure | Effect | Recovery |
|---|---|---|
| 404 | "We couldn't find that PR." | User checks the URL. |
| 403 (rate limit) | External API error | User waits an hour or supplies a token. |
| 500 from GitHub | External API error | Try again later. |
| PR is huge (> 6000 chars diff) | Truncated at 6000 chars in the prompt | Summary may miss details; future: chunked summarization. |

## 10.6 — Public web (HTML → Markdown)

### What we use it for

`/web-summary` fetches a URL and summarizes it. The pipeline:

```text
URL → httpx GET → bytes
   │
   ├─ BeautifulSoup: parse, strip <script>, <style>, <nav>, <header>, <footer>
   │
   ├─ markdownify: HTML → Markdown
   │
   └─ return FetchedPage(url, title, markdown, bytes_downloaded)
```

The Markdown is the input to Gemini; it's much smaller than the raw HTML (no inline styles, no scripts) and Gemini handles Markdown better than HTML.

### The fetcher

`src/wactl/integrations/web/fetcher.py` is a single function:

```python
async def fetch_and_extract(client, url, *, max_bytes=5*1024*1024, timeout=20.0) -> FetchedPage:
    _validate_url(url)
    try:
        resp = await client.get(url, timeout=timeout, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise ExternalAPIError(...) from exc
    if resp.status_code >= 400:
        raise ExternalAPIError(...)

    body = resp.content[:max_bytes]
    soup = BeautifulSoup(body, "html.parser")
    title = (soup.title.string or "").strip() if soup.title and soup.title.string else ""
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer"]):
        tag.decompose()
    main = soup.body or soup
    markdown = markdownify(str(main), heading_style="ATX", strip=[]).strip()
    return FetchedPage(url=url, title=title, markdown=markdown, bytes_downloaded=len(body))
```

Two safety belts:

1. **`_validate_url`** rejects non-HTTP(S) schemes. We don't want `file://` or `javascript:` URLs in our prompt.
2. **`max_bytes=5MB`** truncates the download at the byte level. A 500MB page is still 5MB in memory; we don't blow Lambda.

### Why not an LLM-based scraper?

Tools like Firecrawl or Jina Reader do "smart" extraction (LLM-based content detection). We don't use them because:

- They cost money per page.
- They add an external dependency.
- For most pages, "everything in `<body>` minus scripts" gets ~80% of the useful content.

The Markdown we produce is good enough for Gemini to summarize.

## 10.7 — Common patterns across integrations

Three patterns repeat:

1. **Async wrapper around a sync SDK.** The Gemini SDK is sync; we wrap calls in `asyncio.to_thread`. The pattern: `await asyncio.to_thread(functools.partial(self.client.method, ...))`.
2. **Retry with backoff.** The WhatsApp client uses `tenacity`. Other clients don't (yet) — failures bubble up as `ExternalAPIError(retryable=True)`.
3. **Typed errors.** Every integration has its own error class (`WhatsAppAPIError`, `ExternalAPIError`, `AWSIntegrationError`). The `user_message` field is what the user sees; the technical `message` is what gets logged.

The `user_message` field is the key abstraction. Commands and the dispatcher don't need to know about Meta's error codes or Gemini's rate limits — they just catch `WactlError` and send `exc.user_message` to the user.

## Next

→ [`11-infrastructure-as-code.md`](11-infrastructure-as-code.md) — the Terraform files, line by line.
