from types import SimpleNamespace

import pytest
from fake_llm import FakeLLM, text, tool
from sqlmodel import Session

from app import agent as agent_mod
from app import services, shop
from app.agent import Agent, execute_confirmed_order
from app.tools import PendingOrder, ToolContext


@pytest.fixture
def ctx(initialized_db):
    with Session(initialized_db) as session:
        services.seed_placeholder_products(session)
        user = services.create_user(session, "u001", "Asha", "pw", balance=1000.0)
        yield ToolContext(api=None, session=session, user=user)


def test_text_only_reply_records_usage(ctx):
    usage = SimpleNamespace(input_tokens=3, output_tokens=5)
    agent = Agent(ctx, llm=FakeLLM([text("Hello there!", usage=usage)]))
    reply, history = agent.respond("hi", [])
    assert reply.text == "Hello there!"
    assert reply.pending_order is None
    assert reply.steps == []
    assert history[0] == {"role": "user", "content": "hi"}


def test_tool_then_text(ctx):
    llm = FakeLLM(
        [
            tool("t1", "search_catalogue", {"category": "Chairs", "max_price": 200}),
            text("I found the Nord Dining Chair for $149."),
        ]
    )
    reply, history = Agent(ctx, llm=llm).respond("cheap chair", [])
    assert "Nord" in reply.text
    assert reply.steps == ["search_catalogue"]
    # user, assistant(tool_use), user(tool_result), assistant(text)
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]
    assert history[2]["content"][0]["type"] == "tool_result"


def test_place_order_surfaces_pending(ctx):
    llm = FakeLLM(
        [
            tool("t1", "place_order", {"item_id": "CHR-001", "quantity": 1}),
            text("Shall I confirm the Aria Accent Chair for $399?"),
        ]
    )
    reply, _ = Agent(ctx, llm=llm).respond("buy the aria chair", [])
    assert reply.pending_order is not None
    assert reply.pending_order.item_id == "CHR-001"
    # confirm-before-spend: still nothing ordered
    assert services.order_history(ctx.session, "u001") == []


def test_tool_use_response_with_extra_text_block_is_skipped(ctx):
    from fake_llm import FakeResponse, TextBlock, ToolUseBlock

    mixed = FakeResponse(
        [TextBlock("let me check"), ToolUseBlock("t1", "check_balance", {})],
        stop_reason="tool_use",
    )
    llm = FakeLLM([mixed, text("You have $1000.")])
    reply, _ = Agent(ctx, llm=llm).respond("balance?", [])
    assert "1000" in reply.text
    assert reply.steps == ["check_balance"]  # only the tool_use block ran


def test_max_steps_exhausted_returns_fallback(ctx):
    # Always ask for a tool → loop never terminates on its own.
    llm = FakeLLM([tool(f"t{i}", "check_balance", {}) for i in range(agent_mod.MAX_STEPS)])
    reply, _ = Agent(ctx, llm=llm).respond("loop forever", [])
    assert "couldn't finish" in reply.text
    assert len(reply.steps) == agent_mod.MAX_STEPS


def test_set_llm_factory_used_when_no_llm_passed(ctx):
    sentinel = FakeLLM([text("from factory")])
    agent_mod.set_llm_factory(lambda: sentinel)
    agent = Agent(ctx)  # no llm arg
    assert agent._llm is sentinel


def test_execute_confirmed_order_spends_and_errors(ctx):
    pending = PendingOrder("CHR-001", "Aria", 399.0, 1)
    outcome = execute_confirmed_order(ctx, pending)
    assert outcome.total_price == 399.0
    assert ctx.user.local_balance == 601.0

    ctx.user.local_balance = 10.0
    with pytest.raises(shop.ShopError):
        execute_confirmed_order(ctx, PendingOrder("SOF-001", "Loom", 1199.0, 1))
