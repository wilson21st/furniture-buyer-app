import mongomock
import pytest
from sqlmodel import Session

from app import catalogue_seed as cat


@pytest.fixture
def session(initialized_db):
    with Session(initialized_db) as s:
        yield s


SAMPLE = [
    {
        "item_id": "CHR-001",
        "product_name": "Aria Accent Chair",
        "price": 399.0,
        "category": "Chairs",
        "colours": ["mustard"],
        "image_url": "https://img/chr-001.jpg",
    },
    {"item_id": "TBL-001", "product_name": "Fjord Table"},  # sparse doc
    {"product_name": "no id — skipped"},  # missing item_id
]


def test_doc_to_product_full_and_sparse():
    full = cat.doc_to_product(SAMPLE[0])
    assert full.price == 399.0
    assert full.colours == ["mustard"]
    assert full.image_url.endswith("chr-001.jpg")

    sparse = cat.doc_to_product(SAMPLE[1])
    assert sparse.price == 0.0
    assert sparse.category == ""
    assert sparse.colours == []


def test_fetch_catalogue_with_projection_and_limit():
    client = mongomock.MongoClient()
    client[cat.CATALOGUE_DB][cat.CATALOGUE_COLLECTION].insert_many(
        [dict(d) for d in SAMPLE if d.get("item_id")]
    )
    docs = cat.fetch_catalogue(client)
    assert all("_id" not in d for d in docs)  # projection excludes _id
    assert cat.fetch_catalogue(client, limit=1) == docs[:1]


def test_seed_products_counts_and_skips(session):
    added = cat.seed_products(session, SAMPLE)
    assert added == 2  # the no-id doc is skipped
    # Re-seeding skips already-present items.
    assert cat.seed_products(session, SAMPLE) == 0
