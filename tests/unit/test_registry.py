"""Tests for :mod:`wactl.commands.registry`."""

from __future__ import annotations

import pytest

from wactl.commands.registry import (
    CommandAlreadyRegisteredError,
    all,
    clear,
    get,
    names,
    register,
)
from wactl.models.command import CommandMeta


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear()
    yield
    clear()


def test_register_attaches_name_and_meta() -> None:
    @register("/ping", sync=True, description="health check")
    class Ping:
        async def run(self, ctx: object) -> object:  # pragma: no cover
            return None

    assert Ping.name == "/ping"
    assert Ping.meta == CommandMeta(name="/ping", sync=True, description="health check")


def test_register_async_marker() -> None:
    @register("/heavy", sync=False, requires_media=True)
    class Heavy:
        async def run(self, ctx: object) -> object:  # pragma: no cover
            return None

    assert Heavy.meta.sync is False
    assert Heavy.meta.requires_media is True


def test_register_requires_slash_prefix() -> None:
    with pytest.raises(ValueError):

        @register("bad-name", sync=True)  # type: ignore[arg-type]
        class Bad:  # pragma: no cover
            async def run(self, ctx: object) -> object: ...


def test_register_duplicate_raises() -> None:
    @register("/dup", sync=True)
    class First:
        async def run(self, ctx: object) -> object: ...

    with pytest.raises(CommandAlreadyRegisteredError):

        @register("/dup", sync=True)
        class Second:  # pragma: no cover
            async def run(self, ctx: object) -> object: ...


def test_get_returns_registered() -> None:
    @register("/get-test", sync=True)
    class GetTest:
        async def run(self, ctx: object) -> object: ...

    assert get("/get-test") is GetTest


def test_get_unknown_returns_none() -> None:
    assert get("/nope") is None


def test_all_returns_copy() -> None:
    @register("/a", sync=True)
    class A:
        async def run(self, ctx: object) -> object: ...

    snapshot = all()
    assert "/a" in snapshot
    # Modifying snapshot doesn't affect the real registry
    snapshot["/injected"] = object()  # type: ignore[index]
    assert get("/injected") is None


def test_names_sorted() -> None:
    @register("/zzz", sync=True)
    class Z:
        async def run(self, ctx: object) -> object: ...

    @register("/aaa", sync=True)
    class A:
        async def run(self, ctx: object) -> object: ...

    assert names() == ["/aaa", "/zzz"]


def test_clear_drops_all() -> None:
    @register("/x", sync=True)
    class X:
        async def run(self, ctx: object) -> object: ...

    assert get("/x") is X
    clear()
    assert get("/x") is None
