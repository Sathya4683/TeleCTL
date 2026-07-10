"""Tests for :mod:`wactl.commands.translate`."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import translate as cmd_translate
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_translate_text_input(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """``/translate es hola mundo`` → Spanish reply."""
    called: dict[str, object] = {}

    async def fake_translate(client, text, *, target_language):
        called["text"] = text
        called["lang"] = target_language
        return "Hello world"

    monkeypatch.setattr(
        "wactl.integrations.gemini.text.translate",
        fake_translate,
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_text",
        _capture_send,
    )

    ctx = make_context(
        args="es hola mundo",
        whatsapp=fake_whatsapp,
        gemini=MagicMock(name="gemini"),
    )
    resp = await cmd_translate.TranslateCommand().run(ctx)

    assert resp.success
    assert called["text"] == "hola mundo"
    assert called["lang"] == "es"
    assert called["send_kwargs"]["body"] == "Hello world"
    assert resp.notes["target_language"] == "es"


@pytest.mark.asyncio
async def test_translate_pdf_attachment(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """When given a PDF, text is extracted first then translated."""
    called: dict[str, object] = {}

    monkeypatch.setattr(
        "wactl.commands.translate.pdf_text.extract_text",
        lambda _b: "Hola mundo desde un PDF",
    )

    async def fake_translate(client, text, *, target_language):
        called["text"] = text
        return "Hello world from a PDF"

    monkeypatch.setattr(
        "wactl.integrations.gemini.text.translate",
        fake_translate,
    )
    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_text",
        AsyncMock(return_value="wamid.OUT"),
    )

    ctx = make_context(
        args="en",
        media_bytes=b"%PDF-1.4\n%stuff\n%%EOF",
        media_mime_type="application/pdf",
        whatsapp=fake_whatsapp,
        gemini=MagicMock(name="gemini"),
    )
    resp = await cmd_translate.TranslateCommand().run(ctx)

    assert resp.success
    assert called["text"] == "Hola mundo desde un PDF"
    assert resp.notes["input_chars"] == len("Hola mundo desde un PDF")


@pytest.mark.asyncio
async def test_translate_requires_lang(fake_whatsapp) -> None:
    ctx = make_context(args="", whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_translate.TranslateCommand().run(ctx)


@pytest.mark.asyncio
async def test_translate_requires_input_or_attachment(fake_whatsapp) -> None:
    """Lang provided but no text and no media → user error."""
    ctx = make_context(
        args="es",
        media_bytes=None,
        whatsapp=fake_whatsapp,
        gemini=MagicMock(name="gemini"),
    )
    with pytest.raises(UserInputError):
        await cmd_translate.TranslateCommand().run(ctx)


@pytest.mark.asyncio
async def test_translate_requires_gemini(fake_whatsapp) -> None:
    ctx = make_context(
        args="es hola",
        whatsapp=fake_whatsapp,
        gemini=None,
    )
    with pytest.raises(UserInputError):
        await cmd_translate.TranslateCommand().run(ctx)
