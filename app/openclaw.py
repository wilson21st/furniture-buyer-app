"""OpenClaw skill: expose the four furniture-shop tools to OpenClaw (Step 9).

OpenClaw is a separate personal agent that runs on your laptop and can act through
WhatsApp. This module packages the SAME four tools from Step 6 (identical names and
descriptions) as an OpenClaw skill: a ``manifest()`` describing the tools + least
privilege, and a ``handle()`` dispatcher that executes one against the real shop.

Confirm-before-spend is preserved end to end: ``handle("place_order", ...)`` returns
a ``pending_order`` and does NOT spend; the caller must call ``confirm_order`` after
the human says yes in WhatsApp.
"""

from __future__ import annotations

from sqlmodel import Session

from app import agent as agent_mod
from app import shop
from app import tools as tools_mod
from app.config import get_settings
from app.db import get_engine
from app.furniture_api import FurnitureAPI
from app.models import Customer
from app.tools import PendingOrder, ToolContext

SKILL_NAME = "furniture-shop"
SKILL_DESCRIPTION = "Search a furniture catalogue, check balance, and place orders."


def manifest() -> dict:
    """The skill descriptor OpenClaw registers. Least privilege: shop API only."""
    return {
        "name": SKILL_NAME,
        "description": SKILL_DESCRIPTION,
        "version": "1.0.0",
        "permissions": ["network:furniture-api"],
        "confirm_before": ["place_order"],
        "tools": tools_mod.TOOL_SCHEMAS,
    }


def build_context() -> ToolContext:
    """Build a ToolContext for the configured user from settings."""
    settings = get_settings()
    api = FurnitureAPI.from_settings() if settings.use_real_api else None
    session = Session(get_engine())
    user = Customer(user_id=settings.furniture_user_id, name="OpenClaw user")
    return ToolContext(api=api, session=session, user=user)


def handle(tool_name: str, params: dict | None = None, ctx: ToolContext | None = None) -> dict:
    """Execute one tool call. Returns a JSON-able dict for OpenClaw to relay."""
    own = ctx is None
    ctx = ctx or build_context()
    try:
        content, pending = tools_mod.execute(tool_name, params or {}, ctx)
        out: dict = {"content": content}
        if pending is not None:
            out["pending_order"] = {
                "item_id": pending.item_id,
                "product_name": pending.product_name,
                "price": pending.price,
                "quantity": pending.quantity,
                "total": pending.total,
            }
        return out
    finally:
        if own:
            ctx.session.close()


def confirm_order(
    item_id: str, quantity: int = 1, ctx: ToolContext | None = None
) -> dict:
    """Finalise a previously-surfaced order (this is the step that spends money)."""
    own = ctx is None
    ctx = ctx or build_context()
    try:
        outcome = agent_mod.execute_confirmed_order(
            ctx, PendingOrder(item_id, "", 0.0, quantity)
        )
        return {
            "status": "success",
            "item_id": item_id,
            "total_price": outcome.total_price,
            "remaining_balance": outcome.remaining_balance,
        }
    except shop.ShopError as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if own:
            ctx.session.close()
