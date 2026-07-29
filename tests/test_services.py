import pytest
from sqlmodel import Session

from app import services
from app.models import Customer


@pytest.fixture
def session(initialized_db):
    with Session(initialized_db) as s:
        yield s


def test_create_and_authenticate(session):
    services.create_user(session, "u009", "Sam", "pw12345", balance=100.0)
    assert services.authenticate(session, "u009", "pw12345").name == "Sam"
    assert services.authenticate(session, "u009", "wrong") is None
    assert services.authenticate(session, "ghost", "pw12345") is None


def test_list_products_and_category_filter(session):
    services.seed_placeholder_products(session)
    all_products = services.list_products(session)
    assert len(all_products) == 5
    chairs = services.list_products(session, category="chairs")  # case-insensitive
    assert {p.item_id for p in chairs} == {"CHR-001", "CHR-002"}


def test_get_product(session):
    services.seed_placeholder_products(session)
    assert services.get_product(session, "CHR-001").price == 399.0
    assert services.get_product(session, "NOPE") is None


def test_seed_placeholder_is_idempotent(session):
    assert services.seed_placeholder_products(session) == 5
    assert services.seed_placeholder_products(session) == 0


def test_place_order_success_reduces_balance(session):
    services.seed_placeholder_products(session)
    user = services.create_user(session, "u001", "Asha", "pw", balance=1000.0)
    order = services.place_order(session, user, "CHR-001")  # 399
    assert order.total_price == 399.0
    assert user.local_balance == 601.0
    assert services.order_history(session, "u001")[0].item_id == "CHR-001"


def test_place_order_unknown_product_raises(session):
    user = services.create_user(session, "u001", "Asha", "pw", balance=1000.0)
    with pytest.raises(services.ProductNotFoundError) as exc:
        services.place_order(session, user, "GHOST")
    assert exc.value.item_id == "GHOST"


def test_place_order_insufficient_balance_raises(session):
    services.seed_placeholder_products(session)
    user = services.create_user(session, "u001", "Asha", "pw", balance=50.0)
    with pytest.raises(services.InsufficientBalanceError) as exc:
        services.place_order(session, user, "CHR-001")  # 399 > 50
    assert exc.value.needed == 399.0
    assert exc.value.available == 50.0


def test_order_history_and_total_spent(session):
    services.seed_placeholder_products(session)
    user = services.create_user(session, "u001", "Asha", "pw", balance=5000.0)
    assert services.total_spent(session, "u001") == 0.0
    services.place_order(session, user, "CHR-001")  # 399
    services.place_order(session, user, "LMP-001")  # 89
    assert services.total_spent(session, "u001") == 488.0
    assert len(services.order_history(session, "u001")) == 2


def test_bootstrap_demo_idempotent(session):
    services.bootstrap_demo(session)
    services.bootstrap_demo(session)  # second call is a no-op
    assert session.get(Customer, services.DEMO_USER_ID) is not None
    assert len(services.list_products(session)) == 5
