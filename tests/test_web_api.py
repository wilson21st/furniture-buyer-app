"""Web tests with USE_REAL_API enabled — routes must serve real API data."""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import get_settings

BASE = "https://api.test"


@pytest.fixture
def api_client(client, monkeypatch):
    monkeypatch.setenv("USE_REAL_API", "true")
    get_settings.cache_clear()
    return client


def _login(client):
    client.post("/login", data={"user_id": "u001", "password": "demo1234"}, follow_redirects=False)


@respx.mock
def test_home_and_nav_use_real_api(api_client):
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
        return_value=httpx.Response(
            200, json={"user_id": "u001", "name": "Asha", "balance": 4200.0}
        )
    )
    _login(api_client)
    resp = api_client.get("/")
    assert "Cloud Sofa" in resp.text
    assert "$4200.00" in resp.text  # real balance rendered in the nav


@respx.mock
def test_buy_through_real_api_updates_balance_message(api_client):
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200, json={"order_id": "o1", "total_price": 800.0, "remaining_balance": 3400.0}
        )
    )
    respx.get(f"{BASE}/orders/u001").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "order_id": "o1",
                    "item_id": "API-1",
                    "quantity": 1,
                    "total_price": 800.0,
                    "status": "success",
                }
            ],
        )
    )
    respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(200, json={"user_id": "u001", "balance": 3400.0})
    )
    _login(api_client)
    resp = api_client.post("/buy/API-1", data={"quantity": 1}, follow_redirects=False)
    assert resp.headers["location"] == "/orders"
    orders = api_client.get("/orders")
    assert "API-1" in orders.text
    assert "$3400.00" in orders.text


@respx.mock
def test_buy_insufficient_balance_via_api_shows_message(api_client):
    respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(402, json={"detail": "insufficient"})
    )
    respx.get(f"{BASE}/catalogue/search-index").mock(return_value=httpx.Response(200, json=[]))
    respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(200, json={"user_id": "u001", "balance": 5.0})
    )
    _login(api_client)
    resp = api_client.post("/buy/API-1", data={"quantity": 1}, follow_redirects=False)
    assert resp.headers["location"] == "/"
    assert "Insufficient balance" in api_client.get("/").text
