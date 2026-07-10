"""Unit tests for the WhatsApp envelope parser."""

from __future__ import annotations

import pytest

from wactl.exceptions import WebhookError
from wactl.integrations.whatsapp.parser import (
    first_media,
    first_text,
    parse_envelope,
)
from wactl.models.webhook import MediaMessage, TextMessage


class TestParseTextMessage:
    def test_basic(self, sample_text_webhook: dict) -> None:
        msgs = parse_envelope(sample_text_webhook)
        assert len(msgs) == 1
        msg = msgs[0]
        assert isinstance(msg.message, TextMessage)
        assert msg.body == "/pdf-docx"
        assert msg.user.phone == "16505551234"
        assert msg.user.name == "Sheena Nelson"
        assert msg.user.phone_number_id == "106540352242922"
        assert msg.user.waba_id == "102290129340398"
        assert msg.user.message_id.startswith("wamid.")

    def test_text_only_helper(self, sample_text_webhook: dict) -> None:
        msgs = parse_envelope(sample_text_webhook)
        text = first_text(msgs)
        assert text is not None
        assert text.body == "/pdf-docx"
        assert first_media(msgs) is None


class TestParseMediaMessage:
    def test_image(self, sample_image_webhook: dict) -> None:
        msgs = parse_envelope(sample_image_webhook)
        assert len(msgs) == 1
        msg = msgs[0]
        assert isinstance(msg.message, MediaMessage)
        assert msg.message.type == "image"
        assert msg.media_id == "MEDIA_ID_AAA"
        assert msg.mime_type == "image/jpeg"
        assert msg.message.media_caption == "Make this smaller please"

    def test_document(self, sample_document_webhook: dict) -> None:
        msgs = parse_envelope(sample_document_webhook)
        assert len(msgs) == 1
        msg = msgs[0]
        assert isinstance(msg.message, MediaMessage)
        assert msg.message.type == "document"
        assert msg.media_id == "MEDIA_ID_BBB"
        assert msg.mime_type == "application/pdf"
        assert msg.message.media_filename == "report.pdf"
        assert msg.message.media_caption == "Convert this"


class TestStatusOnly:
    def test_status_returns_empty_list(self, sample_status_webhook: dict) -> None:
        msgs = parse_envelope(sample_status_webhook)
        assert msgs == []
        assert first_text(msgs) is None
        assert first_media(msgs) is None


class TestInvalidEnvelope:
    def test_missing_object_raises(self) -> None:
        with pytest.raises(WebhookError):
            parse_envelope({"entry": []})

    def test_wrong_object_raises(self) -> None:
        with pytest.raises(WebhookError):
            parse_envelope({"object": "instagram", "entry": []})

    def test_garbage_raises(self) -> None:
        with pytest.raises(WebhookError):
            parse_envelope({"this": "is garbage"})
