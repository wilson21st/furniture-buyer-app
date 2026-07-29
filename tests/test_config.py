from app.config import Settings, get_settings


def test_env_overrides_defaults(monkeypatch):
    monkeypatch.setenv("FURNITURE_API_KEY", "abc123")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.furniture_api_key == "abc123"
    assert settings.anthropic_model  # default still present


def test_is_sqlite_property():
    assert Settings(database_url="sqlite:///x.db").is_sqlite is True
    assert Settings(database_url="postgresql://u@h/db").is_sqlite is False


def test_get_settings_is_cached():
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_langfuse_disabled_by_default():
    assert Settings().langfuse_enabled is False
