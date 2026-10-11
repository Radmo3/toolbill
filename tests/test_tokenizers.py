import json

import pytest

from toolbill import TokenizerUnavailableError
from toolbill.tokenizers import (
    TiktokenTokenizer,
    canonical_json,
    count_tool,
    serialize_tool,
)


class CountingTokenizer:
    name = "character-count"

    def count(self, text: str) -> int:
        return len(text)


def test_canonical_json_sorts_keys_and_omits_nulls():
    tool = {
        "name": "x",
        "description": None,
        "inputSchema": {"properties": {"z": {"type": "string"}, "a": {"type": "integer"}}},
    }

    assert serialize_tool(tool) == (
        '{"inputSchema":{"properties":{"a":{"type":"integer"},'
        '"z":{"type":"string"}}},"name":"x"}'
    )


def test_tool_breakdown_and_total_use_documented_text():
    tool = {
        "name": "lookup",
        "description": "Find an item",
        "inputSchema": {"type": "object"},
        "annotations": {"readOnlyHint": True},
    }
    tokenizer = CountingTokenizer()

    total, breakdown = count_tool(tokenizer, tool)

    assert total == len(canonical_json(tool))
    assert breakdown == {
        "description": len("Find an item"),
        "schema": len('{"inputSchema":{"type":"object"}}'),
        "annotations": len('{"readOnlyHint":true}'),
    }


def test_tiktoken_uses_o200k_base():
    tokenizer = TiktokenTokenizer()

    assert tokenizer.name == "o200k_base"
    assert tokenizer.count("hello") > 0


def test_tiktoken_hash_mismatch_raises_tokenizer_unavailable(monkeypatch):
    import tiktoken

    def blocked_by_proxy(name):
        raise ValueError("Hash mismatch for data downloaded")

    monkeypatch.setattr(tiktoken, "get_encoding", blocked_by_proxy)

    with pytest.raises(TokenizerUnavailableError):
        TiktokenTokenizer()
