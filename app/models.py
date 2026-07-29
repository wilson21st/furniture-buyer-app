"""Entity model: Customer, Product, Order (SQLModel tables).

Colours are stored as a JSON string to keep the SQLite schema trivial; use the
``colours`` property / ``set_colours`` helper rather than touching the raw column.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Customer(SQLModel, table=True):
    user_id: str = Field(primary_key=True)
    name: str
    password_hash: str = ""
    # Local fallback balance for offline Level 1; the API is authoritative from L2.
    local_balance: float = 0.0
    created_at: datetime = Field(default_factory=_utcnow)


class Product(SQLModel, table=True):
    item_id: str = Field(primary_key=True)
    product_name: str
    price: float = 0.0
    category: str = ""
    colours_json: str = "[]"
    image_url: str | None = None

    @property
    def colours(self) -> list[str]:
        return json.loads(self.colours_json or "[]")

    def set_colours(self, values: list[str]) -> None:
        self.colours_json = json.dumps(list(values))


class Order(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: str = Field(foreign_key="customer.user_id", index=True)
    item_id: str
    quantity: int = 1
    total_price: float = 0.0
    status: str = "success"
    created_at: datetime = Field(default_factory=_utcnow)
