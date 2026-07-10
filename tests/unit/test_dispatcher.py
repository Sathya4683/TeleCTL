"""Tests for :mod:`wactl.dispatcher`."""

from __future__ import annotations

import pytest

from wactl.commands.registry import clear as clear_registry
from wactl.commands.registry import register
from wactl.exceptions import UserInputError
from wactl.models.user import UserContext


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_registry()
    yield
    clear_registry()


def _user() -> UserContext:
    return UserContext(
        phone="15551234567",
        name="alice",
        message_id="wamid.test",
        waba_id="waba-1",
        phone_number_id="pn-1",
    )


def _routed_sync(name: str = "/greet"):
    @register(name, sync=True)
    class _Cmd:
        async def run(self, ctx):  # pragma: no cover — body overridden in test
            return None

    from wactl.router import route

    return route(name)


# ─── prepare_context ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prepare_context_no_media_required() -> None:
    from wactl.dispatcher import prepare_context

    routed = _routed_sync()
    ctx = await prepare_context(routed, user=_user(), whatsapp=None)
    assert ctx.media_bytes is None
    assert ctx.media_id is None


@pytest.mark.asyncio
async def test_prepare_context_requires_media_but_none_provided() -> None:
    from wactl.commands.registry import clear as clear_registry
    from wactl.dispatcher import prepare_context

    clear_registry()

    @register("/needs-media", sync=True, requires_media=True)
    class _Cmd:
        async def run(self, ctx):
            return None

    from wactl.router import route

    routed = route("/needs-media")
    with pytest.raises(UserInputError):
        await prepare_context(routed, user=_user(), whatsapp=None)


@pytest.mark.asyncio
async def test_prepare_context_requires_media_but_no_whatsapp() -> None:
    from wactl.dispatcher import prepare_context

    @register("/needs-media-2", sync=True, requires_media=True)
    class _Cmd:
        async def run(self, ctx):
            return None

    from wactl.router import route

    routed = route("/needs-media-2")
    with pytest.raises(UserInputError):
        await prepare_context(
            routed,
            user=_user(),
            whatsapp=None,
            media_id="mid-1",
        )


@pytest.mark.asyncio
async def test_prepare_context_downloads_media_when_provided() -> None:
    """When media_id is given AND a whatsapp client is supplied,
    the dispatcher should pull the bytes via the client."""
    import httpx
    import respx

    from wactl.dispatcher import prepare_context
    from wactl.integrations.whatsapp.client import WhatsAppClient

    @register("/dl", sync=True, requires_media=True)
    class _Cmd:
        async def run(self, ctx):
            return None

    from wactl.router import route

    wa = WhatsAppClient(
        api_version="v21.0",
        phone_number_id="pn-1",
        access_token="t",
        max_retries=2,
    )

    routed = route("/dl")

    with respx.mock(assert_all_called=False) as mock:
        mock.get("/v21.0/mid-1").mock(return_value=httpx.Response(200, json={"url": "https://look/b"}))
        mock.get("https://look/b").mock(return_value=httpx.Response(200, content=b"BIN"))

        ctx = await prepare_context(
            routed,
            user=_user(),
            whatsapp=wa,
            media_id="mid-1",
        )

    assert ctx.media_bytes == b"BIN"
    assert ctx.media_id == "mid-1"


# ─── dispatch_sync ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_sync_runs_command() -> None:
    from wactl.dispatcher import dispatch_sync
    from wactl.models.command import CommandResponse

    captured: dict[str, object] = {}

    @register("/captured", sync=True)
    class _Capture:
        async def run(self, ctx):
            captured["user"] = ctx.user
            captured["args"] = ctx.args
            return CommandResponse(success=True, notes={"hello": "world"})

    from wactl.router import route

    routed = route("/captured arg-value")
    resp = await dispatch_sync(routed, user=_user(), whatsapp=None, raw_body="hi")
    assert resp.success
    assert captured["args"] == "arg-value"
    assert captured["user"] == _user()


# ─── dispatch_async ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dispatch_async_enqueues_to_sqs() -> None:
    from wactl.dispatcher import dispatch_async

    @register("/async-cmd", sync=False)
    class _AsyncCmd:
        async def run(self, ctx):
            return None  # pragma: no cover — worker side

    from wactl.router import route

    class _FakeSQS:
        def __init__(self) -> None:
            self.sent: list[dict[str, object]] = []

        async def send_message(self, queue_url: str, body: dict[str, object]) -> str:
            self.sent.append(body)
            return "mid-1"

    sqs = _FakeSQS()
    routed = route("/async-cmd file.pdf")
    mid = await dispatch_async(
        routed,
        user=_user(),
        sqs=sqs,
        queue_url="https://q",
        media_id="m1",
        media_mime="application/pdf",
    )
    assert mid == "mid-1"
    assert len(sqs.sent) == 1
    assert '"command":"/async-cmd"' in str(sqs.sent[0])
