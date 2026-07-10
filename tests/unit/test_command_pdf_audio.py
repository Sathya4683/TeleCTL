"""Tests for :mod:`wactl.commands.pdf_audio`."""

from __future__ import annotations

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import pdf_audio
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_pdf_audio_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """TTS pipeline (mocked) → upload → audio reply."""
    called: dict[str, object] = {}

    async def fake_synthesize(pdf_bytes: bytes, *, api_key: str, **_kw):
        called["synth_input"] = pdf_bytes
        called["api_key"] = api_key
        return b"mp3-bytes"

    monkeypatch.setattr("wactl.commands.pdf_audio.audiobook.synthesize", fake_synthesize)
    monkeypatch.setattr(
        "wactl.commands.pdf_audio.aws_secrets.get_secret",
        lambda name: "test-key",
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_audio",
        _capture_send,
    )

    monkeypatch.setattr(
        "wactl.commands.pdf_audio.s3.put_object",
        lambda *a, **kw: called.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.pdf_audio.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/audio",
    )

    ctx = make_context(
        media_bytes=b"%PDF-1.4",
        media_mime_type="application/pdf",
        whatsapp=fake_whatsapp,
    )
    resp = await pdf_audio.PdfAudioCommand().run(ctx)

    assert resp.success
    assert called["synth_input"] == b"%PDF-1.4"
    assert called["api_key"] == "test-key"
    assert called["send_kwargs"]["link"] == "https://signed.example/audio"


@pytest.mark.asyncio
async def test_pdf_audio_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await pdf_audio.PdfAudioCommand().run(ctx)
