import pytest

from app.config import INSECURE_SECRET, Settings, get_settings


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


# --- Production safety validation -----------------------------------------
def test_prod_rejects_insecure_secret():
    with pytest.raises(ValueError, match="APP_SECRET_KEY"):
        Settings(env="prod", app_secret_key=INSECURE_SECRET, seed_demo_user=False)


def test_prod_rejects_demo_user_seeding():
    with pytest.raises(ValueError, match="SEED_DEMO_USER"):
        Settings(env="prod", app_secret_key="a-strong-secret", seed_demo_user=True)


def test_prod_accepts_hardened_config():
    s = Settings(env="production", app_secret_key="a-strong-secret", seed_demo_user=False)
    assert s.is_prod is True
    assert s.secure_cookies is True  # secure cookies default-on in prod


def test_use_real_api_requires_key():
    with pytest.raises(ValueError, match="FURNITURE_API_KEY"):
        Settings(use_real_api=True, furniture_api_key="")


def test_use_real_api_requires_base_url():
    with pytest.raises(ValueError, match="FURNITURE_API_BASE_URL"):
        Settings(use_real_api=True, furniture_api_key="k", furniture_api_base_url="")


def test_secure_cookies_explicit_override():
    assert Settings(env="dev", session_https_only=True).secure_cookies is True
    assert (
        Settings(
            env="prod", app_secret_key="s", seed_demo_user=False, session_https_only=False
        ).secure_cookies
        is False
    )


def test_allowed_host_list_parsing():
    assert Settings(allowed_hosts="a.com, b.com ,").allowed_host_list == ["a.com", "b.com"]
    assert Settings(allowed_hosts=" ").allowed_host_list == ["*"]  # empty falls back to wildcard
