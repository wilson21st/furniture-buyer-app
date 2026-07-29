"""Tests for the shared LLM helper (extract_text)."""

from __future__ import annotations

from dataclasses import dataclass

from app.llm import extract_text


@dataclass
class _Block:
    type: str
    text: str = ""


def test_extract_text_joins_only_text_blocks():
    blocks = [_Block("text", "hello"), _Block("tool_use"), _Block("text", "world")]
    assert extract_text(blocks) == "hello\nworld"


def test_extract_text_skips_empty_and_nontext():
    assert extract_text([_Block("text", ""), _Block("tool_use")]) == ""
