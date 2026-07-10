"""HMAC-SHA256 signature verification for inbound Meta webhooks.

Meta signs every inbound POST with a header of the form::

    X-Hub-Signature-256: sha256=<hex(hmac_sha256(app_secret, raw_body))>

We must verify against the **raw** body, not the JSON-parsed dict. The
Lambda event provides this via ``event["body"]`` (which may be
base64-encoded if the payload was binary).
"""

from __future__ import annotations

import hashlib
import hmac

from wactl.exceptions import SignatureVerificationError

#: Header name Meta sends.
SIGNATURE_HEADER = "X-Hub-Signature-256"
#: Algorithm prefix used in the header value.
SIGNATURE_PREFIX = "sha256="


def compute_signature(app_secret: str, raw_body: bytes) -> str:
    """Return the full header value (``sha256=<hex>``) for ``raw_body``."""
    mac = hmac.new(
        app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    )
    return SIGNATURE_PREFIX + mac.hexdigest()


def verify_signature(
    app_secret: str,
    raw_body: bytes,
    signature_header: str | None,
) -> None:
    """Verify a webhook signature; raise :class:`SignatureVerificationError` on mismatch.

    ``signature_header`` is the full ``X-Hub-Signature-256`` value (with
    ``sha256=`` prefix). Returns silently on match.
    """
    if not signature_header:
        raise SignatureVerificationError(
            "Missing X-Hub-Signature-256 header",
        )
    if not signature_header.startswith(SIGNATURE_PREFIX):
        raise SignatureVerificationError(
            f"Signature header missing '{SIGNATURE_PREFIX}' prefix",
        )

    expected = compute_signature(app_secret, raw_body)
    if not hmac.compare_digest(expected, signature_header):
        raise SignatureVerificationError(
            "HMAC signature mismatch",
        )


__all__ = [
    "SIGNATURE_HEADER",
    "SIGNATURE_PREFIX",
    "compute_signature",
    "verify_signature",
]
