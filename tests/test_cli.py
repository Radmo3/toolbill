import json
import sys

from toolbill.cli import main


def test_dry_run_lists_servers_without_starting_them(tmp_path, capsys):
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "local": {
                        "command": sys.executable,
                        "args": ["-c", "raise SystemExit(3)"],
                    },
                    "remote": {
                        "type": "http",
                        "url": "https://user:secret@example.com/mcp?api_key=abc",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["audit", "--config", str(config), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "local" in output
    assert "LAUNCH" in output
    assert "remote" in output
    assert "SKIP" in output
    for secret in ("secret", "abc"):
        assert secret not in output


def test_cli_audit_prints_failed_row_then_success(tmp_path, capsys, fixture_dir):
    config = tmp_path / "mcp.json"
    fake_server = fixture_dir / "fake_mcp_server.py"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "command": sys.executable,
                        "args": [str(fake_server), "crash"],
                    },
                    "healthy": {
                        "command": sys.executable,
                        "args": [str(fake_server), "normal"],
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["audit", "--config", str(config), "--timeout", "2"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "broken" in output
    assert "healthy" in output
    assert "first_tool" in output
