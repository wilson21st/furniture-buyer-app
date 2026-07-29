"""A scripted fake of the Anthropic Messages API for testing the agent loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeResponse:
    content: list
    stop_reason: str = "end_turn"
    usage: Any = None


@dataclass
class FakeLLM:
    responses: list = field(default_factory=list)
    calls: list = field(default_factory=list)

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        return self.responses.pop(0)


def text(msg: str, usage: Any = None) -> FakeResponse:
    return FakeResponse([TextBlock(msg)], stop_reason="end_turn", usage=usage)


def tool(block_id: str, name: str, tool_input: dict) -> FakeResponse:
    return FakeResponse(
        [ToolUseBlock(block_id, name, tool_input)], stop_reason="tool_use"
    )
