from app.main import colour_hex, initials


def test_colour_hex_known_and_unknown():
    assert colour_hex("Mustard") == "#d9a441"  # case-insensitive
    assert colour_hex("teal") == "#1f7a8c"
    assert colour_hex("chartreuse") == "#c7cbd1"  # fallback
    assert colour_hex(None) == "#c7cbd1"


def test_initials_variants():
    assert initials("Asha Verma") == "AV"
    assert initials("Sam") == "S"
    assert initials("") == "?"
    assert initials(None) == "?"


def test_static_css_is_served(client):
    resp = client.get("/static/styles.css")
    assert resp.status_code == 200
    assert "product-card" in resp.text


def test_home_uses_stylesheet_and_brand(client):
    html = client.get("/").text
    assert "/static/styles.css" in html
    assert "Furnish" in html
