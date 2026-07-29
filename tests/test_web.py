"""Integration tests for the Level 1 web app via FastAPI TestClient."""

from __future__ import annotations


def login(client, user_id="u001", password="demo1234"):
    return client.post(
        "/login", data={"user_id": user_id, "password": password}, follow_redirects=False
    )


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_home_anonymous_shows_catalogue_and_login(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Aria Accent Chair" in resp.text
    assert "Log in" in resp.text


def test_login_page_renders(client):
    assert "Log in" in client.get("/login").text


def test_login_wrong_password_redirects_back(client):
    resp = login(client, password="nope")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"
    # flash surfaced on the login page
    assert "Wrong user id or password." in client.get("/login").text


def test_login_success_then_home_shows_user(client):
    resp = login(client)
    assert resp.status_code == 303 and resp.headers["location"] == "/"
    home = client.get("/")
    assert "Asha Verma" in home.text
    assert "Buy" in home.text  # buy buttons only show when logged in


def test_buy_requires_login(client):
    resp = client.post("/buy/CHR-001", data={"quantity": 1}, follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_buy_success_reduces_balance_and_lists_order(client):
    login(client)
    resp = client.post("/buy/CHR-001", data={"quantity": 1}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == "/orders"
    orders = client.get("/orders")
    assert "CHR-001" in orders.text
    assert "$2101.00" in orders.text  # 2500 - 399


def test_buy_insufficient_balance_shows_message(client):
    login(client)
    # 1199 * 3 = 3597 > 2500
    resp = client.post("/buy/SOF-001", data={"quantity": 3}, follow_redirects=False)
    assert resp.headers["location"] == "/"
    assert "Insufficient balance" in client.get("/").text


def test_buy_unknown_product_shows_message(client):
    login(client)
    resp = client.post("/buy/GHOST", data={"quantity": 1}, follow_redirects=False)
    assert resp.headers["location"] == "/"
    assert "no longer available" in client.get("/").text


def test_orders_requires_login(client):
    resp = client.get("/orders", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_logout_clears_session(client):
    login(client)
    assert "Asha Verma" in client.get("/").text
    client.post("/logout", follow_redirects=False)
    assert "Log in" in client.get("/").text


def test_lifespan_initialises_and_seeds(initialized_db):
    """Entering the app context runs the lifespan: init_db + bootstrap_demo."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as ctx_client:
        assert ctx_client.get("/health").json() == {"status": "ok"}
        assert "Aria Accent Chair" in ctx_client.get("/").text  # seeded on startup
