import json

import pytest
from sqlmodel import Session

from app import furniture_api as fa
from app import services, shop
from app import tools as tools_mod
from app.tools import ToolContext


@pytest.fixture
def ctx(initialized_db):
    with Session(initialized_db) as session:
        services.seed_placeholder_products(session)
        user = services.create_user(session, "u001", "Asha", "pw", balance=1000.0)
        yield ToolContext(api=None, session=session, user=user)


def _run(name, tool_input, ctx):
    content, pending = tools_mod.execute(name, tool_input, ctx)
    return json.loads(content) if content.startswith("{") else content, pending


def test_search_no_filters(ctx):
    data, pending = _run("search_catalogue", {}, ctx)
    assert data["count"] == 5
    assert pending is None


def test_search_category_and_price_and_colour(ctx):
    data, _ = _run("search_catalogue", {"category": "Chairs", "max_price": 200}, ctx)
    assert [r["item_id"] for r in data["results"]] == ["CHR-002"]  # 149, not 399

    data, _ = _run("search_catalogue", {"colour": "MUSTARD"}, ctx)
    assert data["results"][0]["item_id"] == "CHR-001"


def test_get_product_found_and_missing(ctx):
    data, _ = _run("get_product", {"item_id": "CHR-001"}, ctx)
    assert data["price"] == 399.0
    missing, _ = _run("get_product", {"item_id": "NOPE"}, ctx)
    assert "error" in missing


def test_check_balance(ctx):
    data, _ = _run("check_balance", {}, ctx)
    assert data["balance"] == 1000.0


def test_place_order_returns_pending_not_spent(ctx):
    data, pending = _run("place_order", {"item_id": "CHR-001", "quantity": 2}, ctx)
    assert data["status"] == "confirmation_required"
    assert pending.item_id == "CHR-001"
    assert pending.quantity == 2
    assert pending.total == 798.0
    # Nothing was actually ordered.
    assert services.order_history(ctx.session, "u001") == []


def test_place_order_unknown_item(ctx):
    data, pending = _run("place_order", {"item_id": "GHOST"}, ctx)
    assert "error" in data
    assert pending is None


def test_unknown_tool(ctx):
    data, _ = _run("teleport", {}, ctx)
    assert "Unknown tool" in data["error"]


def test_shoperror_is_caught(ctx, monkeypatch):
    def boom(*a, **k):
        raise shop.ShopError("kaboom")

    monkeypatch.setattr(shop, "list_catalogue", boom)
    data, _ = _run("search_catalogue", {}, ctx)
    assert data["error"] == "kaboom"


def test_apierror_is_caught(ctx, monkeypatch):
    def boom(*a, **k):
        raise fa.ApiError(500, "server sad")

    monkeypatch.setattr(shop, "get_balance", boom)
    data, _ = _run("check_balance", {}, ctx)
    assert "server sad" in data["error"]
