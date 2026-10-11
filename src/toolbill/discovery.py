"""MCP client configuration discovery, parsing, and safe display helpers."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class ServerConfig:
    name: str
    client: str
    source: str
    command: str | None = None
    args: tuple[str, ...] = ()
    env: Mapping[str, str] = field(default_factory=dict)
    cwd: str | None = None
    url: str | None = None
    transport: str = "stdio"


def discover_configs(
    *,
    home: Path | None = None,
    cwd: Path | None = None,
    platform: str | None = None,
) -> list[Path]:
    """Return existing supported MCP config paths in stable client order."""
    home = (home or Path.home()).expanduser()
    cwd = (cwd or Path.cwd()).expanduser()
    platform = platform or sys.platform

    if platform == "darwin":
        desktop = home / "Library/Application Support/Claude/claude_desktop_config.json"
    elif platform.startswith("win"):
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        desktop = appdata / "Claude/claude_desktop_config.json"
    else:
        desktop = home / ".config/Claude/claude_desktop_config.json"

    candidates = [
        desktop,
        home / ".claude.json",
        cwd / ".mcp.json",
        home / ".cursor/mcp.json",
        cwd / ".cursor/mcp.json",
        Path(os.environ.get("COPILOT_HOME") or home / ".copilot")
        / "mcp-config.json",
        _vscode_user_config(home, platform),
        cwd / ".vscode/mcp.json",
    ]
    return list(dict.fromkeys(path for path in candidates if path.is_file()))


def parse_config(path: str | Path, *, client: str | None = None) -> list[ServerConfig]:
    """Read a supported JSON MCP config and return its servers."""
    config_path = Path(path).expanduser()
    if config_path.is_dir():
        raise ValueError(
            f"{config_path} is a directory; expected a JSON config file."
        )
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"Could not read MCP config {config_path} ({type(exc).__name__})"
        ) from None
    if not isinstance(raw, dict):
        raise ValueError(f"MCP config {config_path} must contain a JSON object")

    inferred_client = client or _client_for(config_path)
    entries = raw.get("servers", raw.get("mcpServers", {}))
    if not isinstance(entries, dict):
        raise ValueError(f"MCP servers in {config_path} must be a JSON object")

    servers: list[ServerConfig] = []
    for name, entry in entries.items():
        if not isinstance(entry, dict):
            raise ValueError(f"MCP server entry in {config_path} must be an object")
        server_type = str(entry.get("type", "")).lower()
        url = entry.get("url")
        command = entry.get("command")
        if command is not None and not isinstance(command, str):
            raise ValueError(f"MCP server command in {config_path} must be a string")
        if url is not None and not isinstance(url, str):
            raise ValueError(f"MCP server URL in {config_path} must be a string")
        if url is not None or server_type in {"http", "streamable-http", "sse", "ws"}:
            transport = "http"
        elif server_type == "sdk":
            transport = "unsupported"
        else:
            transport = "stdio"

        args_value = entry.get("args", [])
        if not isinstance(args_value, list) or any(
            not isinstance(arg, str) for arg in args_value
        ):
            raise ValueError(f"MCP server args in {config_path} must be an array of strings")
        args = tuple(args_value)
        env_value = entry.get("env", {})
        if not isinstance(env_value, dict):
            raise ValueError(f"MCP server env in {config_path} must be an object")
        if any(
            value is not None and not isinstance(value, (str, int, float, bool))
            for value in env_value.values()
        ):
            raise ValueError(f"MCP server env values in {config_path} must be scalar")
        env = {
            str(key): str(value) for key, value in env_value.items() if value is not None
        }
        cwd_value = entry.get("cwd")
        if cwd_value is not None and not isinstance(cwd_value, str):
            raise ValueError(f"MCP server cwd in {config_path} must be a string")
        servers.append(
            ServerConfig(
                name=name,
                client=inferred_client,
                source=str(config_path),
                command=str(command) if command is not None else None,
                args=args,
                env=env,
                cwd=cwd_value,
                url=str(url) if url is not None else None,
                transport=transport,
            )
        )
    return servers


def sanitize_url(url: str) -> str:
    """Hide URL userinfo and values in credential-like query parameters."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return "[REDACTED URL]"
    if not parts.scheme or not parts.netloc:
        return "[REDACTED URL]"
    hostname = parts.hostname or ""
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    if port is not None:
        hostname = f"{hostname}:{port}"
    path = re.sub(
        r"(?i)/(token|access[_-]?token|api[_-]?key|secret)/[^/]+",
        r"/\1/[REDACTED]",
        parts.path,
    )
    query = [
        (key, "[REDACTED]" if _sensitive_key(key) else value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parts.scheme, hostname, path, urlencode(query), "[REDACTED]" if parts.fragment else "")
    )


def sanitize_argument(argument: str) -> str:
    """Redact credentials embedded in a command-line argument for display."""
    if "://" in argument:
        argument = _replace_urls(argument)
    return _redact_assignments(argument)


def sanitize_arguments(arguments: list[str] | tuple[str, ...]) -> list[str]:
    """Redact values that follow credential flags as well as inline secrets."""
    sanitized: list[str] = []
    redact_next = False
    for argument in arguments:
        if redact_next:
            sanitized.append("[REDACTED]")
            redact_next = False
            continue
        flag = argument.split("=", 1)[0]
        if argument.startswith("--") and _sensitive_key(flag):
            if "=" in argument:
                sanitized.append(sanitize_argument(argument))
            else:
                sanitized.append(argument)
                redact_next = True
            continue
        sanitized.append(sanitize_argument(argument))
    return sanitized


def _client_for(path: Path) -> str:
    text = str(path).lower().replace("\\", "/")
    if "claude_desktop_config.json" in text:
        return "Claude Desktop"
    if path.name == ".claude.json":
        return "Claude Code"
    if path.name == ".mcp.json":
        return "MCP portable"
    if ".cursor/" in text:
        return "Cursor"
    if path.name == "mcp-config.json":
        return "Copilot CLI"
    if ".vscode/" in text:
        return "VS Code"
    return "MCP config"


def _vscode_user_config(home: Path, platform: str) -> Path:
    if platform == "darwin":
        return home / "Library/Application Support/Code/User/mcp.json"
    if platform.startswith("win"):
        appdata = Path(os.environ.get("APPDATA", home / "AppData/Roaming"))
        return appdata / "Code/User/mcp.json"
    return home / ".config/Code/User/mcp.json"


def _sensitive_key(value: str) -> bool:
    return bool(
        re.search(
            r"(token|secret|password|passphrase|api.?key|access.?key|auth|credential|cookie|session.?id|private.?key|signature|(^|[_-])sig(nature)?($|[_-])|(^|[_-])code($|[_-]))",
            value,
            re.I,
        )
    )


def _redact_assignments(value: str) -> str:
    value = re.sub(
        r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]+",
        r"\1 [REDACTED]",
        value,
    )
    value = re.sub(
        r"(?i)\b(api[_-]?key|access[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|session[_-]?id|token|secret|password|passwd|pwd|authorization|auth|cookie|credential|signature|sig|code)(\s*[=:]\s*)([^\s&,;]+)",
        r"\1\2[REDACTED]",
        value,
    )
    value = re.sub(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b",
        "[REDACTED]",
        value,
    )
    value = re.sub(
        r"\b(?:github_pat_|gh[pousr]_)[A-Za-z0-9_]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{20,}\b|\bAIza[A-Za-z0-9_-]{30,}\b",
        "[REDACTED]",
        value,
    )
    return value


def _replace_urls(value: str) -> str:
    return re.sub(r"https?://[^\s\"']+", lambda match: sanitize_url(match.group(0)), value)
