"""Typed exception hierarchy for WACTL.

Application code raises these instead of bare :class:`Exception`. Integrations
translate raw library errors (botocore, httpx, pydantic) into these at the
boundary so the rest of the codebase never sees vendor-specific types.

A short summary::

    WactlError                              # base
    ├── ConfigError                         # bad configuration
    ├── WebhookError                        # webhook payload problems
    │   ├── SignatureVerificationError     # HMAC mismatch
    │   └── DuplicateMessageError           # dedup hit
    ├── CommandError                        # command dispatch / execution
    │   ├── CommandNotFoundError            # unknown /
    │   ├── UserInputError                  # bad user input (4xx-equivalent)
    │   └── CommandTimeoutError             # exceeded allowed budget
    ├── IntegrationError                    # generic I/O failure
    │   ├── AWSIntegrationError             # S3 / SQS / DDB / Secrets
    │   ├── WhatsAppAPIError                # Meta Graph API
    │   └── ExternalAPIError                # Gemini, GitHub, etc.
    └── ConverterError                      # pdf2docx, pymupdf, Pillow

Each exception carries a ``user_message`` (safe to send to the user) and an
optional ``retryable`` flag (worker uses it to decide between retry and DLQ).
"""

from __future__ import annotations


class WactlError(Exception):
    """Base for all WACTL-originated errors.

    :param message: technical detail for logs.
    :param user_message: friendly detail safe to send to the WhatsApp user.
    :param retryable: whether the worker should retry on failure.
    """

    user_message: str = "Something went wrong. Please try again."
    retryable: bool = False

    def __init__(
        self,
        message: str = "",
        *,
        user_message: str | None = None,
        retryable: bool | None = None,
        **context: object,
    ) -> None:
        super().__init__(message or self.__class__.__name__)
        self.message = message or self.__class__.__name__
        if user_message is not None:
            self.user_message = user_message
        if retryable is not None:
            self.retryable = retryable
        self.context: dict[str, object] = dict(context)


# ─── Configuration ──────────────────────────────────────────────────────


class ConfigError(WactlError):
    """Application is misconfigured (missing required env var, etc.)."""

    user_message = "Service is temporarily unavailable."
    retryable = False


# ─── Webhook ────────────────────────────────────────────────────────────


class WebhookError(WactlError):
    """Problem with an incoming webhook payload."""

    user_message = "We couldn't process your message."
    retryable = False


class SignatureVerificationError(WebhookError):
    """HMAC-SHA256 signature on a webhook is invalid."""

    user_message = ""
    retryable = False


class DuplicateMessageError(WebhookError):
    """Message has already been processed (DynamoDB dedup hit)."""

    user_message = ""
    retryable = False


# ─── Command ────────────────────────────────────────────────────────────


class CommandError(WactlError):
    """Problem dispatching or executing a command."""


class CommandNotFoundError(CommandError):
    """User typed a command name that is not registered."""

    user_message = "Unknown command. Send /help for a list."
    retryable = False


class UserInputError(CommandError):
    """User provided bad input — file type, missing args, etc.

    These are reported back to the user; they should not raise alarms.
    """

    user_message = "Your request couldn't be processed. Please check your input."
    retryable = False


class CommandTimeoutError(CommandError):
    """Command exceeded its allowed time budget."""

    user_message = "This took too long. Please try a smaller file."
    retryable = True


# ─── Integration ────────────────────────────────────────────────────────


class IntegrationError(WactlError):
    """A wrapped external API call failed."""


class AWSIntegrationError(IntegrationError):
    """An AWS SDK call (boto3) failed."""

    user_message = "Our storage system is having trouble. Please try again."
    retryable = True


class WhatsAppAPIError(IntegrationError):
    """The Meta WhatsApp Cloud API returned an error response.

    Carries the upstream error code for diagnostics. ``code 130429`` (rate
    limit) and ``code 190`` (token expired) get special handling.
    """

    user_message = "We couldn't reach WhatsApp. Please try again."
    retryable = True

    def __init__(
        self,
        message: str = "",
        *,
        user_message: str | None = None,
        retryable: bool | None = None,
        code: int | None = None,
        fbtrace_id: str | None = None,
        status: int | None = None,
        **context: object,
    ) -> None:
        super().__init__(message, user_message=user_message, retryable=retryable, **context)
        self.code = code
        self.fbtrace_id = fbtrace_id
        self.status = status


class ExternalAPIError(IntegrationError):
    """A non-Meta external API (Gemini, GitHub, ...) failed."""

    user_message = "An external service failed. Please try again."
    retryable = True


# ─── Converter ──────────────────────────────────────────────────────────


class ConverterError(WactlError):
    """Document / image conversion failed."""

    user_message = "We couldn't process your file. Make sure it's a valid PDF or image."
    retryable = False


__all__ = [
    "AWSIntegrationError",
    "CommandError",
    "CommandNotFoundError",
    "CommandTimeoutError",
    "ConfigError",
    "ConverterError",
    "DuplicateMessageError",
    "ExternalAPIError",
    "IntegrationError",
    "SignatureVerificationError",
    "UserInputError",
    "WactlError",
    "WebhookError",
    "WhatsAppAPIError",
]
