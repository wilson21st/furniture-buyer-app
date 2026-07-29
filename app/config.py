"""Typed application settings, loaded from environment / .env.

Everything secret or environment-specific flows through here so the rest of the
code never reads os.environ directly and tests can override cleanly.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # App
    app_secret_key: str = "dev-insecure-secret-change-me"
    database_url: str = "sqlite:///./data/app.db"
    env: str = "dev"

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton. Call `get_settings.cache_clear()` in tests."""
    return Settings()
