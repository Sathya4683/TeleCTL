"""Central configuration loaded once at process start.

All environment variables are read here. Application code MUST NOT call
``os.getenv(...)`` directly — use :data:`settings`.

Telegram-specific values (bot token, webhook secret token) live as plain
environment variables on the Lambda / EC2 instance — no Secrets Manager /
SSM Parameter Store. Free-tier friendly and one less moving part.
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
    for local development; production overrides via Lambda/worker env vars.
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

    # ── Telegram ───────────────────────────────────────────────────────
    # Bot token issued by @BotFather. Example: "123456:ABCDEF...".
    # In Lambda / EC2, set this as a plain env var (no Secrets Manager).
    telegram_bot_token: str = ""
    # Optional: if set, the webhook verifies the X-Telegram-Bot-Api-Secret-Token
    # header against this value (constant-time compare).
    telegram_webhook_secret_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    # ── Storage / state ────────────────────────────────────────────────
    s3_media_bucket: str = Field(default_factory=lambda: "")
    s3_releases_bucket: str = Field(default_factory=lambda: "")
    sqs_jobs_queue_url: str = Field(default_factory=lambda: "")
    dynamodb_dedup_table: str = "wactl-dedup"
    dedup_ttl_seconds: int = 7 * 24 * 60 * 60  # 7 days

    # ── External services ──────────────────────────────────────────────
    # Gemini API key is read by the /pdf-audio worker directly from env.
    gemini_api_key: str = ""
    gemini_text_model: str = "gemini-2.0-flash"
    gemini_tts_voice: str = "en-US-Journey-D"

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
