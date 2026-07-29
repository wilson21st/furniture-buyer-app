"""Typed application settings, loaded from environment / .env.

Everything secret or environment-specific flows through here so the rest of the
code never reads os.environ directly and tests can override cleanly.

Production safety: when ``env`` is ``prod`` (or ``use_real_api`` is on) the settings
fail fast at startup if a required secret is missing or left at its insecure default,
rather than booting a subtly broken/insecure app.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_SECRET = "dev-insecure-secret-change-me"  # nosec B105 - sentinel rejected in prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_secret_key: str = INSECURE_SECRET
    database_url: str = "sqlite:///./data/app.db"
    env: str = "dev"

    # Web hardening (applied by the app factory outside dev)
    allowed_hosts: str = "*"  # comma-separated host allow-list for TrustedHostMiddleware
    force_https: bool = False  # redirect http->https (enable behind a TLS-terminating proxy)
    session_https_only: bool | None = None  # None => secure cookies iff is_prod
    seed_demo_user: bool = True  # seed the known-credential demo user (must be off in prod)

    # Rate limiting (in-process; applied to spend-capable routes)
    rate_limit_enabled: bool = True
    rate_limit_per_minute: int = 60

    # Furniture shop API (Steps 3–6)
    furniture_api_base_url: str = "https://day1.training.cognitivo.com.au"
    furniture_api_key: str = ""
    furniture_user_id: str = "u001"
    # When true, catalogue/balance/orders come from the real API (Step 5+).
    # When false, the app runs fully on local SQLite (Level 1).
    use_real_api: bool = False

    # Shared read-only catalogue (Step 2 seed)
    catalogue_mongo_uri: str = ""

    # Anthropic (Step 6 agent, Step 8 generation)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-8"

    # Embeddings for RAG (Step 8)
    voyage_api_key: str = ""
    embedding_model: str = "voyage-3"

    # Langfuse runtime observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_enabled: bool = False

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def is_prod(self) -> bool:
        return self.env.lower() in {"prod", "production"}

    @property
    def secure_cookies(self) -> bool:
        """Whether session cookies get Secure+HTTPS-only flags."""
        return self.is_prod if self.session_https_only is None else self.session_https_only

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()] or ["*"]

    @model_validator(mode="after")
    def _validate_production(self) -> Settings:
        """Fail fast on insecure/missing config where it actually matters."""
        errors: list[str] = []
        if self.is_prod:
            if self.app_secret_key == INSECURE_SECRET or not self.app_secret_key:
                errors.append("APP_SECRET_KEY must be set to a strong value in prod.")
            if self.seed_demo_user:
                errors.append("SEED_DEMO_USER must be false in prod (known-credential user).")
        if self.use_real_api:
            if not self.furniture_api_key:
                errors.append("FURNITURE_API_KEY is required when USE_REAL_API is true.")
            if not self.furniture_api_base_url:
                errors.append("FURNITURE_API_BASE_URL is required when USE_REAL_API is true.")
        if errors:
            raise ValueError("Invalid production configuration:\n- " + "\n- ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call `get_settings.cache_clear()` in tests."""
    return Settings()
