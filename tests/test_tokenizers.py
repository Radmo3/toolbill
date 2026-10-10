import json

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
