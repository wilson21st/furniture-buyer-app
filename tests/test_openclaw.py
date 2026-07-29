import json

import pytest
from sqlmodel import Session

from app import openclaw, services
from app.tools import ToolContext


@pytest.fixture
def ctx(initialized_db):
    with Session(initialized_db) as session:
        services.seed_placeholder_products(session)
        user = services.create_user(session, "u001", "Asha", "pw", balance=1000.0)
        yield ToolContext(api=None, session=session, user=user)


def test_manifest_exposes_four_tools_and_confirm_gate():
    manifest = openclaw.manifest()
    names = {t["name"] for t in manifest["tools"]}
    assert names == {"search_catalogue", "get_product", "check_balance", "place_order"}
    assert manifest["confirm_before"] == ["place_order"]
    assert manifest["permissions"] == ["network:furniture-api"]


def test_handle_search(ctx):
    out = openclaw.handle("search_catalogue", {"category": "Chairs"}, ctx=ctx)
    data = json.loads(out["content"])
    assert data["count"] == 2
    assert "pending_order" not in out


def test_handle_place_order_returns_pending_without_spending(ctx):
    out = openclaw.handle("place_order", {"item_id": "CHR-001", "quantity": 1}, ctx=ctx)
    assert out["pending_order"]["item_id"] == "CHR-001"
    assert out["pending_order"]["total"] == 399.0
    assert services.order_history(ctx.session, "u001") == []  # not spent yet


def test_confirm_order_spends_then_errors(ctx):
    ok = openclaw.confirm_order("CHR-001", 1, ctx=ctx)
    assert ok["status"] == "success"
    assert ok["remaining_balance"] == 601.0

    ctx.user.local_balance = 1.0
    fail = openclaw.confirm_order("SOF-001", 1, ctx=ctx)
    assert fail["status"] == "error"
    assert "Insufficient balance" in fail["message"]


def test_build_context_local_mode(initialized_db):
    ctx = openclaw.build_context()
    try:
        assert ctx.api is None  # USE_REAL_API is false in tests
        assert ctx.user.user_id == "u001"
    finally:
        ctx.session.close()


def test_build_context_api_mode(monkeypatch, initialized_db):
    monkeypatch.setenv("USE_REAL_API", "true")
    from app.config import get_settings

    get_settings.cache_clear()
    ctx = openclaw.build_context()
    try:
        assert ctx.api is not None  # constructed, no network call made
    finally:
        ctx.api.close()
        ctx.session.close()


def test_handle_builds_own_context_when_none(initialized_db):
    # Exercises the own-context branch (build + close) without passing ctx.
    with Session(initialized_db) as s:
        services.seed_placeholder_products(s)
        services.create_user(s, "u001", "Asha", "pw", balance=100.0)
    out = openclaw.handle("check_balance")
    assert "content" in out


def test_confirm_order_builds_own_context_when_none(initialized_db):
    # confirm_order with no ctx builds+closes its own session (own-context branch).
    with Session(initialized_db) as s:
        services.seed_placeholder_products(s)
    # build_context's ad-hoc user has a 0 balance, so this fails gracefully —
    # which is exactly the path that runs the `finally: ctx.session.close()`.
    result = openclaw.confirm_order("CHR-001", 1)
    assert result["status"] == "error"
