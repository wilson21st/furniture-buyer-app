"""RAG Q&A demo over the live catalogue (Step 8, optional).

    uv run python -m scripts.rag_demo "what's the most affordable option in blue?"

Loads the shared MongoDB catalogue, builds an in-memory vector index (Voyage
embeddings), and answers with Claude grounded in the retrieved products. Needs
VOYAGE_API_KEY + ANTHROPIC_API_KEY + CATALOGUE_MONGO_URI in .env. Network CLI.
"""

from __future__ import annotations

import sys

from app import rag
from app.catalogue_seed import CATALOGUE_COLLECTION, CATALOGUE_DB, get_mongo_client
from app.config import get_settings


def main() -> None:  # pragma: no cover - CLI/network
    if len(sys.argv) < 2:
        raise SystemExit('usage: python -m scripts.rag_demo "your question"')
    question = " ".join(sys.argv[1:])

    settings = get_settings()
    client = get_mongo_client(settings.catalogue_mongo_uri)
    try:
        docs = list(client[CATALOGUE_DB][CATALOGUE_COLLECTION].find({}, {"_id": 0}))
    finally:
        client.close()

    index = rag.VectorIndex().build(rag.chunk_products(docs))
    answer = rag.answer_question(index, question, k=5)
    print(answer.text)
    print("\nsources:", ", ".join(answer.sources))


if __name__ == "__main__":  # pragma: no cover
    main()
