"""SQLite engine + session management (SQLModel)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, text

from app.config import get_settings

_engine = None


def get_engine():
    """Lazily build (and cache) the SQLModel engine from settings."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_url
        connect_args: dict = {}
        if settings.is_sqlite:
            connect_args = {"check_same_thread": False}
            # Ensure the parent directory exists for file-backed SQLite.
            path = url.split("sqlite:///")[-1]
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(url, connect_args=connect_args)
    return _engine


def init_db() -> None:
    """Create all tables. Imports models so metadata is populated."""
    import app.models  # noqa: F401

    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yield a session bound to the engine."""
    with Session(get_engine()) as session:
        yield session


def check_connection() -> bool:
    """Readiness probe: return True iff the database answers a trivial query."""
    try:
        with Session(get_engine()) as session:
            session.exec(text("SELECT 1"))
        return True
    except Exception:  # noqa: BLE001 - any failure means "not ready"
        return False


def reset_engine() -> None:
    """Test helper: forget the cached engine so a new DATABASE_URL takes effect."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None
