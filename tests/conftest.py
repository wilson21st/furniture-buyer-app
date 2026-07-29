"""Shared pytest fixtures.

Every test runs against an isolated temp SQLite file, with Langfuse disabled and
settings/engine caches cleared, so tests never touch real services or leak state.
"""

from __future__ import annotations

import pytest

from app import db, observability
from app.config import get_settings


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch, tmp_path):
    dbfile = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{dbfile}")
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("APP_SECRET_KEY", "test-secret")
    monkeypatch.setenv("FURNITURE_API_BASE_URL", "https://api.test")
    monkeypatch.setenv("FURNITURE_API_KEY", "test-key")
    monkeypatch.setenv("FURNITURE_USER_ID", "u001")
    get_settings.cache_clear()
    db.reset_engine()
    observability.set_client(None)
    yield
    get_settings.cache_clear()
    db.reset_engine()
    observability.set_client(None)
    from app import agent as agent_mod
    from app.main import reset_chat_store

    reset_chat_store()
    agent_mod.set_llm_factory(agent_mod.default_llm)


@pytest.fixture
def initialized_db():
    """Create all tables and return the engine."""
    db.init_db()
    return db.get_engine()


@pytest.fixture
def client(initialized_db):
    """A TestClient with the demo user + placeholder catalogue seeded."""
    from fastapi.testclient import TestClient
    from sqlmodel import Session

    from app import services
    from app.main import create_app

    with Session(initialized_db) as session:
        services.bootstrap_demo(session)
    return TestClient(create_app())
