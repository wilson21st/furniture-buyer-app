"""Langfuse runtime observability — the single import surface for the whole app.

Design goals:
- **Off by default.** When ``LANGFUSE_ENABLED`` is false (dev + the test suite),
  every helper here is a no-op, so we never make a network call unexpectedly.
- **One place to change.** Agent turns, tool calls, embeddings and generations all
  go through ``span`` / ``record_generation`` / ``observe`` — see CLAUDE.md rule #2.
- **Version tolerant.** The Langfuse SDK's method names have shifted across major
  versions, so forwarding uses ``getattr`` with fallbacks rather than one hard call.

The enabled path is exercised in tests by injecting a fake client via
``set_client``; only the real-SDK constructor is excluded from coverage.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

from app.config import get_settings

_client: Any | None = None


class _NoopSpan:
    """Returned when observability is disabled; swallows all interactions."""

    def update(self, **kwargs: Any) -> _NoopSpan:
        return self

    def score(self, **kwargs: Any) -> _NoopSpan:
        return self

    def end(self, **kwargs: Any) -> None:
        return None


def set_client(client: Any | None) -> None:
    """Inject a client (tests) or clear it (pass ``None``)."""
    global _client
    _client = client


def get_client() -> Any | None:
    """Return the active Langfuse client, or ``None`` when disabled."""
    global _client
    if _client is not None:
        return _client
    settings = get_settings()
    if not settings.langfuse_enabled:
        return None
    from langfuse import Langfuse  # pragma: no cover - needs real package + creds

    _client = Langfuse(  # pragma: no cover
        public_key=settings.langfuse_public_key,
        secret_key=settings.langfuse_secret_key,
        host=settings.langfuse_host,
    )
    return _client  # pragma: no cover


def _start_span_legacy(client: Any, name: str, attributes: dict) -> Any:
    """Forward to whichever span-creation method a v2/v3 SDK exposes."""
    for method in ("start_span", "span"):
        fn = getattr(client, method, None)
        if callable(fn):
            return fn(name=name, metadata=attributes or None)
    return _NoopSpan()


def _end_span(handle: Any) -> None:
    end = getattr(handle, "end", None)
    if callable(end):
        end()


def _safe_update(handle: Any, attributes: dict) -> None:
    update = getattr(handle, "update", None)
    if callable(update):
        try:
            update(metadata=attributes)
        except Exception:  # noqa: BLE001  # nosec B110 - never let tracing break the app
            pass


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Any]:
    """Context manager creating a Langfuse span (no-op when disabled).

    Supports Langfuse v4 (OTEL: ``start_as_current_observation`` — proper nesting)
    and falls back to v2/v3 span methods, then to a no-op.
    """
    client = get_client()
    if client is None:
        yield _NoopSpan()
        return
    start_current = getattr(client, "start_as_current_observation", None)
    if callable(start_current):  # Langfuse v4
        with start_current(as_type="span", name=name) as handle:
            if attributes:
                _safe_update(handle, attributes)
            yield handle
        return
    handle = _start_span_legacy(client, name, attributes)
    try:
        yield handle
    finally:
        _end_span(handle)


def record_generation(
    *,
    name: str,
    model: str,
    input: Any,
    output: Any,
    usage: dict | None = None,
    metadata: dict | None = None,
) -> Any:
    """Record an LLM generation (no-op when disabled)."""
    client = get_client()
    if client is None:
        return None
    start_obs = getattr(client, "start_observation", None)
    if callable(start_obs) and hasattr(client, "update_current_generation"):  # v4
        observation = start_obs(
            as_type="generation", name=name, model=model, input=input, output=output
        )
        _end_span(observation)
        return observation
    fn = getattr(client, "generation", None) or getattr(client, "create_generation", None)
    if not callable(fn):
        return None
    return fn(name=name, model=model, input=input, output=output, usage=usage, metadata=metadata)


def observe(fn: Callable | None = None, *, name: str | None = None) -> Callable:
    """Decorator that wraps a function call in a span."""

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            with span(name or func.__name__):
                return func(*args, **kwargs)

        return wrapper

    return decorator(fn) if fn is not None else decorator


def flush() -> None:
    """Flush buffered events (important before process exit)."""
    client = get_client()
    if client is None:
        return
    fn = getattr(client, "flush", None)
    if callable(fn):
        fn()
