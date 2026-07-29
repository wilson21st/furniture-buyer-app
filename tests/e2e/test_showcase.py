"""End-to-end showcase flow with Playwright against a real in-process server.

Excluded from the default suite + coverage gate (marker: e2e). Run it with:

    uv run playwright install chromium
    uv run pytest -m e2e

Drives the full demo path: log in, browse the real (local) catalogue, buy an item,
see it in orders, then use the assistant to place an order with confirm-before-spend
(a scripted fake LLM keeps it deterministic — no API key needed).
"""

from __future__ import annotations

import socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest
import uvicorn

pytestmark = pytest.mark.e2e


# --- Inline scripted LLM (kept local so e2e has no cross-module import) -----
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


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'e2e.db'}")
    monkeypatch.setenv("APP_SECRET_KEY", "e2e-secret")

    from app import agent as agent_mod
    from app import db
    from app.config import get_settings

    get_settings.cache_clear()
    db.reset_engine()

    # Deterministic agent: ask to buy the Aria chair, then a confirmation prompt.
    agent_mod.set_llm_factory(
        lambda: _FakeLLM(
            [
                _Resp(
                    [_ToolUse("t1", "place_order", {"item_id": "CHR-001", "quantity": 1})],
                    stop_reason="tool_use",
                ),
                _Resp([_Text("Confirm the Aria Accent Chair for $399.00?")]),
            ]
        )
    )

    from app.main import create_app

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


def test_full_showcase_flow(live_server, page):
    # 1. Catalogue is visible to anonymous visitors.
    page.goto(live_server)
    assert "Aria Accent Chair" in page.content()

    # 2. Log in as the demo user.
    page.goto(f"{live_server}/login")
    page.fill("input[name=user_id]", "u001")
    page.fill("input[name=password]", "demo1234")
    page.click("button[type=submit]")
    page.wait_for_url(live_server + "/")
    assert "Asha Verma" in page.content()

    # 3. Buy the first product; it appears in orders and reduces the balance.
    page.click("form[action^='/buy/'] button")
    page.wait_for_url(live_server + "/orders")
    assert "CHR-001" in page.content()

    # 4. Use the assistant: request → confirm-before-spend → order placed.
    page.goto(f"{live_server}/chat")
    page.fill("input[name=message]", "buy the aria chair")
    page.click("form[action='/chat'] button")
    page.wait_for_selector("text=Confirm purchase")
    page.click("form[action='/chat/confirm'] button")
    assert "Done — ordered" in page.content()
