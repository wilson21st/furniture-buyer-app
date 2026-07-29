"""Unified shop layer over two data sources: local SQLite (L1) and the real API (L2).

Routes and the agent depend on this module rather than branching on the data source
themselves. Every expected failure is normalised to a single ``ShopError`` carrying a
user-friendly message, so callers never have to know which backend produced it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session

from app import furniture_api as fa
from app import services
from app.models import Customer


class ShopError(Exception):
    """An expected, user-facing shop failure with a friendly message."""


@dataclass
class ProductView:
    item_id: str
    product_name: str
    price: float
    category: str
    colours: list[str]


@dataclass
class OrderView:
    item_id: str
    quantity: int
    total_price: float
    status: str
    created_at: datetime | None = None


@dataclass
class OrderOutcome:
    item_id: str
    total_price: float
    remaining_balance: float


def list_catalogue(
    api: fa.FurnitureAPI | None,
    session: Session,
    category: str | None = None,
    limit: int = 100,
) -> list[ProductView]:
    if api is not None:
        products = api.search_products(category=category, limit=limit)
        return [
            ProductView(p.item_id, p.product_name, p.price, p.category, p.colours)
            for p in products
        ]
    local = services.list_products(session, category=category, limit=limit)
    return [
        ProductView(p.item_id, p.product_name, p.price, p.category, p.colours)
        for p in local
    ]


def get_balance(api: fa.FurnitureAPI | None, user: Customer) -> float:
    if api is not None:
        return api.get_balance().balance
    return user.local_balance


def get_product_view(
    api: fa.FurnitureAPI | None, session: Session, item_id: str
) -> ProductView | None:
    if api is not None:
        try:
            p = api.get_product(item_id)
        except fa.ApiError:
            return None
        return ProductView(p.item_id, p.product_name, p.price, p.category, p.colours)
    local = services.get_product(session, item_id)
    if local is None:
        return None
    return ProductView(
        local.item_id, local.product_name, local.price, local.category, local.colours
    )


def _friendly(exc: Exception) -> str:
    if isinstance(exc, (fa.InsufficientBalanceError, services.InsufficientBalanceError)):
        return "Insufficient balance — this order costs more than you have left."
    if isinstance(exc, (fa.NotFoundError, services.ProductNotFoundError)):
        return "This item is no longer available."
    if isinstance(exc, fa.RateLimitError):
        wait = exc.retry_after or "a few"
        return f"The shop is busy right now — please try again in {wait} seconds."
    if isinstance(exc, (fa.AuthError, fa.ForbiddenError)):
        return "We couldn't authorise that request. Check the API key configuration."
    return "Sorry, something went wrong placing that order. Please try again."


def place_order(
    api: fa.FurnitureAPI | None,
    session: Session,
    user: Customer,
    item_id: str,
    quantity: int = 1,
) -> OrderOutcome:
    if api is not None:
        try:
            result = api.place_order(item_id, quantity)
        except fa.ApiError as exc:
            raise ShopError(_friendly(exc)) from exc
        return OrderOutcome(item_id, result.total_price, result.remaining_balance)
    try:
        order = services.place_order(session, user, item_id, quantity)
    except services.ServiceError as exc:
        raise ShopError(_friendly(exc)) from exc
    return OrderOutcome(order.item_id, order.total_price, user.local_balance)


def order_history(
    api: fa.FurnitureAPI | None, session: Session, user: Customer
) -> list[OrderView]:
    if api is not None:
        return [
            OrderView(r.item_id, r.quantity, r.total_price, r.status)
            for r in api.order_history()
        ]
    return [
        OrderView(o.item_id, o.quantity, o.total_price, o.status, o.created_at)
        for o in services.order_history(session, user.user_id)
    ]
