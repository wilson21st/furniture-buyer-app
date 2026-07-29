"""Web tests for the Step 6 agent chat, driving a scripted fake LLM."""

from __future__ import annotations

from fake_llm import FakeLLM, text, tool

from app import agent as agent_mod
from app import services


def _login(client):
    client.post("/login", data={"user_id": "u001", "password": "demo1234"}, follow_redirects=False)


def test_chat_requires_login(client):
    resp = client.get("/chat", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"


def test_chat_send_and_render_reply(client):
    _login(client)
    agent_mod.set_llm_factory(lambda: FakeLLM([text("Your balance is $2500.")]))
    resp = client.post("/chat", data={"message": "balance?"}, follow_redirects=False)
    assert resp.status_code == 303
    page = client.get("/chat")
    assert "balance?" in page.text
    assert "Your balance is $2500." in page.text


def test_chat_confirm_places_order_and_updates_balance(client):
    _login(client)
    # Turn 1: model asks to place an order → pending appears.
    agent_mod.set_llm_factory(
        lambda: FakeLLM(
            [
                tool("t1", "place_order", {"item_id": "CHR-001", "quantity": 1}),
                text("Confirm the Aria Accent Chair for $399?"),
            ]
        )
    )
    client.post("/chat", data={"message": "buy the aria chair"}, follow_redirects=False)
    page = client.get("/chat")
    assert "Confirm purchase" in page.text
    assert "Aria Accent Chair" in page.text

    # Confirm → real (local) order placed, balance reduced from 2500 to 2101.
    client.post("/chat/confirm", follow_redirects=False)
    page = client.get("/chat")
    assert "Done — ordered" in page.text
    assert "$2101.00" in page.text


def test_chat_confirm_insufficient_balance_shows_message(client, initialized_db):
    from sqlmodel import Session

    # Drop the demo user's balance so the confirmed order fails.
    with Session(initialized_db) as session:
        user = session.get(services.Customer, "u001")
        user.local_balance = 5.0
        session.add(user)
        session.commit()

    _login(client)
    agent_mod.set_llm_factory(
        lambda: FakeLLM(
            [
                tool("t1", "place_order", {"item_id": "SOF-001", "quantity": 1}),
                text("Confirm the Loom sofa for $1199?"),
            ]
        )
    )
    client.post("/chat", data={"message": "buy the loom sofa"}, follow_redirects=False)
    client.post("/chat/confirm", follow_redirects=False)
    page = client.get("/chat")
    assert "Insufficient balance" in page.text


def test_chat_cancel_clears_pending(client):
    _login(client)
    agent_mod.set_llm_factory(
        lambda: FakeLLM(
            [
                tool("t1", "place_order", {"item_id": "CHR-001", "quantity": 1}),
                text("Confirm?"),
            ]
        )
    )
    client.post("/chat", data={"message": "buy a chair"}, follow_redirects=False)
    assert "Confirm purchase" in client.get("/chat").text
    client.post("/chat/cancel", follow_redirects=False)
    page = client.get("/chat")
    assert "place that order" in page.text  # apostrophe is HTML-escaped in template
    assert "Confirm purchase" not in page.text


def test_chat_post_endpoints_require_login(client):
    assert (
        client.post("/chat", data={"message": "hi"}, follow_redirects=False).headers["location"]
        == "/login"
    )
    assert client.post("/chat/confirm", follow_redirects=False).headers["location"] == ("/login")
    assert client.post("/chat/cancel", follow_redirects=False).headers["location"] == ("/login")
