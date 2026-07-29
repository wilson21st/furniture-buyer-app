"""End-to-end run that captures ALL test detail as structured observability traces.

This is the "observability, not just logs" harness. It injects a recording client
into app/observability.py and drives every instrumented path — the Level 2 API
client, the Level 3 agent (with confirm-before-spend), and the Level 4 RAG Q&A —
then emits a nested trace tree (spans + tool calls + API calls + LLM generations,
each with timings and attributes) as both a printed tree and a JSON artifact.

    uv run python -m scripts.observability_e2e

Writes docs/observability-report.json. Uses respx + scripted fakes, so it is fully
deterministic and needs no external credentials.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/obs_e2e.db")
os.environ.setdefault("APP_SECRET_KEY", "obs-e2e")

import httpx  # noqa: E402
import respx  # noqa: E402

from app import agent as agent_mod  # noqa: E402
from app import db, observability, rag, services  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.furniture_api import FurnitureAPI  # noqa: E402
from app.tools import ToolContext  # noqa: E402

BASE = "https://api.test"


# --- Recording observability client ----------------------------------------
class RecSpan:
    def __init__(self, name: str, metadata: dict | None, recorder: Recorder):
        self.name = name
        self.metadata: dict = dict(metadata or {})
        self.children: list[RecSpan] = []
        self.generations: list[dict] = []
        self._rec = recorder
        self._start = time.perf_counter()
        self.duration_ms: float | None = None

    def update(self, **kwargs: Any) -> RecSpan:
        meta = kwargs.pop("metadata", None)
        if meta:
            self.metadata.update(meta)
        self.metadata.update(kwargs)
        return self

    def score(self, **kwargs: Any) -> RecSpan:
        return self

    def end(self, **kwargs: Any) -> None:
        self.duration_ms = round((time.perf_counter() - self._start) * 1000, 2)
        self._rec.pop(self)


class Recorder:
    def __init__(self) -> None:
        self.roots: list[RecSpan] = []
        self._stack: list[RecSpan] = []
        self.generation_count = 0

    def start_span(self, name: str, metadata: dict | None = None) -> RecSpan:
        span = RecSpan(name, metadata, self)
        (self._stack[-1].children if self._stack else self.roots).append(span)
        self._stack.append(span)
        return span

    def pop(self, span: RecSpan) -> None:
        if self._stack and self._stack[-1] is span:
            self._stack.pop()

    def generation(self, **kwargs: Any) -> dict:
        self.generation_count += 1
        record = {
            "name": kwargs.get("name"),
            "model": kwargs.get("model"),
            "output": str(kwargs.get("output"))[:120],
        }
        target = self._stack[-1].generations if self._stack else None
        if target is not None:
            target.append(record)
        return record

    def flush(self) -> None:
        pass


# --- Scripted LLMs ----------------------------------------------------------
@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _ToolUse:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class _Resp:
    content: list
    stop_reason: str = "end_turn"
    usage: Any = None


@dataclass
class _FakeLLM:
    responses: list = field(default_factory=list)

    def create(self, **kwargs: Any) -> _Resp:
        return self.responses.pop(0)


class _BagEmbedder:
    VOCAB = ["chair", "table", "sofa", "lamp", "blue", "mustard", "cheap"]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(t.lower().count(w)) for w in self.VOCAB] for t in texts]


# --- The scenario -----------------------------------------------------------
def _catalogue_mocks(router) -> None:
    router.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
    router.get(f"{BASE}/catalogue/categories").mock(
        return_value=httpx.Response(200, json=["Chairs", "Tables"])
    )
    router.get(f"{BASE}/catalogue/search-index").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"item_id": "CHR-001", "product_name": "Aria Accent Chair", "price": 399.0,
                 "category": "Chairs", "colours": ["mustard"]},
                {"item_id": "CHR-002", "product_name": "Nord Dining Chair", "price": 149.0,
                 "category": "Chairs", "colours": ["oak"]},
            ],
        )
    )
    router.get(f"{BASE}/catalogue/CHR-001").mock(
        return_value=httpx.Response(
            200, json={"item_id": "CHR-001", "product_name": "Aria Accent Chair",
                       "price": 399.0, "category": "Chairs", "colours": ["mustard"]}
        )
    )
    router.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(200, json={"user_id": "u001", "name": "Asha",
                                               "balance": 2500.0})
    )
    router.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(200, json={"order_id": "o1", "status": "success",
                                               "total_price": 399.0,
                                               "remaining_balance": 2101.0})
    )


def run() -> Recorder:
    get_settings.cache_clear()
    db.reset_engine()
    db.init_db()
    recorder = Recorder()
    real = get_settings().langfuse_enabled
    if not real:
        # In-process capture (default). When LANGFUSE_ENABLED=true we instead let the
        # app build the real Langfuse client so spans stream to the running backend.
        observability.set_client(recorder)

    with respx.mock(assert_all_called=False) as router:
        _catalogue_mocks(router)
        api = FurnitureAPI(BASE, "test-key", "u001", client=httpx.Client())
        with db_session() as session:
            user = _ensure_user(session)
            ctx = ToolContext(api=api, session=session, user=user)

            # --- Level 2: direct API client calls ---
            with observability.span("scenario.level2_api_client"):
                api.health()
                api.list_categories()
                api.search_products(category="Chairs", limit=10)
                api.get_balance()

            # --- Level 3: agent decides to search then order (confirm-before-spend) ---
            llm = _FakeLLM(
                [
                    _Resp([_ToolUse("t1", "search_catalogue",
                                    {"category": "Chairs", "max_price": 500})],
                          stop_reason="tool_use"),
                    _Resp([_ToolUse("t2", "place_order", {"item_id": "CHR-001", "quantity": 1})],
                          stop_reason="tool_use"),
                    _Resp([_Text("Confirm buying the Aria Accent Chair for $399.00?")]),
                ]
            )
            reply, _ = agent_mod.Agent(ctx, llm=llm).respond("find a cheap chair and buy it", [])
            assert reply.pending_order is not None, "agent should surface a pending order"

            # user confirms -> real debit happens here
            outcome = agent_mod.execute_confirmed_order(ctx, reply.pending_order)
            assert outcome.remaining_balance == 2101.0

            # --- Level 4: RAG Q&A ---
            rag.set_embedder_factory(_BagEmbedder)
            index = rag.VectorIndex().build(
                rag.chunk_products(
                    [
                        {"item_id": "CHR-001", "product_name": "Mustard Chair",
                         "price": 399.0, "category": "Chairs", "colours": ["mustard"]},
                        {"item_id": "SOF-001", "product_name": "Blue Sofa", "price": 900.0,
                         "category": "Sofas", "colours": ["blue"]},
                    ]
                )
            )
            rag.answer_question(
                index, "something cheap like a chair", k=1,
                llm=_FakeLLM([_Resp([_Text("The Mustard Chair (CHR-001).")])]),
            )
        api.close()

    if real:
        observability.flush()
    else:
        observability.set_client(None)
    return recorder


# --- Small helpers ----------------------------------------------------------
from contextlib import contextmanager  # noqa: E402

from sqlmodel import Session  # noqa: E402


@contextmanager
def db_session():
    with Session(db.get_engine()) as session:
        yield session


def _ensure_user(session: Session):
    existing = session.get(services.Customer, "u001")
    if existing:
        return existing
    return services.create_user(session, "u001", "Asha", "demo1234", balance=2500.0)


# --- Reporting --------------------------------------------------------------
def to_dict(span: RecSpan) -> dict:
    return {
        "name": span.name,
        "duration_ms": span.duration_ms,
        "attributes": span.metadata,
        "generations": span.generations,
        "children": [to_dict(c) for c in span.children],
    }


def print_tree(span: RecSpan, depth: int = 0) -> tuple[int, int, int]:
    spans = api_calls = gens = 0
    indent = "  " * depth
    dur = f"{span.duration_ms:.1f}ms" if span.duration_ms is not None else "-"
    attrs = ""
    if span.metadata:
        attrs = "  " + json.dumps(span.metadata, separators=(",", ":"))
    print(f"{indent}▸ {span.name}  [{dur}]{attrs}")
    spans += 1
    if span.name.startswith("furniture_api"):
        api_calls += 1
    for gen in span.generations:
        gens += 1
        print(f"{indent}    ◆ generation: {gen['name']} ({gen['model']})")
    for child in span.children:
        s, a, g = print_tree(child, depth + 1)
        spans += s
        api_calls += a
        gens += g
    return spans, api_calls, gens


def main() -> None:
    recorder = run()
    if get_settings().langfuse_enabled:
        print("Ran scenario with LANGFUSE_ENABLED=true — spans/generations flushed to "
              f"{get_settings().langfuse_host}. Query the API to inspect them.")
        return
    print("\n=== OBSERVABILITY TRACE TREE (in-process recorder) ===\n")
    total_spans = total_api = total_gens = 0
    for root in recorder.roots:
        s, a, g = print_tree(root)
        total_spans += s
        total_api += a
        total_gens += g

    summary = {
        "root_traces": len(recorder.roots),
        "total_spans": total_spans,
        "furniture_api_calls": total_api,
        "llm_generations": recorder.generation_count,
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))

    report = {"summary": summary, "traces": [to_dict(r) for r in recorder.roots]}
    out = Path("docs/observability-report.json")
    out.write_text(json.dumps(report, indent=2))
    print(f"\nWrote {out}")


if __name__ == "__main__":
    main()
