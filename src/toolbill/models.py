"""Public report objects returned by the audit API."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


ServerStatus = Literal["ok", "failed", "skipped"]


@dataclass(frozen=True)
class ToolReport:
    name: str
    tokens: int
    breakdown: dict[str, int] = field(default_factory=dict)


@dataclass
class ServerReport:
    name: str
    tools: list[ToolReport] = field(default_factory=list)
    status: ServerStatus = "ok"
    error: str | None = None
    client: str | None = None
    source: str | None = None
    share: float = 0.0

    @property
    def tokens(self) -> int:
        return sum(tool.tokens for tool in self.tools)

    @property
    def tool_count(self) -> int:
        return len(self.tools)

    def heaviest(self, count: int = 5) -> list[ToolReport]:
        if count < 0:
            raise ValueError("count must be non-negative")
        return sorted(self.tools, key=lambda tool: tool.tokens, reverse=True)[:count]


@dataclass
class AuditReport:
    servers: list[ServerReport] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.servers.sort(key=lambda server: server.tokens, reverse=True)
        total = sum(server.tokens for server in self.servers)
        for server in self.servers:
            server.share = server.tokens / total if total else 0.0

    @property
    def total_tokens(self) -> int:
        return sum(server.tokens for server in self.servers)

    @property
    def tool_count(self) -> int:
        return sum(server.tool_count for server in self.servers)

    def __getitem__(self, name: str) -> ServerReport:
        for server in self.servers:
            if server.name == name:
                return server
        raise KeyError(name)

    def __iter__(self):
        return iter(self.servers)
