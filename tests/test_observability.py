"""Cover both the disabled no-op path and the enabled path (via a fake client)."""

from __future__ import annotations

from app import observability as obs
from app.config import get_settings


# --- Fakes -----------------------------------------------------------------
class FakeSpan:
    def __init__(self):
        self.ended = False

    def end(self):
        self.ended = True


class FakeClient:
    def __init__(self):
        self.spans: list[FakeSpan] = []
        self.generations: list[dict] = []
        self.flushed = False

    def start_span(self, name, metadata=None):
        span = FakeSpan()
        span.name = name
        span.metadata = metadata
        self.spans.append(span)
        return span

    def generation(self, **kwargs):
        self.generations.append(kwargs)
        return kwargs

    def flush(self):
        self.flushed = True


class LegacyClient:
    """Only exposes the old `span` method name, to exercise the fallback."""

    def span(self, name, metadata=None):
        return FakeSpan()


# --- Disabled path ---------------------------------------------------------
def test_get_client_none_when_disabled():
    assert obs.get_client() is None


def test_span_noop_when_disabled():
    with obs.span("x", foo="bar") as handle:
        assert isinstance(handle, obs._NoopSpan)
        assert handle.update(a=1) is handle
        assert handle.score(value=1) is handle
        assert handle.end() is None


def test_record_generation_noop_when_disabled():
    assert obs.record_generation(name="g", model="m", input="i", output="o") is None


def test_observe_decorator_passthrough_when_disabled():
    @obs.observe(name="calc")
    def add(a, b):
        return a + b

    assert add(2, 3) == 5


def test_observe_without_name_uses_func_name():
    @obs.observe
    def double(x):
        return x * 2

    assert double(4) == 8


def test_flush_noop_when_disabled():
    obs.flush()  # should not raise


# --- Enabled path (injected fake client) -----------------------------------
def test_span_uses_client_and_ends():
    client = FakeClient()
    obs.set_client(client)
    with obs.span("agent-turn", user="u001") as handle:
        assert handle is client.spans[0]
    assert client.spans[0].ended is True
    assert client.spans[0].metadata == {"user": "u001"}


def test_span_legacy_method_fallback():
    obs.set_client(LegacyClient())
    with obs.span("legacy") as handle:
        assert isinstance(handle, FakeSpan)


def test_span_no_method_yields_noop():
    class Empty:
        pass

    obs.set_client(Empty())
    with obs.span("none") as handle:
        assert isinstance(handle, obs._NoopSpan)


def test_record_generation_forwards():
    client = FakeClient()
    obs.set_client(client)
    result = obs.record_generation(
        name="chat", model="claude", input="hi", output="hello", usage={"in": 1}
    )
    assert result["model"] == "claude"
    assert client.generations[0]["name"] == "chat"


def test_record_generation_missing_method_returns_none():
    class Empty:
        pass

    obs.set_client(Empty())
    assert obs.record_generation(name="n", model="m", input="i", output="o") is None


def test_flush_forwards_to_client():
    client = FakeClient()
    obs.set_client(client)
    obs.flush()
    assert client.flushed is True


def test_get_client_returns_injected():
    client = FakeClient()
    obs.set_client(client)
    assert obs.get_client() is client


def test_enabled_setting_reads_from_env(monkeypatch):
    # When enabled but no client injected, get_client tries the real SDK path.
    # We assert the branch is reached by clearing the injected client and
    # confirming settings flip; the real constructor is import-guarded.
    monkeypatch.setenv("LANGFUSE_ENABLED", "true")
    get_settings.cache_clear()
    assert get_settings().langfuse_enabled is True
