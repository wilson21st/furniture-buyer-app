"""Level 4 (optional): vector RAG Q&A over the product catalogue.

Pipeline: chunk (one per product) → embed → store in-memory → cosine-similarity
retrieve → generate a grounded answer with Claude. Both the embedder and the LLM
are behind tiny factories so tests inject deterministic fakes and run offline.
Retrieval and generation are traced with Langfuse.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from app import observability
from app.config import get_settings
from app.llm import LLM, default_anthropic, extract_text


# --- Data ------------------------------------------------------------------
@dataclass
class Chunk:
    item_id: str
    text: str
    metadata: dict = field(default_factory=dict)


@dataclass
class RagAnswer:
    text: str
    sources: list[str]


# --- Providers (protocols + real defaults) ---------------------------------
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:  # pragma: no cover
        ...


def default_embedder() -> Embedder:  # pragma: no cover - needs voyage + key
    import voyageai

    settings = get_settings()
    client = voyageai.Client(api_key=settings.voyage_api_key)
    model = settings.embedding_model

    class _Voyage:
        def embed(self, texts: list[str]) -> list[list[float]]:
            return client.embed(texts, model=model, input_type="document").embeddings

    return _Voyage()


def default_rag_llm() -> LLM:  # pragma: no cover - needs anthropic + key
    return default_anthropic()


_embedder_factory: Callable[[], Embedder] = default_embedder
_rag_llm_factory: Callable[[], LLM] = default_rag_llm


def set_embedder_factory(factory: Callable[[], Embedder]) -> None:
    global _embedder_factory
    _embedder_factory = factory


def set_rag_llm_factory(factory: Callable[[], LLM]) -> None:
    global _rag_llm_factory
    _rag_llm_factory = factory


# --- Chunking --------------------------------------------------------------
def chunk_products(products: list[dict]) -> list[Chunk]:
    """One chunk per product, keeping structured fields in the metadata."""
    chunks = []
    for p in products:
        colours = ", ".join(p.get("colours") or []) or "n/a"
        text = (
            f"{p.get('product_name', '')} — category {p.get('category', '')}. "
            f"Price ${float(p.get('price') or 0):.2f}. Colours: {colours}."
        )
        chunks.append(
            Chunk(
                item_id=p.get("item_id", ""),
                text=text,
                metadata={
                    "product_name": p.get("product_name", ""),
                    "price": float(p.get("price") or 0),
                    "category": p.get("category", ""),
                },
            )
        )
    return chunks


def naive_paragraph_chunks(text: str) -> list[str]:
    """Fallback splitter for free text (e.g. extracted PDF): split on blank lines."""
    return [block.strip() for block in text.split("\n\n") if block.strip()]


def extract_pdf_text(path: str) -> str:  # pragma: no cover - needs a real PDF file
    from pypdf import PdfReader

    reader = PdfReader(path)
    return "\n\n".join(page.extract_text() or "" for page in reader.pages)


# --- Vector maths ----------------------------------------------------------
def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


# --- Index -----------------------------------------------------------------
class VectorIndex:
    def __init__(self, embedder: Embedder | None = None):
        self._embedder = embedder or _embedder_factory()
        self._chunks: list[Chunk] = []
        self._vectors = np.zeros((0, 0))

    def build(self, chunks: list[Chunk]) -> VectorIndex:
        self._chunks = chunks
        raw = np.array(self._embedder.embed([c.text for c in chunks]), dtype=float)
        self._vectors = _normalize(raw)
        return self

    def search(self, query: str, k: int = 3) -> list[tuple[Chunk, float]]:
        with observability.span("rag.retrieve", k=k):
            q = np.array(self._embedder.embed([query])[0], dtype=float)[None, :]
            sims = (self._vectors @ _normalize(q).T).ravel()
            order = np.argsort(-sims)[:k]
            return [(self._chunks[i], float(sims[i])) for i in order]


def answer_question(
    index: VectorIndex, question: str, k: int = 3, llm: LLM | None = None
) -> RagAnswer:
    hits = index.search(question, k=k)
    context = "\n".join(f"- [{c.item_id}] {c.text}" for c, _ in hits)
    prompt = (
        "Answer the question using ONLY the products below. If none fit, say so.\n\n"
        f"Products:\n{context}\n\nQuestion: {question}"
    )
    client = llm or _rag_llm_factory()
    settings = get_settings()
    response = client.create(
        model=settings.anthropic_model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = extract_text(response.content)
    observability.record_generation(
        name="rag.answer", model=settings.anthropic_model, input=question, output=text
    )
    return RagAnswer(text=text, sources=[c.item_id for c, _ in hits])
