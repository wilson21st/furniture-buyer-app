"""The four agent tools: definitions (Anthropic tool-use schema) + an executor.

Design notes baked into the descriptions (per the Participant Guide):
- The shop only does an EXACT, case-insensitive category match. Price/colour
  filtering is done here in Python over the results, NOT by the shop — the
  descriptions say so, so the model won't expect fuzzy matching from the API.
- ``place_order`` NEVER spends money on its own. It returns a confirmation
  request and a PendingOrder; the real debit happens only after the user confirms
  (see ``agent.execute_confirmed_order``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sqlmodel import Session

from app import furniture_api as fa
from app import shop


@dataclass
class PendingOrder:
    item_id: str
    product_name: str
    price: float
    quantity: int

    @property
    def total(self) -> float:
        return self.price * self.quantity


@dataclass
class ToolContext:
    api: fa.FurnitureAPI | None
    session: Session
    user: object  # Customer


TOOL_SCHEMAS = [
    {
        "name": "search_catalogue",
        "description": (
            "Search the furniture catalogue. `category` is matched EXACTLY and "
            "case-insensitively by the shop (e.g. 'Chairs'); it cannot interpret "
            "vague terms. `max_price` and `colour` are applied by this tool over "
            "the results after fetching — the shop itself does not understand them, "
            "so translate a user's vibe/budget into these fields yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Exact category name."},
                "max_price": {"type": "number", "description": "Keep items <= this."},
                "colour": {"type": "string", "description": "Keep items with this colour."},
            },
        },
    },
    {
        "name": "get_product",
        "description": "Full detail for one specific product by its item_id.",
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "string"}},
            "required": ["item_id"],
        },
    },
    {
        "name": "check_balance",
        "description": "The current user's remaining balance. Takes no arguments.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "place_order",
        "description": (
            "Request to buy a product for the current user. This does NOT place the "
            "order immediately — it asks for the user's confirmation first, because "
            "it spends a real balance. Only call it once you know the exact item_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "string"},
                "quantity": {"type": "integer", "minimum": 1},
            },
            "required": ["item_id"],
        },
    },
]


def _search(ctx: ToolContext, tool_input: dict) -> str:
    category = tool_input.get("category")
    max_price = tool_input.get("max_price")
    colour = tool_input.get("colour")
    products = shop.list_catalogue(ctx.api, ctx.session, category=category, limit=100)
    if max_price is not None:
        products = [p for p in products if p.price <= max_price]
    if colour:
        wanted = colour.lower()
        products = [p for p in products if wanted in [c.lower() for c in p.colours]]
    results = [
        {
            "item_id": p.item_id,
            "product_name": p.product_name,
            "price": p.price,
            "category": p.category,
            "colours": p.colours,
        }
        for p in products[:20]
    ]
    return json.dumps({"count": len(results), "results": results})


def execute(name: str, tool_input: dict, ctx: ToolContext) -> tuple[str, PendingOrder | None]:
    """Run a tool. Returns (content-for-the-model, optional PendingOrder)."""
    try:
        if name == "search_catalogue":
            return _search(ctx, tool_input), None

        if name == "get_product":
            view = shop.get_product_view(ctx.api, ctx.session, tool_input["item_id"])
            if view is None:
                return json.dumps({"error": "No such product."}), None
            return json.dumps(
                {
                    "item_id": view.item_id,
                    "product_name": view.product_name,
                    "price": view.price,
                    "category": view.category,
                    "colours": view.colours,
                }
            ), None

        if name == "check_balance":
            return json.dumps({"balance": shop.get_balance(ctx.api, ctx.user)}), None

        if name == "place_order":
            item_id = tool_input["item_id"]
            quantity = int(tool_input.get("quantity", 1))
            view = shop.get_product_view(ctx.api, ctx.session, item_id)
            if view is None:
                return json.dumps({"error": "No such product to order."}), None
            pending = PendingOrder(item_id, view.product_name, view.price, quantity)
            return (
                json.dumps(
                    {
                        "status": "confirmation_required",
                        "message": (
                            f"Ask the user to confirm buying {quantity} x "
                            f"{view.product_name} for ${pending.total:.2f}. "
                            "Do not claim the order is placed until they confirm."
                        ),
                    }
                ),
                pending,
            )

        return json.dumps({"error": f"Unknown tool '{name}'."}), None
    except shop.ShopError as exc:
        return json.dumps({"error": str(exc)}), None
    except fa.ApiError as exc:
        return json.dumps({"error": str(exc)}), None
