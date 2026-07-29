"""Unit/integration tests for the external API client, with respx mocking HTTP.

No real network is touched. Covers happy paths, header/auth behaviour, and every
documented error code (401/402/403/404/429 + a generic 500).
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app import furniture_api as fa

BASE = "https://api.test"


@pytest.fixture
def api():
    client = fa.FurnitureAPI(BASE, "test-key", "u001", client=httpx.Client())
    yield client
    client.close()


@respx.mock
def test_health_true_and_false(api):
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(200, json={"ok": True}))
    assert api.health() is True
    respx.get(f"{BASE}/health").mock(return_value=httpx.Response(503, text="down"))
    assert api.health() is False


@respx.mock
def test_list_categories(api):
    respx.get(f"{BASE}/catalogue/categories").mock(
        return_value=httpx.Response(200, json=["Chairs", "Tables"])
    )
    assert api.list_categories() == ["Chairs", "Tables"]


@respx.mock
def test_search_products_passes_params_and_no_auth(api):
    route = respx.get(f"{BASE}/catalogue/search-index").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"item_id": "CHR-001", "product_name": "Aria", "price": 399.0,
                 "category": "Chairs", "colours": ["mustard"], "colour_count": 1}
            ],
        )
    )
    products = api.search_products(category="Chairs", limit=10)
    assert products[0].item_id == "CHR-001"
    assert products[0].colours == ["mustard"]
    request = route.calls.last.request
    assert request.url.params["category"] == "Chairs"
    assert request.url.params["limit"] == "10"
    assert "X-Api-Key" not in request.headers  # browsing is public


@respx.mock
def test_search_products_without_category(api):
    route = respx.get(f"{BASE}/catalogue/search-index").mock(
        return_value=httpx.Response(200, json=[])
    )
    assert api.search_products() == []
    assert "category" not in route.calls.last.request.url.params


@respx.mock
def test_get_product_ignores_extra_image_field(api):
    respx.get(f"{BASE}/catalogue/CHR-001").mock(
        return_value=httpx.Response(
            200,
            json={"item_id": "CHR-001", "product_name": "Aria", "price": 399.0,
                  "image": "data:image/jpeg;base64,AAAABBBB"},  # must be ignored
        )
    )
    product = api.get_product("CHR-001")
    assert product.product_name == "Aria"
    assert not hasattr(product, "image")


@respx.mock
def test_get_balance_sends_api_key(api):
    route = respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(200, json={"user_id": "u001", "name": "Asha",
                                               "balance": 2500.0})
    )
    balance = api.get_balance()
    assert balance.balance == 2500.0
    assert route.calls.last.request.headers["X-Api-Key"] == "test-key"


@respx.mock
def test_place_order_posts_body_and_returns_result(api):
    route = respx.post(f"{BASE}/orders").mock(
        return_value=httpx.Response(
            200,
            json={"order_id": "o123", "status": "success", "total_price": 399.0,
                  "remaining_balance": 2101.0},
        )
    )
    result = api.place_order("CHR-001", quantity=1)
    assert result.order_id == "o123"
    assert result.remaining_balance == 2101.0
    import json

    sent = json.loads(route.calls.last.request.content)
    assert sent == {"user_id": "u001", "item_id": "CHR-001", "quantity": 1}


@respx.mock
def test_order_history(api):
    respx.get(f"{BASE}/orders/u001").mock(
        return_value=httpx.Response(
            200, json=[{"order_id": "o1", "item_id": "CHR-001", "total_price": 399.0}]
        )
    )
    history = api.order_history()
    assert history[0].order_id == "o1"


@respx.mock
@pytest.mark.parametrize(
    "status,exc",
    [
        (401, fa.AuthError),
        (402, fa.InsufficientBalanceError),
        (403, fa.ForbiddenError),
        (404, fa.NotFoundError),
        (500, fa.ApiError),
    ],
)
def test_error_status_mapping(api, status, exc):
    respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(status, json={"detail": f"boom {status}"})
    )
    with pytest.raises(exc) as info:
        api.get_balance()
    assert info.value.status_code == status
    assert str(status) in info.value.detail


@respx.mock
def test_rate_limit_carries_retry_after(api):
    respx.get(f"{BASE}/catalogue/categories").mock(
        return_value=httpx.Response(429, headers={"Retry-After": "7"}, text="slow down")
    )
    with pytest.raises(fa.RateLimitError) as info:
        api.list_categories()
    assert info.value.retry_after == 7


@respx.mock
def test_error_detail_falls_back_to_text_when_not_json(api):
    respx.get(f"{BASE}/users/u001").mock(
        return_value=httpx.Response(404, text="plain not found")
    )
    with pytest.raises(fa.NotFoundError) as info:
        api.get_balance()
    assert info.value.detail == "plain not found"


def test_from_settings_builds_client(monkeypatch):
    monkeypatch.setenv("FURNITURE_API_BASE_URL", "https://x.test/")
    monkeypatch.setenv("FURNITURE_API_KEY", "k")
    monkeypatch.setenv("FURNITURE_USER_ID", "u042")
    from app.config import get_settings

    get_settings.cache_clear()
    client = fa.FurnitureAPI.from_settings()
    assert client.base_url == "https://x.test"  # trailing slash trimmed
    assert client.user_id == "u042"
    client.close()
