"""Shared Anthropic client seam + response helpers.

Both the agent (Step 6) and RAG (Step 8) talk to Claude the same way: through a tiny
``LLM`` protocol so tests inject a scripted fake, and both need to flatten a response's
text blocks. Keeping one definition here avoids the two near-identical copies that used
to live in ``agent.py`` and ``rag.py``.
"""

from __future__ import annotations

from typing import Any, Protocol

from app.config import get_settings


class LLM(Protocol):
    def create(self, **kwargs: Any) -> Any:  # pragma: no cover - protocol
        ...


def default_anthropic() -> LLM:  # pragma: no cover - needs anthropic + key
    """Build the real Anthropic-backed LLM from settings."""
    from anthropic import Anthropic

    client = Anthropic(api_key=get_settings().anthropic_api_key)

    class _Anthropic:
        def create(self, **kwargs: Any) -> Any:
            return client.messages.create(**kwargs)

    return _Anthropic()


def extract_text(blocks: Any) -> str:
    """Join the text of every text block in a Claude response's content list."""
    return "\n".join(
        b.text for b in blocks if getattr(b, "type", "") == "text" and getattr(b, "text", "")
    )
