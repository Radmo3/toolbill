# toolbill

**Measure the token cost of MCP tool definitions before they enter a model's
context window.**

[![PyPI](https://img.shields.io/pypi/v/toolbill.svg)](https://pypi.org/project/toolbill/)
[![CI](https://github.com/Radmo3/toolbill/actions/workflows/ci.yml/badge.svg)](https://github.com/Radmo3/toolbill/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/toolbill.svg)](https://pypi.org/project/toolbill/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

`toolbill` is a read-only Python CLI and library for auditing MCP server tool
definitions. It discovers supported local client configurations, starts local
stdio servers, calls `tools/list`, and reports total and per-tool token counts.

## Install and run

```bash
python -m pip install toolbill
toolbill audit
```

By default, `audit` discovers MCP configs for Claude Desktop, Claude Code,
Cursor, and VS Code, and starts their configured stdio servers. The official
[`mcp` Python SDK](https://github.com/modelcontextprotocol/python-sdk) handles
the stdio connection and MCP protocol.

Example audit summary:

```text
SERVER               STATUS  TOOLS  TOKENS  % OF TOTAL  HEAVIEST TOOL
filesystem           OK         14   2,852       35.7%  read_media_file (294 tokens)
memory               OK          9   2,408       30.1%  search_nodes (327 tokens)
everything           OK         13   1,729       21.6%  gzip-file-as-resource (249 tokens)
sequential-thinking  OK          1   1,005       12.6%  sequentialthinking (1,005 tokens)
TOTAL                           37   7,994      100.0%  sequentialthinking (1,005 tokens)
```

Measured on 2026-10-10 against the latest published versions of the four
official reference servers. Run the command yourself to reproduce:

```bash
toolbill audit --config examples/reference-servers.json --timeout 60
```

Use `--dry-run` to see which servers would be launched without running them.
HTTP servers are listed as `SKIP`; HTTP transport is not supported in this
release. Command arguments and URL credentials are redacted in dry-run output.
Environment variable values are never displayed.

Each server has a 15-second timeout by default. Change it with
`--timeout SECONDS`. A server that fails to launch, initialize, times out, or
fails to list tools gets a `FAILED` row; the audit continues with other
servers. Server stderr is suppressed unless `--verbose` is passed. Failed
servers make the CLI exit with status 1.

The summary includes each server's share of total tokens and its heaviest
tool. The tool table shows the 10 heaviest tools overall by default. Use
`--all-tools` to show every tool, or `--json` to print the full report (all
servers and tools) as JSON:

```bash
toolbill audit --all-tools
toolbill audit --json
```

To audit a specific config file instead of the discovered configs:

```bash
toolbill audit --config ~/.cursor/mcp.json
toolbill audit --config .mcp.json --timeout 30
```

## Python API

```python
import asyncio
from toolbill import audit_config, audit_server

async def main():
    report = await audit_config("~/.cursor/mcp.json")
    print(f"{report.total_tokens:,} tokens across {report.tool_count} tools")

    for server in report.servers:  # sorted, heaviest first
        print(f"{server.name:<16} {server.tokens:>7,} ({server.share:.1%})")
        for tool in server.heaviest(5):
            print(tool.name, tool.tokens, tool.breakdown)

    filesystem = await audit_server(
        command="python",
        args=["my_mcp_server.py"],
        timeout=15,
    )
    print(filesystem.tokens, filesystem.status)

asyncio.run(main())
```

`audit_config(path, *, model="openai", timeout=15, verbose=False,
tokenizer=None)` returns an `AuditReport`. `audit_server(command, args=None,
*, env=None, cwd=None, name=None, model="openai", timeout=15, verbose=False,
tokenizer=None)` returns a `ServerReport`. The first release supports the
`openai` model option and uses `tiktoken`'s `o200k_base` encoding. Pass an
object implementing `count(text: str) -> int` as `tokenizer` to use a
compatible custom counter.

Reports expose `total_tokens`, `tool_count`, `servers`, and lookup by server
name (`report["github"]`). Each server has `name`, `tokens`, `tool_count`,
`share`, `status`, `tools`, and `heaviest(n)`. A tool has `name`, `tokens`,
and a breakdown for description, schema, and annotations. Failed/skipped
servers have a safe summary in `error` and contribute no tokens.

## Tokenization details

For each MCP `Tool` returned by `tools/list`, `toolbill` first converts the
SDK object to its protocol-field JSON object, omitting absent and null fields.
It tokenizes the complete tool definition as compact UTF-8 JSON: recursively
sorted object keys, no insignificant whitespace, and non-ASCII characters
preserved. No client-specific wrapper or provider framing is added.

Breakdown counts are measured independently: description is counted as its
plain text; schema is the compact JSON object containing `inputSchema` and/or
`outputSchema`; annotations are counted as their compact JSON value. These
field counts do not necessarily sum to the complete definition's token count.

`tools/list` pagination is followed until the server returns no cursor, so
each listed tool is counted. Counting measures the tool definitions only;
provider framing overhead is not included.

## Configuration discovery and safety

The config fixtures in [tests/fixtures](tests/fixtures) follow the documented
formats for each supported client:

| Client | Config format and discovery locations | Current reference |
|---|---|---|
| Claude Desktop | `mcpServers`; platform config (`claude_desktop_config.json`) | [Local MCP servers](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop) |
| Claude Code | `mcpServers`; `~/.claude.json` | [MCP reference](https://code.claude.com/docs/en/mcp) |
| Cursor | `mcpServers`; `~/.cursor/mcp.json` and project `.cursor/mcp.json` | [Cursor MCP docs — configuration format and locations](https://cursor.com/docs/mcp) |
| VS Code | `servers`; `$COPILOT_HOME/mcp-config.json` (default `~/.copilot/mcp-config.json`), user profile `mcp.json`, and workspace `.vscode/mcp.json` | [Configuration reference](https://code.visualstudio.com/docs/agents/reference/mcp-configuration) |

The portable workspace `.mcp.json` format (`mcpServers`) is also discovered
once and labeled `MCP portable`, since more than one client can read it.

MCP servers are executable programs. Review a server configuration before
auditing it. `--dry-run` never starts a server; it omits environment values and
redacts credential-looking argument and URL values. The same redaction applies
to error output. Server stderr remains hidden by default; `--verbose` displays
it, which may reveal whatever the server itself writes there.

## Development

```bash
python -m pip install -e ".[test]"
pytest
```

The GitHub Actions workflow runs the test suite on supported Python versions.

## License

MIT. See [LICENSE](LICENSE).
