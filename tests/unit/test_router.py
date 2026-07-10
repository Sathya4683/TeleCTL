"""Tests for :mod:`wactl.router`."""

from __future__ import annotations

import pytest

from wactl.commands.registry import clear as clear_registry
from wactl.commands.registry import register
from wactl.exceptions import CommandNotFoundError
from wactl.router import parse, route


@pytest.fixture(autouse=True)
def _reset_registry() -> None:
    clear_registry()
    yield
    clear_registry()


def test_parse_empty_string() -> None:
    assert parse("") == ("", "")
    assert parse("   ") == ("", "")


def test_parse_command_only() -> None:
    assert parse("/pdf-docx") == ("/pdf-docx", "")


def test_parse_command_with_args() -> None:
    assert parse("/image-resize 800 600") == ("/image-resize", "800 600")


def test_parse_strips_whitespace() -> None:
    assert parse("   /cmd   arg with spaces   ") == ("/cmd", "arg with spaces")


def test_parse_preserves_inner_whitespace() -> None:
    assert parse("/translate to spanish") == ("/translate", "to spanish")


def test_route_unknown_command_raises() -> None:
    with pytest.raises(CommandNotFoundError):
        route("/nonexistent")


def test_route_non_slash_prefix_raises() -> None:
    with pytest.raises(CommandNotFoundError):
        route("hello world")


def test_route_with_registered_command() -> None:
    @register("/ping", sync=True)
    class _Ping:
        name = "/ping"
        meta = None  # type: ignore[assignment]

        async def run(self, ctx: object) -> object:  # pragma: no cover
            return None

    routed = route("/ping")
    assert routed.name == "/ping"
    assert routed.cls is _Ping
    assert routed.args == ""


def test_route_with_args() -> None:
    @register("/echo", sync=True)
    class _Echo:
        name = "/echo"
        meta = None  # type: ignore[assignment]

        async def run(self, ctx: object) -> object:  # pragma: no cover
            return None

    routed = route("/echo  hello world  ")
    assert routed.args == "hello world"
