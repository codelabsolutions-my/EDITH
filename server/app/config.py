"""Application configuration via pydantic-settings.

Settings load from the process environment and ``server/.env`` (gitignored). The
variable names here are the project's config contract — keep them in sync with
``.env.example`` and ``docker-compose.yml``.

Required-at-startup secrets are validated by :meth:`Settings.require_runtime`,
called from the app factory so a misconfigured deploy fails fast (engineering.md).
``ILMU_API_KEY`` is intentionally *optional*: without it the voice/LLM path stays
stubbed, but auth + DB + the text agent run.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings. One instance per process (see :func:`get_settings`)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ─── App ───────────────────────────────────────────────────────────────
    ENV: str = "development"
    LOG_LEVEL: str = "info"

    # ─── Database ──────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://edith:edith@localhost:5434/edith"

    # ─── Auth: our session JWTs ────────────────────────────────────────────
    JWT_SECRET: str = ""
    JWT_ACCESS_TTL_SECONDS: int = 900
    JWT_REFRESH_TTL_SECONDS: int = 2592000
    TOKEN_ENCRYPTION_KEY: str = ""  # base64; encrypts OAuth *_enc tokens at rest (P2)

    # ─── OAuth relying party (Google APIs — Gmail read-only, P2) ───────────
    # Create an OAuth client in Google Cloud Console and add
    # {PUBLIC_BASE_URL}/integrations/google/callback as an authorized redirect URI.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    # Extra accepted id_token audiences (comma-separated): the Android / iOS OAuth
    # client IDs, since native Google Sign-In issues id_tokens with those as aud.
    GOOGLE_ALLOWED_AUDIENCES: str = ""

    @property
    def google_audiences(self) -> list[str]:
        """All client IDs whose id_tokens we accept (web + mobile)."""
        extra = [a.strip() for a in self.GOOGLE_ALLOWED_AUDIENCES.split(",") if a.strip()]
        return [a for a in (self.GOOGLE_CLIENT_ID, *extra) if a]

    # Public origin used to build OAuth redirect URIs (no trailing slash).
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    # ─── Email: Gmail via IMAP (dev path; preferred path is OAuth above) ───
    # Set GMAIL_ADDRESS + GMAIL_APP_PASSWORD (a Google App Password, not your
    # login password) to let EDITH read your inbox. Empty => the email tools stay
    # inert and report they need connecting.
    GMAIL_ADDRESS: str = ""
    GMAIL_APP_PASSWORD: str = ""
    GMAIL_IMAP_HOST: str = "imap.gmail.com"

    # ─── WhatsApp Business Cloud API (P4 — compliant send channel) ─────────
    # EDITH's own number via the official Cloud API. NEVER WhatsApp Web scraping.
    # Personal-assist (reading your own WhatsApp) is Android on-device, not here.
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_API_VERSION: str = "v21.0"

    # ─── Proactivity (P3): scheduler + push ────────────────────────────────
    PROACTIVE_POLL_SECONDS: float = 30.0
    # Firebase project id for FCM HTTP v1 push. Without it (and a service-account
    # token provider) push is logged, not delivered.
    FCM_PROJECT_ID: str = ""

    # ─── ILMU (OpenAI-compatible) ──────────────────────────────────────────
    ILMU_API_BASE: str = ""
    ILMU_API_KEY: str = ""  # optional: empty => voice/LLM stays stubbed
    ILMU_TOOL_MODEL: str = "nemo-super"
    ILMU_GEN_MODEL: str = "ilmu-v3.1"
    ILMU_ASR_MODEL: str = ""
    ILMU_TTS_MODEL: str = ""
    ILMU_TTS_VOICE: str = ""
    ILMU_EMBED_MODEL: str = ""

    @property
    def is_production(self) -> bool:
        return self.ENV.lower() in ("production", "prod")

    @property
    def voice_enabled(self) -> bool:
        """True when an ILMU key is configured; otherwise voice/LLM stays stubbed."""
        return bool(self.ILMU_API_KEY)

    def require_runtime(self) -> None:
        """Fail fast if a secret required to run is missing or insecure.

        ``ILMU_API_KEY`` is *not* required (voice stays stubbed without it).
        """
        missing: list[str] = []
        if not self.JWT_SECRET:
            missing.append("JWT_SECRET")
        if not self.DATABASE_URL:
            missing.append("DATABASE_URL")
        if missing:
            raise RuntimeError(f"missing required configuration: {', '.join(missing)}")
        if self.is_production and self.JWT_SECRET.startswith("dev-only"):
            raise RuntimeError("JWT_SECRET is a dev placeholder but ENV is production")


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings_cache() -> None:
    """Clear the cached settings (tests that mutate the environment)."""
    global _settings
    _settings = None
