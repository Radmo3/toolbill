"""Command-line interface for toolbill."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Sequence

from toolbill.audit import audit_configs
from toolbill.discovery import (
    ServerConfig,
    discover_configs,
    parse_config,
    sanitize_argument,
    sanitize_arguments,
    sanitize_url,
)
from toolbill.models import AuditReport


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toolbill",
        description="Measure the token cost of MCP server tool definitions.",
    )
    commands = parser.add_subparsers(dest="subcommand", required=True)
    audit = commands.add_parser("audit", help="audit discovered MCP servers")
    audit.add_argument(
        "--config",
        action="append",
        type=Path,
        help="audit a config file instead of discovered client configs (repeatable)",
    )
    audit.add_argument("--timeout", type=float, default=15.0)
    audit.add_argument("--model", choices=("openai",), default="openai")
    audit.add_argument("--dry-run", action="store_true")
    audit.add_argument("--all-tools", action="store_true")
    audit.add_argument("--json", action="store_true", dest="json_output")
    audit.add_argument(
        "--verbose",
        action="store_true",
        help="show MCP server stderr",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    options = parser.parse_args(argv)
    if options.timeout <= 0:
        parser.error("--timeout must be greater than zero")

    paths = options.config or discover_configs()
    servers: list[ServerConfig] = []
    try:
        for path in paths:
            servers.extend(
                parse_config(path, client="config file" if options.config else None)
            )
    except ValueError as exc:
        print(sanitize_argument(str(exc)))
        return 2

    if options.dry_run:
        _print_dry_run(servers)
        return 0

    report = asyncio.run(
        audit_configs(
            servers,
            model=options.model,
            timeout=options.timeout,
            verbose=options.verbose,
        )
    )
    if options.json_output:
        print(json.dumps(_report_as_dict(report), indent=2, ensure_ascii=False))
    else:
        print_report(report, all_tools=options.all_tools)
    return 1 if any(server.status == "failed" for server in report.servers) else 0


def print_report(report: AuditReport, *, all_tools: bool = False) -> None:
    summary_rows: list[list[str]] = []
    for server in report.servers:
        heaviest = server.heaviest(1)
        heaviest_label = (
            f"{heaviest[0].name} ({heaviest[0].tokens:,} tokens)"
            if heaviest
            else "-"
        )
        summary_rows.append(
            [
                sanitize_argument(server.name),
                server.status.upper(),
                f"{server.tool_count:,}",
                f"{server.tokens:,}",
                f"{server.share:.1%}",
                sanitize_argument(heaviest_label),
            ]
        )
        if server.error:
            summary_rows[-1].append(server.error)

    headers = ["SERVER", "STATUS", "TOOLS", "TOKENS", "% OF TOTAL", "HEAVIEST TOOL"]
    if any(len(row) > len(headers) for row in summary_rows):
        headers.append("DETAIL")
    total_tools = [
        (server, tool)
        for server in report.servers
        for tool in server.tools
    ]
    total_heaviest = max(
        (tool for _, tool in total_tools),
        key=lambda tool: tool.tokens,
        default=None,
    )
    summary_rows.append(
        [
            "TOTAL",
            "",
            f"{report.tool_count:,}",
            f"{report.total_tokens:,}",
            "100.0%" if report.total_tokens else "0.0%",
            (
                f"{total_heaviest.name} ({total_heaviest.tokens:,} tokens)"
                if total_heaviest
                else "-"
            ),
        ]
    )
    _print_table(
        headers,
        summary_rows,
        right_align={2, 3, 4},
    )
    print("Counted with o200k_base. This cost is paid on every turn.")
    print()
    tools = sorted(
        total_tools,
        key=lambda item: item[1].tokens,
        reverse=True,
    )
    if not all_tools:
        tools = tools[:10]
    if all_tools:
        print(f"All tools ({len(total_tools)} total)")
    else:
        print(
            f"10 heaviest tools (of {len(total_tools)} total; "
            "use --all-tools to see all)"
        )
    tool_rows = [
        [
            sanitize_argument(server.name),
            sanitize_argument(tool.name),
            f"{tool.tokens:,}",
            f"{tool.breakdown.get('description', 0):,}",
            f"{tool.breakdown.get('schema', 0):,}",
            f"{tool.breakdown.get('annotations', 0):,}",
        ]
        for server, tool in tools
    ]
    _print_table(
        ["SERVER", "TOOL", "TOKENS", "DESCRIPTION", "SCHEMA", "ANNOTATIONS"],
        tool_rows,
        right_align={2, 3, 4, 5},
    )


def _print_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    right_align: set[int],
) -> None:
    widths = [
        max(
            [
                len(headers[index]),
                *(len(row[index]) for row in rows if index < len(row)),
            ]
        )
        for index in range(len(headers))
    ]

    def format_row(row: list[str]) -> str:
        cells = []
        for index, width in enumerate(widths):
            value = row[index] if index < len(row) else ""
            cells.append(value.rjust(width) if index in right_align else value.ljust(width))
        return "  ".join(cells).rstrip()

    print(format_row(headers))
    for row in rows:
        print(format_row(row))


def _report_as_dict(report: AuditReport) -> dict[str, object]:
    return {
        "total_tokens": report.total_tokens,
        "tool_count": report.tool_count,
        "servers": [
            {
                "name": server.name,
                "tokens": server.tokens,
                "tool_count": server.tool_count,
                "share": server.share,
                "status": server.status,
                "error": server.error,
                "client": server.client,
                "source": server.source,
                "tools": [
                    {
                        "name": tool.name,
                        "tokens": tool.tokens,
                        "breakdown": tool.breakdown,
                    }
                    for tool in server.tools
                ],
            }
            for server in report.servers
        ],
    }


def _print_dry_run(servers: Sequence[ServerConfig]) -> None:
    if not servers:
        print("No MCP servers found in supported client configs.")
        return
    print("SERVER                 CLIENT         ACTION    LAUNCH")
    for server in servers:
        name = sanitize_argument(server.name)
        if server.transport == "http":
            action = "SKIP"
            launch = sanitize_url(server.url or "")
        elif server.transport != "stdio" or not server.command:
            action = "SKIP"
            launch = "unsupported configuration"
        else:
            action = "LAUNCH"
            launch = " ".join(
                [sanitize_argument(server.command), *sanitize_arguments(server.args)]
            )
        print(f"{name[:20]:<20} {server.client[:14]:<14} {action:<9} {launch}")


if __name__ == "__main__":
    raise SystemExit(main())
