"""Unit tests for HMAC-SHA256 webhook signature verification."""

from __future__ import annotations

import pytest

from wactl.exceptions import SignatureVerificationError
from wactl.integrations.whatsapp.signature import (
    SIGNATURE_PREFIX,
    compute_signature,
    verify_signature,
)


class TestComputeSignature:
    def test_format(self, app_secret: str, raw_body: bytes) -> None:
        sig = compute_signature(app_secret, raw_body)
        assert sig.startswith(SIGNATURE_PREFIX)
        hex_part = sig[len(SIGNATURE_PREFIX) :]
        # 64 hex chars for sha256
        assert len(hex_part) == 64
        int(hex_part, 16)  # raises if not hex

    def test_deterministic(self, app_secret: str, raw_body: bytes) -> None:
        a = compute_signature(app_secret, raw_body)
        b = compute_signature(app_secret, raw_body)
        assert a == b

    def test_different_body_different_signature(self, app_secret: str) -> None:
        a = compute_signature(app_secret, b"hello")
        b = compute_signature(app_secret, b"hello!")
        assert a != b

    def test_different_secret_different_signature(self, raw_body: bytes) -> None:
        a = compute_signature("secret_a", raw_body)
        b = compute_signature("secret_b", raw_body)
        assert a != b


class TestVerifySignature:
    def test_round_trip_succeeds(self, app_secret: str, raw_body: bytes) -> None:
        sig = compute_signature(app_secret, raw_body)
        # Should not raise
        verify_signature(app_secret, raw_body, sig)

    def test_tampered_body_fails(self, app_secret: str, raw_body: bytes) -> None:
        sig = compute_signature(app_secret, raw_body)
        with pytest.raises(SignatureVerificationError):
            verify_signature(app_secret, raw_body + b"tamper", sig)

    def test_wrong_secret_fails(self, app_secret: str, raw_body: bytes) -> None:
        sig = compute_signature(app_secret, raw_body)
        with pytest.raises(SignatureVerificationError):
            verify_signature("wrong_secret", raw_body, sig)

    def test_missing_header_fails(self, app_secret: str, raw_body: bytes) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_signature(app_secret, raw_body, None)

    def test_empty_header_fails(self, app_secret: str, raw_body: bytes) -> None:
        with pytest.raises(SignatureVerificationError):
            verify_signature(app_secret, raw_body, "")

    def test_missing_prefix_fails(self, app_secret: str, raw_body: bytes) -> None:
        sig = compute_signature(app_secret, raw_body)[len(SIGNATURE_PREFIX) :]
        with pytest.raises(SignatureVerificationError):
            verify_signature(app_secret, raw_body, sig)

    def test_constant_time_compare_used(self, app_secret: str, raw_body: bytes) -> None:
        # Verify that the implementation uses hmac.compare_digest. We can't
        # easily prove this without a side-channel; smoke-test that an
        # almost-correct but not-equal signature is rejected.
        sig = compute_signature(app_secret, raw_body)
        # Flip one hex char.
        last_char = sig[-1]
        replacement = "0" if last_char != "0" else "1"
        tampered = sig[:-1] + replacement
        with pytest.raises(SignatureVerificationError):
            verify_signature(app_secret, raw_body, tampered)
