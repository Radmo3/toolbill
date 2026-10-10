"""Command-line interface for toolbill."""

from __future__ import annotations

import argparse
import asyncio
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
            servers.extend(parse_config(path))
    except ValueError as exc:
        print(f"toolbill: {sanitize_argument(str(exc))}")
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
    print_report(report)
    return 1 if any(server.status == "failed" for server in report.servers) else 0


def print_report(report: AuditReport) -> None:
    print("SERVER                 STATUS    TOOLS      TOKENS")
    for server in report.servers:
        print(
            f"{sanitize_argument(server.name)[:20]:<20} {server.status.upper():<9} "
            f"{server.tool_count:>5} {server.tokens:>10,}"
        )
        if server.error:
            print(f"  {server.error}")
    print("-" * 53)
    print(f"TOTAL                                  {report.total_tokens:>10,}")
    print()
    print(
        "SERVER                 TOOL                          TOKENS "
        "DESCRIPTION  SCHEMA  ANNOTATIONS"
    )
    for server in report.servers:
        for tool in server.tools:
            breakdown = tool.breakdown
            print(
                f"{sanitize_argument(server.name)[:20]:<20} "
                f"{sanitize_argument(tool.name)[:28]:<28} "
                f"{tool.tokens:>7,} "
                f"{breakdown.get('description', 0):>11,} "
                f"{breakdown.get('schema', 0):>7,} "
                f"{breakdown.get('annotations', 0):>11,}"
            )


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
