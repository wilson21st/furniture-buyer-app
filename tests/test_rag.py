"""Unit tests for the RAG library, using a deterministic bag-of-words embedder."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from app import rag

VOCAB = ["chair", "table", "sofa", "lamp", "blue", "mustard", "cheap", "grey"]


class BagEmbedder:
    """Deterministic embeddings: count vocab word occurrences (offline, stable)."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            low = text.lower()
            vectors.append([float(low.count(word)) for word in VOCAB])
        return vectors


PRODUCTS = [
    {
        "item_id": "CHR-001",
        "product_name": "Mustard Chair",
        "price": 399.0,
        "category": "Chairs",
        "colours": ["mustard"],
    },
    {
        "item_id": "SOF-001",
        "product_name": "Blue Sofa",
        "price": 900.0,
        "category": "Sofas",
        "colours": ["blue"],
    },
    {
        "item_id": "LMP-001",
        "product_name": "Grey Lamp",
        "price": 49.0,
        "category": "Lighting",
        "colours": ["grey"],
    },
]


@dataclass
class _Text:
    text: str
    type: str = "text"


@dataclass
class _Resp:
    content: list


class FakeRagLLM:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _Resp([_Text(self.answer)])


def test_chunk_products_maps_fields():
    chunks = rag.chunk_products(PRODUCTS)
    assert len(chunks) == 3
    assert chunks[0].item_id == "CHR-001"
    assert "Mustard Chair" in chunks[0].text
    assert chunks[0].metadata["price"] == 399.0


def test_chunk_products_handles_missing_fields():
    chunks = rag.chunk_products([{"item_id": "X"}])
    assert "Colours: n/a" in chunks[0].text
    assert chunks[0].metadata["price"] == 0.0


def test_naive_paragraph_chunks():
    assert rag.naive_paragraph_chunks("a\n\n b \n\n\n c") == ["a", "b", "c"]


def test_normalize_handles_zero_vector():
    out = rag._normalize(np.array([[0.0, 0.0], [3.0, 4.0]]))
    assert np.allclose(out[0], [0.0, 0.0])  # zero row stays zero, no divide error
    assert np.allclose(np.linalg.norm(out[1]), 1.0)


def test_index_retrieves_most_similar():
    index = rag.VectorIndex(embedder=BagEmbedder()).build(rag.chunk_products(PRODUCTS))
    hits = index.search("something blue like a sofa", k=1)
    assert hits[0][0].item_id == "SOF-001"
    assert hits[0][1] > 0  # positive cosine similarity


def test_index_uses_factory_when_no_embedder():
    rag.set_embedder_factory(BagEmbedder)
    index = rag.VectorIndex()  # no embedder passed
    assert isinstance(index._embedder, BagEmbedder)


def test_answer_question_cites_sources():
    index = rag.VectorIndex(embedder=BagEmbedder()).build(rag.chunk_products(PRODUCTS))
    llm = FakeRagLLM("The Blue Sofa (SOF-001) fits best.")
    answer = rag.answer_question(index, "cheapest blue thing?", k=2, llm=llm)
    assert "SOF-001" in answer.text
    assert len(answer.sources) == 2
    # the prompt handed to the model contained the retrieved context
    assert "Products:" in llm.calls[0]["messages"][0]["content"]


def test_answer_question_uses_llm_factory():
    index = rag.VectorIndex(embedder=BagEmbedder()).build(rag.chunk_products(PRODUCTS))
    rag.set_rag_llm_factory(lambda: FakeRagLLM("factory answer"))
    answer = rag.answer_question(index, "anything?", k=1)
    assert answer.text == "factory answer"


@pytest.fixture(autouse=True)
def _reset_factories():
    yield
    rag.set_embedder_factory(rag.default_embedder)
    rag.set_rag_llm_factory(rag.default_rag_llm)
