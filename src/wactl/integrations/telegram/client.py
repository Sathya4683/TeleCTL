"""HTTP client for the Telegram Bot API.

Thin wrapper around :class:`httpx.AsyncClient` that:

- Builds the URL ``https://api.telegram.org/bot<TOKEN>/<METHOD>`` for every call.
- Always sends ``application/json`` for non-file payloads.
- Parses the standard ``{"ok": bool, "result": ..., "description": ...}``
  envelope via :class:`wactl.models.telegram.TelegramResponse` and raises
  :class:`TelegramApiError` on ``ok=False``.

Reuses one ``AsyncClient`` per process. ``bot token`` is read once at
construction (it's a static secret), so per-request overhead is one
``.post()`` / ``.get()``.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from wactl.models.telegram import ResponseResult, TelegramResponse

logger = structlog.get_logger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramApiError(RuntimeError):
    """Raised when the Bot API returns ``ok=false`` or an HTTP failure."""


class TelegramClient:
    """Asynchronous Telegram Bot API client.

    Parameters
    ----------
    bot_token:
        Bot token issued by `@BotFather` (e.g. ``"123456:ABCDEF..."``).
        The bot fetches it from ``settings.telegram_bot_token`` at startup.
    api_base:
        Override only for local Bot API server or tests. Default is the
        production ``https://api.telegram.org``.
    timeout_seconds:
        HTTP timeout per request. Default 30 s.
    """

    def __init__(
        self,
        bot_token: str,
        *,
        api_base: str = API_BASE,
        timeout_seconds: float = 30.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """Construct the client.

        On AWS Lambda, the container (and our ``TelegramClient`` instance)
        is reused across invocations but a **new event loop is created
        per request**. Any ``httpx.AsyncClient`` we created in a previous
        invocation is bound to a now-dead loop, but ``is_closed()``
        returns ``False`` for it because the underlying TCP socket is
        still alive — making the obvious "recreate if closed" fix
        useless. So we never reuse a client: every call creates + closes
        a fresh one. The overhead is ~1 ms (just socket setup) compared
        to network roundtrip latency.
        """
        if not bot_token:
            raise ValueError("TelegramClient requires a non-empty bot_token")
        self._token = bot_token
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout_seconds
        # Optional pre-built client for tests that want to share a client
        # across instances. ``client`` is always used as-is when provided.
        self._client = client

    @property
    def api_base(self) -> str:
        return self._api_base

    @property
    def bot_token(self) -> str:
        return self._token

    def file_url(self, file_path: str) -> str:
        """Build the download URL for a Telegram-hosted file path.

        ``file_path`` is the value returned by ``/getFile`` — e.g.
        ``"photos/file_0.jpg"``. The host is always the same as the API
        base; the path is appended to ``/file/bot<TOKEN>/``.
        """
        return f"{self._api_base}/file/bot{self._token}/{file_path}"

    def _url(self, method: str) -> str:
        return f"{self._api_base}/bot{self._token}/{method}"

    def _new_http(self) -> httpx.AsyncClient:
        """Build a fresh ``httpx.AsyncClient`` for one request.

        Always creates a new client — see the ``__init__`` docstring for
        why we can't reuse a client across Lambda invocations. Caller is
        responsible for ``aclose()`` (we use ``async with`` everywhere).
        """
        return httpx.AsyncClient(timeout=self._timeout)

    async def _post(self, method: str, payload: dict[str, Any]) -> TelegramResponse:
        """POST a JSON payload, return the parsed envelope."""
        url = self._url(method)
        async with self._new_http() as client:
            resp = await client.post(url, json=payload)
        if resp.status_code >= 400:
            # Capture the response body for diagnostics — Telegram returns
            # ``{"ok": false, "description": "..."}`` on errors.
            raise TelegramApiError(
                f"Telegram API {method} returned HTTP {resp.status_code}: "
                f"{resp.text[:500]!r}"
            )
        data = resp.json()
        envelope = TelegramResponse.model_validate(data)
        if not envelope.ok:
            raise TelegramApiError(
                f"Telegram API {method} returned ok=false: "
                f"{envelope.description!r} (error_code={envelope.error_code})"
            )
        return envelope

    async def _get(self, method: str, params: dict[str, Any] | None = None) -> TelegramResponse:
        """GET a method, return the parsed envelope."""
        url = self._url(method)
        async with self._new_http() as client:
            resp = await client.get(url, params=params or {})
        resp.raise_for_status()
        data = resp.json()
        envelope = TelegramResponse.model_validate(data)
        if not envelope.ok:
            raise TelegramApiError(
                f"Telegram API {method} returned ok=false: "
                f"{envelope.description!r} (error_code={envelope.error_code})"
            )
        return envelope

    async def get_me(self) -> TelegramResponse:
        """Return basic information about the bot."""
        return await self._get("getMe")

    async def set_webhook(self, url: str, *, secret_token: str | None = None) -> TelegramResponse:
        """Register the webhook URL with Telegram.

        ``secret_token`` (optional) sets the ``X-Telegram-Bot-Api-Secret-Token``
        header that Telegram will include on every webhook POST.
        """
        payload: dict[str, Any] = {"url": url}
        if secret_token:
            payload["secret_token"] = secret_token
        return await self._post("setWebhook", payload)

    async def get_file(self, file_id: str) -> TelegramResponse:
        """Resolve ``file_id`` to a downloadable ``file_path``."""
        resp = await self._get("getFile", {"file_id": file_id})
        if isinstance(resp.result, dict):
            resp = resp.model_copy(update={"result": ResponseResult.model_validate(resp.result)})
        return resp

    async def download_file(self, file_path: str) -> bytes:
        """Download bytes for a Telegram file path returned by ``getFile``."""
        async with self._new_http() as client:
            resp = await client.get(self.file_url(file_path))
        resp.raise_for_status()
        return resp.content

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_to_message_id: int | None = None,
        parse_mode: str | None = None,
    ) -> TelegramResponse:
        """Send a text message. ``parse_mode`` is ``"Markdown"``, ``"HTML"``, or None."""
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text}
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        if parse_mode:
            payload["parse_mode"] = parse_mode
        resp = await self._post("sendMessage", payload)
        # Normalize result into a typed shape for callers.
        if isinstance(resp.result, dict):
            resp = resp.model_copy(update={"result": ResponseResult.model_validate(resp.result)})
        return resp

    async def send_chat_action(self, chat_id: int, action: str) -> TelegramResponse:
        """Show a chat action (e.g. ``"typing"``, ``"upload_document"``)."""
        return await self._post(
            "sendChatAction", {"chat_id": chat_id, "action": action}
        )

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramResponse:
        """Send a photo. ``photo`` can be a URL, ``file_id``, or local file upload."""
        payload: dict[str, Any] = {"chat_id": chat_id, "photo": photo}
        if caption:
            payload["caption"] = caption
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendPhoto", payload)

    async def send_document(
        self,
        chat_id: int,
        document: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramResponse:
        """Send a generic file. ``document`` can be a URL, ``file_id``, or local file upload."""
        payload: dict[str, Any] = {"chat_id": chat_id, "document": document}
        if caption:
            payload["caption"] = caption
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendDocument", payload)

    async def send_audio(
        self,
        chat_id: int,
        audio: str,
        *,
        caption: str | None = None,
        title: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramResponse:
        """Send an audio file. ``audio`` is a URL, ``file_id``, or local file upload."""
        payload: dict[str, Any] = {"chat_id": chat_id, "audio": audio}
        if caption:
            payload["caption"] = caption
        if title:
            payload["title"] = title
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendAudio", payload)

    async def send_voice(
        self,
        chat_id: int,
        voice: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramResponse:
        """Send a voice note (OGG/Opus preferred)."""
        payload: dict[str, Any] = {"chat_id": chat_id, "voice": voice}
        if caption:
            payload["caption"] = caption
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendVoice", payload)

    async def send_video(
        self,
        chat_id: int,
        video: str,
        *,
        caption: str | None = None,
        reply_to_message_id: int | None = None,
    ) -> TelegramResponse:
        """Send a video file."""
        payload: dict[str, Any] = {"chat_id": chat_id, "video": video}
        if caption:
            payload["caption"] = caption
        if reply_to_message_id is not None:
            payload["reply_to_message_id"] = reply_to_message_id
        return await self._post("sendVideo", payload)

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()


__all__ = ["API_BASE", "TelegramApiError", "TelegramClient"]
