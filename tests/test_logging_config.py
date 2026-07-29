"""Tests for structured request logging + the in-process rate limiter."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.logging_config import (
    JsonFormatter,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    configure_logging,
    logger,
)


def _app_with_logging() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    return app


def _app_with_rate_limit(per_minute: int) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, per_minute=per_minute, guarded_prefixes=("/buy",))

    @app.post("/buy/{item}")
    def buy(item: str) -> dict:
        return {"item": item}

    @app.get("/free")
    def free() -> dict:
        return {"ok": True}

    return app


def test_json_formatter_includes_context():
    record = logging.LogRecord("x", logging.INFO, "f", 1, "hi", None, None)
    record.context = {"a": 1}
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["msg"] == "hi" and parsed["a"] == 1 and parsed["level"] == "INFO"


def test_configure_logging_is_idempotent():
    configure_logging._done = False  # reset the guard for this test
    configure_logging()
    handlers_after_first = list(logger.handlers)
    configure_logging()  # second call is a no-op
    assert logger.handlers == handlers_after_first


def test_request_logging_adds_request_id_header():
    client = TestClient(_app_with_logging())
    resp = client.get("/ping")
    assert resp.status_code == 200
    assert len(resp.headers["X-Request-ID"]) == 12


def test_rate_limit_blocks_after_threshold():
    client = TestClient(_app_with_rate_limit(per_minute=2))
    assert client.post("/buy/a").status_code == 200
    assert client.post("/buy/a").status_code == 200
    blocked = client.post("/buy/a")
    assert blocked.status_code == 429
    assert "Rate limit" in blocked.json()["detail"]


def test_rate_limit_ignores_unguarded_and_get():
    client = TestClient(_app_with_rate_limit(per_minute=1))
    # GET on the guarded prefix is not counted; unguarded routes are free.
    for _ in range(5):
        assert client.get("/free").status_code == 200


def test_rate_limit_window_expires_old_hits(monkeypatch):
    """A hit older than 60s is evicted, so the client is allowed again."""
    import app.logging_config as lc

    clock = {"t": 0.0}
    monkeypatch.setattr(lc.time, "monotonic", lambda: clock["t"])
    client = TestClient(_app_with_rate_limit(per_minute=1))

    assert client.post("/buy/a").status_code == 200  # fills the window at t=0
    assert client.post("/buy/a").status_code == 429  # still within the window
    clock["t"] = 61.0  # advance past the window
    assert client.post("/buy/a").status_code == 200  # old hit evicted -> allowed
