"""Structured JSON request logging + a tiny in-process rate limiter.

Langfuse traces LLM/tool activity; this covers ordinary HTTP requests and errors
that Langfuse never sees. One log line per request as JSON: method, path, status,
duration, and a per-request id. The rate limiter is a minimal fixed-window counter
guarding spend-capable routes — enough for a single-instance deploy; swap for Redis
if you scale out.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger("app.request")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        extra = getattr(record, "context", None)
        if isinstance(extra, dict):
            payload.update(extra)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Attach a single JSON handler to the app logger (idempotent)."""
    if getattr(configure_logging, "_done", False):
        return
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.setLevel(level)
    logger.handlers = [handler]
    logger.propagate = False
    configure_logging._done = True  # type: ignore[attr-defined]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured JSON line per request with a correlation id."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = uuid.uuid4().hex[:12]
        start = time.perf_counter()
        request.state.request_id = request_id
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "request",
            extra={
                "context": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                }
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-client rate limit on spend-capable POST routes."""

    def __init__(self, app, *, per_minute: int, guarded_prefixes: tuple[str, ...]):
        super().__init__(app)
        self.per_minute = per_minute
        self.guarded = guarded_prefixes
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _guarded(self, request: Request) -> bool:
        return request.method == "POST" and any(
            request.url.path.startswith(p) for p in self.guarded
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._guarded(request):
            return await call_next(request)
        client = request.client.host if request.client else "anon"
        now = time.monotonic()
        window = self._hits[client]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self.per_minute:
            return JSONResponse(
                {"detail": "Rate limit exceeded. Please slow down."}, status_code=429
            )
        window.append(now)
        return await call_next(request)
