"""Tests for :mod:`wactl.commands.help`."""

from __future__ import annotations

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import help as cmd_help
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_help_lists_only_registered_commands(
    monkeypatch: pytest.MonkeyPatch, fake_telegram
) -> None:
    """``/help`` reports the names + descriptions of every registered command."""
    captured: dict[str, object] = {}

    async def _capture_send(telegram, *, chat_id, text, **kwargs):
        captured["text"] = text
        captured["chat_id"] = chat_id
        captured["kwargs"] = kwargs
        return "999"

    monkeypatch.setattr(
        "wactl.commands.help.messages.send_text", _capture_send
    )

    ctx = make_context(telegram=fake_telegram)
    resp = await cmd_help.HelpCommand().run(ctx)

    assert resp.success
    text = captured["text"]
    assert isinstance(text, str)
    assert text.startswith("Available commands")
    # Every registered command should be present in the listing.
    for name in ("/help", "/image-resize", "/image-compress", "/pdf-docx", "/pdf-audio"):
        assert name in text, f"{name} missing from help text"
    # Sync vs async tag is shown for async commands.
    assert "(async)" in text
    assert "chat_id" in captured
    assert captured["chat_id"] == 111111111


@pytest.mark.asyncio
async def test_help_requires_telegram(fake_telegram) -> None:
    ctx = make_context(telegram=None)
    with pytest.raises(UserInputError):
        await cmd_help.HelpCommand().run(ctx)
