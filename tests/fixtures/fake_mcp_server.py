"""Tiny line-oriented MCP stdio fixture with controllable failure modes."""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def respond(message: dict, result: dict) -> None:
    sys.stdout.write(
        json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n"
    )
    sys.stdout.flush()


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "normal"
    if mode in {"normal", "verbose"}:
        print("FAKE STDERR OUTPUT", file=sys.stderr, flush=True)
    if mode == "crash":
        raise SystemExit(17)
    if mode == "hang":
        if len(sys.argv) > 2:
            Path(sys.argv[2]).write_text(str(os.getpid()), encoding="ascii")
        time.sleep(30)
        return
    if mode == "malformed":
        sys.stdout.write("{not json}\n")
        sys.stdout.flush()
        time.sleep(30)
        return

    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "initialize":
            respond(
                message,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "fake", "version": "1.0"},
                },
            )
        elif method == "tools/list":
            if message.get("params", {}).get("cursor") == "page-2":
                respond(
                    message,
                    {
                        "tools": [
                            {
                                "name": "second_tool",
                                "description": "Second page tool",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"id": {"type": "string"}},
                                },
                            }
                        ]
                    },
                )
            else:
                respond(
                    message,
                    {
                        "tools": [
                            {
                                "name": "first_tool",
                                "description": "First page tool",
                                "inputSchema": {"type": "object"},
                            }
                        ],
                        "nextCursor": "page-2",
                    },
                )


if __name__ == "__main__":
    main()
