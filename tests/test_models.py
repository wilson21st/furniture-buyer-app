from app.models import Customer, Order, Product


def test_product_colours_roundtrip():
    p = Product(item_id="CHR-001", product_name="Aria", price=399.0, category="Chairs")
    assert p.colours == []
    p.set_colours(["mustard", "teal"])
    assert p.colours == ["mustard", "teal"]


def test_product_colours_empty_string_is_empty_list():
    p = Product(item_id="X", product_name="Y", colours_json="")
    assert p.colours == []


def test_customer_defaults():
    c = Customer(user_id="u001", name="Asha")
    assert c.local_balance == 0.0
    assert c.created_at is not None


def test_order_defaults():
    o = Order(user_id="u001", item_id="CHR-001", total_price=399.0)
    assert o.quantity == 1
    assert o.status == "success"
