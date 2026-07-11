"""Central configuration loaded once at process start.

All environment variables are read here. Application code MUST NOT call
``os.getenv(...)`` directly — use :data:`settings`.

Secrets are referenced by SSM Parameter Store name (SecureString). The
actual value is fetched lazily via :mod:`wactl.integrations.aws.secrets`
and cached.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["dev", "staging", "prod"]


class Settings(BaseSettings):
    """Application settings, sourced from environment variables.

    See :file:`.env.example` for the exhaustive list. Defaults are tuned
    for local development; production overrides via Lambda/worker env vars
    or SSM Parameter Store.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Environment / runtime ──────────────────────────────────────────
    env: Environment = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    strict_webhook: bool = True
    debug: bool = False

    # ── AWS ────────────────────────────────────────────────────────────
    aws_region: str = "us-east-1"

    # ── WhatsApp ───────────────────────────────────────────────────────
    whatsapp_api_version: str = "v21.0"
    whatsapp_phone_number_id: str = ""  # populated via SSM or env
    whatsapp_waba_id: str = ""  # informational
    # Secrets Manager ARNs / names. The actual values are fetched lazily.
    # SSM Parameter Store names (SecureString). The actual values are
    # fetched lazily from the parameters under /wactl/whatsapp/*.
    whatsapp_access_token_secret: str = "wactl/whatsapp/access-token"
    whatsapp_app_secret_secret: str = "wactl/whatsapp/app-secret"
    whatsapp_verify_token_secret: str = "wactl/whatsapp/verify-token"

    # ── Storage / state ────────────────────────────────────────────────
    s3_media_bucket: str = Field(default_factory=lambda: "")
    s3_releases_bucket: str = Field(default_factory=lambda: "")
    sqs_jobs_queue_url: str = Field(default_factory=lambda: "")
    dynamodb_dedup_table: str = "wactl-dedup"
    dedup_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days

    # ── External services ──────────────────────────────────────────────
    gemini_api_key_secret: str = "wactl/gemini/api-key"
    gemini_text_model: str = "gemini-2.0-flash"
    gemini_tts_voice: str = "en-US-Journey-D"
    github_token_secret: str = "wactl/github/token"

    # ── HTTP client tuning ────────────────────────────────────────────
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3

    # ── Behavior knobs ─────────────────────────────────────────────────
    audio_chunk_char_limit: int = 2000  # chars per TTS request
    image_max_input_bytes: int = 10 * 1024 * 1024  # 10 MB
    pdf_max_input_bytes: int = 50 * 1024 * 1024  # 50 MB

    # ── Derived helpers ────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        """True when running in production environment."""
        return self.env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-singleton :class:`Settings` instance.

    The cache means the underlying env file is read once per process.
    Tests can call :func:`get_settings.cache_clear` to reset.
    """
    return Settings()


#: Module-level singleton for convenience. Most code reads this directly.
settings = get_settings()


__all__ = ["Environment", "Settings", "get_settings", "settings"]
