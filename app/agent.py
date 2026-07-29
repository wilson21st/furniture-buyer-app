"""Level 3 agent: a Claude tool-use loop over the four furniture-shop tools.

The LLM is behind a tiny ``LLM`` protocol so tests inject a scripted fake and the
loop runs without a network call. Every turn is traced with Langfuse
(``record_generation``) and every tool call gets its own span. ``place_order``
never spends on its own — the loop surfaces a PendingOrder and the real debit only
happens in ``execute_confirmed_order`` after the user confirms.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app import observability
from app import tools as tools_mod
from app.config import get_settings
from app.shop import OrderOutcome, place_order
from app.tools import PendingOrder, ToolContext

SYSTEM_PROMPT = (
    "You are a shopping assistant for a furniture store. You help the user browse "
    "the catalogue, check their balance, and buy items using the provided tools.\n"
    "- The catalogue only matches an exact category. Any reasoning about 'cheap', "
    "budgets, or colours is YOUR job: translate the request into the tool's "
    "category/max_price/colour fields and filter/reason over the results.\n"
    "- Never fetch or reason about product images.\n"
    "- Placing an order spends a real balance. ALWAYS show the item and price and "
    "get the user's explicit confirmation before an order is finalised. If a tool "
    "reports an error (insufficient balance, unknown item), explain it plainly and "
    "suggest an alternative rather than repeating the call."
)

MAX_STEPS = 6


class LLM(Protocol):
    def create(self, **kwargs: Any) -> Any:  # pragma: no cover - protocol
        ...


@dataclass
class AgentReply:
    text: str
    pending_order: PendingOrder | None = None
    steps: list[str] = field(default_factory=list)


def default_llm() -> LLM:  # pragma: no cover - needs anthropic + key
    from anthropic import Anthropic

    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)

    class _Anthropic:
        def create(self, **kwargs: Any) -> Any:
            return client.messages.create(**kwargs)

    return _Anthropic()


_llm_factory: Callable[[], LLM] = default_llm


def set_llm_factory(factory: Callable[[], LLM]) -> None:
    """Override how the LLM client is built (used by tests)."""
    global _llm_factory
    _llm_factory = factory


def _block_to_dict(block: Any) -> dict:
    if block.type == "tool_use":
        return {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
    return {"type": "text", "text": getattr(block, "text", "")}


def _extract_text(blocks: list) -> str:
    return "\n".join(b.text for b in blocks if b.type == "text" and getattr(b, "text", ""))


class Agent:
    def __init__(self, ctx: ToolContext, llm: LLM | None = None, model: str | None = None):
        self.ctx = ctx
        self._llm = llm or _llm_factory()
        self._model = model or get_settings().anthropic_model

    def _create(self, messages: list[dict]) -> Any:
        response = self._llm.create(
            model=self._model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=tools_mod.TOOL_SCHEMAS,
            messages=messages,
        )
        observability.record_generation(
            name="agent.turn",
            model=self._model,
            input=messages[-1] if messages else None,
            output={"stop_reason": getattr(response, "stop_reason", None)},
            usage=getattr(response, "usage", None) and vars(response.usage),
        )
        return response

    def respond(self, user_text: str, history: list[dict]) -> tuple[AgentReply, list[dict]]:
        messages = [*history, {"role": "user", "content": user_text}]
        pending: PendingOrder | None = None
        steps: list[str] = []

        with observability.span("agent.respond", user=str(getattr(self.ctx.user, "user_id", ""))):
            for _ in range(MAX_STEPS):
                response = self._create(messages)
                blocks = response.content
                messages.append(
                    {"role": "assistant", "content": [_block_to_dict(b) for b in blocks]}
                )

                if getattr(response, "stop_reason", None) != "tool_use":
                    return AgentReply(_extract_text(blocks), pending, steps), messages

                tool_results = []
                for block in blocks:
                    if block.type != "tool_use":
                        continue
                    with observability.span(f"tool.{block.name}"):
                        content, maybe_pending = tools_mod.execute(
                            block.name, block.input, self.ctx
                        )
                    steps.append(block.name)
                    if maybe_pending is not None:
                        pending = maybe_pending
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": content,
                        }
                    )
                messages.append({"role": "user", "content": tool_results})

        return (
            AgentReply(
                "Sorry, I couldn't finish that — let's try rephrasing.", pending, steps
            ),
            messages,
        )


def execute_confirmed_order(ctx: ToolContext, pending: PendingOrder) -> OrderOutcome:
    """Actually place the order (spends the balance). Raises ShopError on failure."""
    with observability.span("agent.confirm_order", item_id=pending.item_id):
        return place_order(ctx.api, ctx.session, ctx.user, pending.item_id, pending.quantity)
