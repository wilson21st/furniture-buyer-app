"""Unit tests for the unified shop layer — both the local and real-API paths."""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlmodel import Session

from app import furniture_api as fa
from app import services, shop

BASE = "https://api.test"


@pytest.fixture
def session(initialized_db):
    with Session(initialized_db) as s:
        services.seed_placeholder_products(s)
        yield s


@pytest.fixture
def user(session):
    return services.create_user(session, "u001", "Asha", "pw", balance=1000.0)


@pytest.fixture
def api():
    client = fa.FurnitureAPI(BASE, "test-key", "u001", client=httpx.Client())
    yield client
    client.close()


# --- Local path (api=None) -------------------------------------------------
def test_local_catalogue_balance_and_order(session, user):
    products = shop.list_catalogue(None, session)
    assert any(p.item_id == "CHR-001" for p in products)
    assert shop.get_balance(None, user) == 1000.0

    outcome = shop.place_order(None, session, user, "CHR-001")  # 399
    assert outcome.total_price == 399.0
    assert outcome.remaining_balance == 601.0
    assert shop.order_history(None, session, user)[0].item_id == "CHR-001"


def test_local_insufficient_becomes_shoperror(session, user):
    user.local_balance = 10.0
    with pytest.raises(shop.ShopError, match="Insufficient balance"):
        shop.place_order(None, session, user, "CHR-001")


def test_local_unknown_product_becomes_shoperror(session, user):
    with pytest.raises(shop.ShopError, match="no longer available"):
        shop.place_order(None, session, user, "GHOST")


# --- Real-API path ---------------------------------------------------------
@respx.mock
def test_api_catalogue_and_balance(api, session, user):
    respx.get(f"{BASE}/catalogue/search-index").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "item_id": "API-1",
                    "product_name": "Cloud Sofa",
                    "price": 800.0,
                    "category": "Sofas",
                    "colours": ["grey"],
                }
            ],
        )
    )
    respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(200, json={"user_id": "u001", "balance": 4200.0})
    )
    catalogue = shop.list_catalogue(api, session)
    assert catalogue[0].product_name == "Cloud Sofa"
    assert shop.get_balance(api, user) == 4200.0


@respx.mock
def test_api_place_order_success(api, session, user):
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200, json={"order_id": "o1", "total_price": 800.0, "remaining_balance": 3400.0}
        )
    )
    outcome = shop.place_order(api, session, user, "API-1")
    assert outcome.remaining_balance == 3400.0


@respx.mock
@pytest.mark.parametrize(
    "status,headers,fragment",
    [
        (402, {}, "Insufficient balance"),
        (404, {}, "no longer available"),
        (429, {"Retry-After": "5"}, "try again in 5 seconds"),
        (401, {}, "authorise"),
        (500, {}, "something went wrong"),
    ],
)
def test_api_errors_map_to_friendly_shoperror(api, session, user, status, headers, fragment):
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(status, headers=headers, json={"detail": "x"})
    )
    with pytest.raises(shop.ShopError, match=fragment):
        shop.place_order(api, session, user, "API-1")


@respx.mock
def test_api_get_product_view_found_and_missing(api, session, user):
    respx.get(f"{BASE}/catalogue/API-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "item_id": "API-1",
                "product_name": "Cloud Sofa",
                "price": 800.0,
                "category": "Sofas",
                "colours": ["grey"],
            },
        )
    )
    view = shop.get_product_view(api, session, "API-1")
    assert view.product_name == "Cloud Sofa"

    respx.get(f"{BASE}/catalogue/GONE").mock(
        return_value=httpx.Response(404, json={"detail": "no"})
    )
    assert shop.get_product_view(api, session, "GONE") is None


def test_local_get_product_view_found_and_missing(session, user):
    assert shop.get_product_view(None, session, "CHR-001").price == 399.0
    assert shop.get_product_view(None, session, "NOPE") is None


@respx.mock
def test_api_order_history(api, session, user):
    respx.get(f"{BASE}/orders/u001").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "order_id": "o1",
                    "item_id": "API-1",
                    "quantity": 2,
                    "total_price": 1600.0,
                    "status": "success",
                }
            ],
        )
    )
    history = shop.order_history(api, session, user)
    assert history[0].quantity == 2
    assert history[0].created_at is None  # API history has no local timestamp
