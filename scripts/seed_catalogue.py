"""Seed the local DB from the shared read-only MongoDB catalogue (Step 2).

    uv run python -m scripts.seed_catalogue --limit 100

Reads CATALOGUE_MONGO_URI from the environment / .env. Idempotent: existing
products are skipped. This is a network CLI, so it is excluded from coverage.
"""

from __future__ import annotations

import argparse

from sqlmodel import Session

from app.catalogue_seed import seed_from_mongo
from app.config import get_settings
from app.db import get_engine, init_db


def main() -> None:  # pragma: no cover - CLI/network
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None, help="max products to load")
    args = parser.parse_args()

    settings = get_settings()
    if not settings.catalogue_mongo_uri:
        raise SystemExit("CATALOGUE_MONGO_URI is not set — add it to your .env")

    init_db()
    with Session(get_engine()) as session:
        added = seed_from_mongo(session, settings.catalogue_mongo_uri, limit=args.limit)
    print(f"Seeded {added} new products from the shared catalogue.")


if __name__ == "__main__":  # pragma: no cover
    main()
