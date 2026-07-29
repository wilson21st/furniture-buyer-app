"""Tests for production-hardening wiring in the app factory + probes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import get_settings


@pytest.fixture
def build_app(monkeypatch):
    """Rebuild the app after applying env overrides, with tables created."""

    def _build(**env: str) -> TestClient:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()
        db.reset_engine()
        db.init_db()
        from app.main import create_app

        return TestClient(create_app())

    return _build


def test_ready_returns_200_when_db_ok(build_app):
    client = build_app()
    resp = client.get("/ready")
    assert resp.status_code == 200 and resp.json() == {"status": "ready"}


def test_ready_returns_503_when_db_down(build_app, monkeypatch):
    client = build_app()
    monkeypatch.setattr(db, "check_connection", lambda: False)
    resp = client.get("/ready")
    assert resp.status_code == 503 and resp.json() == {"status": "not ready"}


def test_rate_limit_disabled_branch(build_app):
    # rate_limit_enabled=false skips the middleware; app still serves.
    client = build_app(RATE_LIMIT_ENABLED="false")
    assert client.get("/health").status_code == 200


def test_trusted_host_allows_listed_and_blocks_others(build_app):
    client = build_app(ALLOWED_HOSTS="testserver")
    assert client.get("/health").status_code == 200
    bad = client.get("/health", headers={"host": "evil.example.com"})
    assert bad.status_code == 400  # TrustedHostMiddleware rejects


def test_force_https_redirects(build_app):
    client = build_app(FORCE_HTTPS="true", ALLOWED_HOSTS="*")
    resp = client.get("/health", follow_redirects=False)
    assert resp.status_code in (301, 307)
    assert resp.headers["location"].startswith("https://")


def test_rate_limit_guards_chat_route(build_app):
    client = build_app(RATE_LIMIT_ENABLED="true", RATE_LIMIT_PER_MINUTE="1")
    # First unauthenticated POST /chat is allowed through (then redirects to login);
    # the second within the window is rate-limited.
    first = client.post("/chat", data={"message": "hi"}, follow_redirects=False)
    assert first.status_code in (303, 307)
    second = client.post("/chat", data={"message": "hi"}, follow_redirects=False)
    assert second.status_code == 429
