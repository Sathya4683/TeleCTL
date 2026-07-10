"""Tests for :mod:`wactl.commands.merge_pdf`."""

from __future__ import annotations

import pytest

from unit.conftest_helpers import make_context
from wactl.commands import merge_pdf as cmd_merge_pdf
from wactl.exceptions import UserInputError


@pytest.mark.asyncio
async def test_merge_pdf_combines_blobs(monkeypatch: pytest.MonkeyPatch, fake_whatsapp) -> None:
    """Prior + current blob are merged and the result is sent."""
    called: dict[str, object] = {}

    def fake_merge(blobs: list[bytes]) -> bytes:
        called["merge_input"] = blobs
        return b"merged-pdf"

    monkeypatch.setattr(
        "wactl.integrations.converters.merge_pdf.merge",
        fake_merge,
    )

    async def _capture_send(*_a, **kw):
        called["send_kwargs"] = kw
        return "wamid.OUT"

    monkeypatch.setattr(
        "wactl.integrations.whatsapp.messages.send_document",
        _capture_send,
    )

    monkeypatch.setattr(
        "wactl.commands.merge_pdf.s3.put_object",
        lambda *a, **kw: called.update({"put": a}),
    )
    monkeypatch.setattr(
        "wactl.commands.merge_pdf.s3.presigned_get_url",
        lambda *a, **kw: "https://signed.example/merged",
    )

    ctx = make_context(
        media_bytes=b"current",
        media_mime_type="application/pdf",
        whatsapp=fake_whatsapp,
        extra={"pending_pdfs": [b"prior-1", b"prior-2"]},
    )
    resp = await cmd_merge_pdf.MergePdfCommand().run(ctx)

    assert resp.success
    assert called["merge_input"] == [b"prior-1", b"prior-2", b"current"]
    assert called["send_kwargs"]["link"] == "https://signed.example/merged"


@pytest.mark.asyncio
async def test_merge_pdf_requires_media(fake_whatsapp) -> None:
    ctx = make_context(media_bytes=None, whatsapp=fake_whatsapp)
    with pytest.raises(UserInputError):
        await cmd_merge_pdf.MergePdfCommand().run(ctx)
