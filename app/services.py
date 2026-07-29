"""Business logic: users, catalogue reads, the balance workflow rule, and reports.

This is Level 1 logic operating on the local SQLite database. In Step 5 the
catalogue/balance/order calls are swapped for the real API, but the workflow rule
(never let a user spend past their balance) and the report shape stay the same.
"""

from __future__ import annotations

from sqlmodel import Session, func, select

from app.auth import hash_password, verify_password
from app.config import get_settings
from app.models import Customer, Order, Product


class ServiceError(Exception):
    """Base class for expected, user-facing failures."""


class ProductNotFoundError(ServiceError):
    def __init__(self, item_id: str):
        self.item_id = item_id
        super().__init__(f"Product '{item_id}' is no longer available.")


class LocalInsufficientBalanceError(ServiceError):
    def __init__(self, needed: float, available: float):
        self.needed = needed
        self.available = available
        super().__init__(
            f"Insufficient balance: need ${needed:.2f} but only ${available:.2f} left."
        )


# --- Users -----------------------------------------------------------------
def create_user(
    session: Session, user_id: str, name: str, password: str, balance: float = 0.0
) -> Customer:
    user = Customer(
        user_id=user_id,
        name=name,
        password_hash=hash_password(password),
        local_balance=balance,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def authenticate(session: Session, user_id: str, password: str) -> Customer | None:
    user = session.get(Customer, user_id)
    if user and verify_password(password, user.password_hash):
        return user
    return None


# --- Catalogue -------------------------------------------------------------
def list_products(
    session: Session, category: str | None = None, limit: int = 50, skip: int = 0
) -> list[Product]:
    statement = select(Product)
    if category:
        # Exact, case-insensitive category match — mirrors the real API's behaviour.
        statement = statement.where(func.lower(Product.category) == category.lower())
    statement = statement.order_by(Product.product_name).offset(skip).limit(limit)
    return list(session.exec(statement).all())


def get_product(session: Session, item_id: str) -> Product | None:
    return session.get(Product, item_id)


def seed_placeholder_products(session: Session) -> int:
    placeholders = [
        ("CHR-001", "Aria Accent Chair", 399.0, "Chairs", ["mustard"]),
        ("CHR-002", "Nord Dining Chair", 149.0, "Chairs", ["oak", "white"]),
        ("TBL-001", "Fjord Coffee Table", 259.0, "Tables", ["walnut"]),
        ("SOF-001", "Loom 3-Seat Sofa", 1199.0, "Sofas", ["teal"]),
        ("LMP-001", "Halo Floor Lamp", 89.0, "Lighting", ["black"]),
    ]
    count = 0
    for item_id, name, price, category, colours in placeholders:
        if session.get(Product, item_id):
            continue
        product = Product(item_id=item_id, product_name=name, price=price, category=category)
        product.set_colours(colours)
        session.add(product)
        count += 1
    session.commit()
    return count


# --- Orders (workflow rule + report) ---------------------------------------
def place_order(session: Session, user: Customer, item_id: str, quantity: int = 1) -> Order:
    product = session.get(Product, item_id)
    if product is None:
        raise ProductNotFoundError(item_id)
    total = product.price * quantity
    if total > user.local_balance:
        raise LocalInsufficientBalanceError(needed=total, available=user.local_balance)
    user.local_balance -= total
    order = Order(user_id=user.user_id, item_id=item_id, quantity=quantity, total_price=total)
    session.add(order)
    session.add(user)
    session.commit()
    session.refresh(order)
    return order


def order_history(session: Session, user_id: str) -> list[Order]:
    statement = select(Order).where(Order.user_id == user_id).order_by(Order.created_at.desc())
    return list(session.exec(statement).all())


def total_spent(session: Session, user_id: str) -> float:
    statement = select(func.coalesce(func.sum(Order.total_price), 0.0)).where(
        Order.user_id == user_id
    )
    return float(session.exec(statement).one())


# --- Bootstrap -------------------------------------------------------------
DEMO_USER_ID = "u001"
DEMO_PASSWORD = "demo1234"  # nosec B105 - dev-only demo credential, gated by SEED_DEMO_USER
DEMO_BALANCE = 2500.0


def bootstrap_demo(session: Session) -> None:
    """Idempotently ensure a demo user + placeholder catalogue exist.

    The known-credential demo user is only seeded when ``SEED_DEMO_USER`` is on
    (default in dev; forced off in prod by config validation). The placeholder
    catalogue is always safe to seed as a browsing fallback.
    """
    if get_settings().seed_demo_user and session.get(Customer, DEMO_USER_ID) is None:
        create_user(session, DEMO_USER_ID, "Asha Verma", DEMO_PASSWORD, balance=DEMO_BALANCE)
    if not list_products(session, limit=1):
        seed_placeholder_products(session)
