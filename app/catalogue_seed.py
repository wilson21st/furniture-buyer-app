"""Load the shared, read-only MongoDB catalogue into local Product rows (Step 2).

The connection itself (network) is thin and coverage-excluded; the mapping and
seeding logic are pure and fully tested with plain dicts / mongomock.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from app.models import Product

CATALOGUE_DB = "catalog"
CATALOGUE_COLLECTION = "catalog"


def get_mongo_client(uri: str):  # pragma: no cover - network
    from pymongo import MongoClient

    return MongoClient(uri, serverSelectionTimeoutMS=5000)


def fetch_catalogue(client: Any, limit: int | None = None) -> list[dict]:
    collection = client[CATALOGUE_DB][CATALOGUE_COLLECTION]
    cursor = collection.find({}, {"_id": 0})
    if limit:
        cursor = cursor.limit(limit)
    return list(cursor)


def doc_to_product(doc: dict) -> Product:
    product = Product(
        item_id=doc["item_id"],
        product_name=doc.get("product_name", ""),
        price=float(doc.get("price") or 0.0),
        category=doc.get("category") or "",
        image_url=doc.get("image_url"),
    )
    product.set_colours(list(doc.get("colours") or []))
    return product


def seed_products(session: Session, docs: list[dict]) -> int:
    count = 0
    for doc in docs:
        item_id = doc.get("item_id")
        if not item_id or session.get(Product, item_id):
            continue
        session.add(doc_to_product(doc))
        count += 1
    session.commit()
    return count


def seed_from_mongo(  # pragma: no cover - network
    session: Session, uri: str, limit: int | None = None
) -> int:
    client = get_mongo_client(uri)
    try:
        docs = fetch_catalogue(client, limit=limit)
    finally:
        client.close()
    return seed_products(session, docs)
