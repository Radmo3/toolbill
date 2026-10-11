"""Pluggable token counting and canonical MCP tool serialization."""

from __future__ import annotations

import json
from typing import Any, Protocol


class Tokenizer(Protocol):
    """Interface for tokenizers that count UTF-8 text."""

    name: str

    def count(self, text: str) -> int: ...


class TokenizerUnavailableError(RuntimeError):
    """Raised when the tokenizer's encoding file cannot be loaded."""


class TiktokenTokenizer:
    """OpenAI-compatible token counter using the o200k_base encoding."""

    name = "o200k_base"

    def __init__(self) -> None:
        import tiktoken

        try:
            self._encoding = tiktoken.get_encoding(self.name)
        except (OSError, ValueError) as exc:
            # tiktoken downloads the encoding on first use. Network and proxy
            # failures surface as OSError (requests errors subclass it), and a
            # proxy that returns the wrong content fails the hash check.
            raise TokenizerUnavailableError(
                f"Could not download the {self.name} tokenizer file "
                "(no network access or blocked by a proxy). Allow access to "
                "openaipublic.blob.core.windows.net, or set TIKTOKEN_CACHE_DIR "
                "to a directory that already contains the cached file."
            ) from exc

    def count(self, text: str) -> int:
        return len(self._encoding.encode(text))


def tool_as_dict(tool: Any) -> dict[str, Any]:
    """Convert an SDK Tool model or mapping to JSON-compatible protocol fields."""
    if hasattr(tool, "model_dump"):
        value = tool.model_dump(
            by_alias=True,
            exclude_none=True,
            exclude_unset=True,
            mode="json",
        )
    elif hasattr(tool, "dict"):
        value = tool.dict(
            by_alias=True,
            exclude_none=True,
            exclude_unset=True,
        )
    elif isinstance(tool, dict):
        value = tool
    else:
        raise TypeError("tool must be an MCP Tool model or mapping")

    if not isinstance(value, dict):
        raise TypeError("serialized MCP Tool must be an object")
    return _without_nulls(value)


def canonical_json(value: Any) -> str:
    """Serialize JSON with sorted keys, UTF-8 characters, and no extra spaces."""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def serialize_tool(tool: Any) -> str:
    """Return the canonical text counted for an MCP tool definition."""
    return canonical_json(tool_as_dict(tool))


def count_tool(tokenizer: Tokenizer, tool: Any) -> tuple[int, dict[str, int]]:
    """Count a complete definition and its description/schema/annotation fields."""
    data = tool_as_dict(tool)
    total = tokenizer.count(canonical_json(data))
    breakdown: dict[str, int] = {}

    description = data.get("description")
    if isinstance(description, str):
        breakdown["description"] = tokenizer.count(description)

    schema: dict[str, Any] = {}
    for key in ("inputSchema", "outputSchema"):
        if key in data:
            schema[key] = data[key]
    if schema:
        breakdown["schema"] = tokenizer.count(canonical_json(schema))

    if "annotations" in data:
        breakdown["annotations"] = tokenizer.count(
            canonical_json(data["annotations"])
        )
    return total, breakdown


def _without_nulls(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_nulls(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, list):
        return [_without_nulls(item) for item in value]
    return value
