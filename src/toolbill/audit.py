"""Connect to configured stdio MCP servers and audit their tools."""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence, TextIO

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from toolbill.discovery import ServerConfig, parse_config
from toolbill.models import AuditReport, ServerReport, ToolReport
from toolbill.tokenizers import Tokenizer, TiktokenTokenizer, count_tool


async def audit_server(
    command: str,
    args: Sequence[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    name: str | None = None,
    model: str = "openai",
    timeout: float = 15.0,
    verbose: bool = False,
    tokenizer: Tokenizer | None = None,
) -> ServerReport:
    """Audit one MCP server using the official SDK's stdio transport."""
    if model != "openai":
        raise ValueError("Only the openai tokenizer is supported in v0.1.0")
    server_name = name or command
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    token_counter = tokenizer if tokenizer is not None else TiktokenTokenizer()
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)

    server_params = StdioServerParameters(
        command=command,
        args=list(args or ()),
        env=merged_env,
        cwd=cwd,
    )
    try:
        with _server_stderr(verbose) as errlog:
            tools = await asyncio.wait_for(
                _connect_and_list(server_params, errlog),
                timeout=timeout,
            )
        reports = []
        for tool in tools:
            tokens, breakdown = count_tool(token_counter, tool)
            reports.append(
                ToolReport(name=str(tool.name), tokens=tokens, breakdown=breakdown)
            )
        reports.sort(key=lambda item: item.tokens, reverse=True)
        total = sum(tool.tokens for tool in reports)
        return ServerReport(
            name=server_name,
            tools=reports,
            status="ok",
            share=1.0 if total else 0.0,
        )
    except asyncio.TimeoutError:
        return ServerReport(
            name=server_name,
            status="failed",
            error=f"Timed out after {timeout:g} seconds",
        )
    except Exception as exc:
        return ServerReport(
            name=server_name,
            status="failed",
            error=f"Server audit failed ({_exception_name(exc)})",
        )


@contextmanager
def _server_stderr(verbose: bool) -> Iterator[TextIO]:
    if not verbose:
        with open(os.devnull, "w", encoding="utf-8") as sink:
            yield sink
        return

    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as captured:
        try:
            yield captured
        finally:
            captured.flush()
            captured.seek(0)
            output = captured.read()
            if output:
                sys.stderr.write(output)
                sys.stderr.flush()


async def _connect_and_list(
    server_params: StdioServerParameters,
    errlog: TextIO,
) -> list[Any]:
    async with stdio_client(server_params, errlog=errlog) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await _list_all_tools(session)


def _exception_name(exc: Exception) -> str:
    nested = getattr(exc, "exceptions", None)
    if nested:
        return _exception_name(nested[0])
    return type(exc).__name__


async def audit_config(
    config: str | Path,
    *,
    model: str = "openai",
    timeout: float = 15.0,
    verbose: bool = False,
    tokenizer: Tokenizer | None = None,
) -> AuditReport:
    """Audit every server in one supported MCP client JSON config."""
    servers = parse_config(config)
    reports = await _audit_configs(
        servers,
        model=model,
        timeout=timeout,
        verbose=verbose,
        tokenizer=tokenizer,
    )
    return AuditReport(servers=reports)


async def audit_configs(
    servers: Sequence[ServerConfig],
    *,
    model: str = "openai",
    timeout: float = 15.0,
    verbose: bool = False,
    tokenizer: Tokenizer | None = None,
) -> AuditReport:
    """Audit parsed servers from discovered client configurations."""
    reports = await _audit_configs(
        servers,
        model=model,
        timeout=timeout,
        verbose=verbose,
        tokenizer=tokenizer,
    )
    return AuditReport(servers=reports)


async def _audit_configs(
    servers: Sequence[ServerConfig],
    *,
    model: str,
    timeout: float,
    verbose: bool,
    tokenizer: Tokenizer | None,
) -> list[ServerReport]:
    if model != "openai":
        raise ValueError("Only the openai tokenizer is supported in v0.1.0")
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    reports: list[ServerReport] = []
    for server in servers:
        if server.transport == "http":
            reports.append(
                ServerReport(
                    name=server.name,
                    status="skipped",
                    error="HTTP transport is not supported in v0.1.0",
                    client=server.client,
                    source=server.source,
                )
            )
            continue
        if server.transport != "stdio" or not server.command:
            reports.append(
                ServerReport(
                    name=server.name,
                    status="skipped",
                    error="Unsupported server configuration",
                    client=server.client,
                    source=server.source,
                )
            )
            continue
        report = await audit_server(
            server.command,
            server.args,
            env=dict(server.env),
            cwd=server.cwd,
            name=server.name,
            model=model,
            timeout=timeout,
            verbose=verbose,
            tokenizer=tokenizer,
        )
        report.client = server.client
        report.source = server.source
        reports.append(report)
    return reports


async def _list_all_tools(session: ClientSession) -> list[Any]:
    tools: list[Any] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()
    while True:
        if cursor is None:
            page = await session.list_tools()
        else:
            from mcp.types import PaginatedRequestParams

            page = await session.list_tools(
                params=PaginatedRequestParams(cursor=cursor)
            )
        tools.extend(page.tools)
        cursor = page.next_cursor
        if cursor is None:
            return tools
        if cursor in seen_cursors:
            raise RuntimeError("MCP tools/list returned a repeated pagination cursor")
        seen_cursors.add(cursor)
