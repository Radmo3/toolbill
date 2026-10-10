import json

import pytest

from toolbill.discovery import discover_configs, parse_config


@pytest.mark.parametrize(
    ("filename", "client", "server_name"),
    [
        ("claude_desktop.json", "Claude Desktop", "desktop-local"),
        ("claude_code.json", "Claude Code", "code-local"),
        ("cursor.json", "Cursor", "cursor-local"),
        ("vscode_settings.json", "VS Code", "vscode-local"),
    ],
)
def test_client_config_fixtures_parse(fixture_dir, filename, client, server_name):
    parsed = parse_config(fixture_dir / filename, client=client)

    assert parsed[0].client == client
    assert parsed[0].name == server_name
    assert parsed[0].command == "python"
    assert parsed[0].transport == "stdio"


def test_http_servers_are_recognized(fixture_dir):
    servers = parse_config(fixture_dir / "claude_code.json")

    assert servers[1].transport == "http"
    assert servers[1].url == "https://example.com/mcp"


def test_discovery_finds_supported_config_locations(tmp_path, monkeypatch):
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    paths = [
        home / ".claude.json",
        cwd / ".mcp.json",
        home / ".cursor/mcp.json",
        home / ".copilot/mcp-config.json",
        cwd / ".vscode/mcp.json",
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    assert discover_configs(home=home, cwd=cwd, platform="linux") == paths


def test_discovery_finds_vscode_user_profile_config(tmp_path):
    home = tmp_path / "home"
    cwd = tmp_path / "project"
    profile = home / ".config/Code/User/mcp.json"
    profile.parent.mkdir(parents=True)
    profile.write_text('{"servers": {}}', encoding="utf-8")

    assert discover_configs(home=home, cwd=cwd, platform="linux") == [profile]


def test_invalid_config_error_does_not_echo_content(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"token": "do-not-show",', encoding="utf-8")

    with pytest.raises(ValueError) as error:
        parse_config(path)

    assert "do-not-show" not in str(error.value)


def test_sensitive_args_and_url_values_are_redacted(tmp_path):
    config = tmp_path / ".mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "private": {
                        "command": "server",
                        "args": [
                            "--api-key",
                            "argument-secret",
                            "https://example.com/mcp?access_token=url-secret",
                            "PASSWORD=inline-secret",
                        ],
                        "env": {"AUTH_TOKEN": "environment-secret"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    server = parse_config(config)[0]
    from toolbill.cli import _print_dry_run

    # Capture the text so none of the three credential sources can leak.
    import io
    from contextlib import redirect_stdout

    output = io.StringIO()
    with redirect_stdout(output):
        _print_dry_run([server])
    rendered = output.getvalue()
    for secret in ("argument-secret", "url-secret", "inline-secret", "environment-secret"):
        assert secret not in rendered
    assert "[REDACTED]" in rendered


def test_malformed_url_is_fully_redacted():
    from toolbill.discovery import sanitize_url

    assert sanitize_url("https://user:secret@example.com:invalid/path") == "[REDACTED URL]"
