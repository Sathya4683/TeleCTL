"""Tests for :mod:`wactl.commands.pdf_audio`."""

from __future__ import annotations

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import pdf_audio
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_pdf_audio_runs_pipeline(monkeypatch: pytest.MonkeyPatch, fake_telegram) -> None:
    """TTS pipeline (mocked) → upload → audio reply."""
    called: dict[str, object] = {}

    async def fake_synthesize(pdf_bytes: bytes, *, api_key: str, **_kw):
        called["synth_input"] = pdf_bytes
        called["api_key"] = api_key
        return b"mp3-bytes"

    monkeypatch.setattr("wactl.commands.pdf_audio.audiobook.synthesize", fake_synthesize)
    # pdf_audio reads the key via `settings.gemini_api_key`, so patch the
    # settings object's attribute instead of an SSM/Secrets call.
    monkeypatch.setattr(
        "wactl.config.settings.gemini_api_key", "test-key", raising=False
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "999"

    monkeypatch.setattr(
        "wactl.integrations.telegram.messages.send_audio",
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
        telegram=fake_telegram,
    )
    resp = await pdf_audio.PdfAudioCommand().run(ctx)

    assert resp.success
    assert called["synth_input"] == b"%PDF-1.4"
    assert called["api_key"] == "test-key"
    assert called["send_kwargs"]["link"] == "https://signed.example/audio"
    assert called["send_kwargs"]["chat_id"] == 111111111


@pytest.mark.asyncio
async def test_pdf_audio_requires_media(fake_telegram) -> None:
    ctx = make_context(media_bytes=None, telegram=fake_telegram)
    with pytest.raises(UserInputError):
        await pdf_audio.PdfAudioCommand().run(ctx)


def test_pdf_audio_is_async() -> None:
    """/pdf-audio stays async (worker) — long runtime + needs ffmpeg."""
    from wactl.commands.registry import get

    cls = get("/pdf-audio")
    assert cls is not None
    assert cls.meta.sync is False
