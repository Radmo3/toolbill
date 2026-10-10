import asyncio
import json
import os
import sys

from toolbill.audit import audit_config, audit_server


def fake_command(fixture_dir, mode="normal"):
    return sys.executable, [str(fixture_dir / "fake_mcp_server.py"), mode]


async def test_audit_server_follows_all_tools_list_pages(fixture_dir):
    command, args = fake_command(fixture_dir)

    report = await audit_server(command, args, name="fake")

    assert report.status == "ok"
    assert report.tool_count == 2
    assert {tool.name for tool in report.tools} == {"first_tool", "second_tool"}


async def test_server_stderr_is_hidden_unless_verbose(fixture_dir, capsys):
    command, args = fake_command(fixture_dir)

    hidden = await audit_server(command, args)
    assert hidden.status == "ok"
    assert "FAKE STDERR OUTPUT" not in capsys.readouterr().err

    command, args = fake_command(fixture_dir, "verbose")
    shown = await audit_server(command, args, verbose=True)
    assert shown.status == "ok", shown.error
    assert "FAKE STDERR OUTPUT" in capsys.readouterr().err


async def test_hanging_server_returns_timeout_failed_row(fixture_dir):
    command, args = fake_command(fixture_dir, "hang")

    report = await audit_server(command, args, timeout=0.2)

    assert report.status == "failed"
    assert "Timed out" in report.error


async def test_timeout_kills_child_process(fixture_dir, tmp_path):
    pid_file = tmp_path / "child.pid"
    command, args = fake_command(fixture_dir, "hang")
    args.append(str(pid_file))

    report = await audit_server(command, args, timeout=0.5)

    assert report.status == "failed"
    assert pid_file.exists()
    child_pid = int(pid_file.read_text(encoding="ascii"))
    deadline = asyncio.get_running_loop().time() + 2
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError(f"Timed-out MCP child {child_pid} is still running")
        await asyncio.sleep(0.05)


async def test_startup_failure_error_does_not_echo_command_credentials():
    report = await audit_server(
        "missing-token=command-secret",
        ["--api-key", "argument-secret"],
        name="offline",
    )

    assert report.status == "failed"
    assert "command-secret" not in report.error
    assert "argument-secret" not in report.error


async def test_crashing_and_malformed_servers_return_failed_rows(fixture_dir):
    crash_command, crash_args = fake_command(fixture_dir, "crash")
    malformed_command, malformed_args = fake_command(fixture_dir, "malformed")

    crash = await audit_server(crash_command, crash_args, timeout=2)
    malformed = await audit_server(malformed_command, malformed_args, timeout=2)

    assert crash.status == "failed"
    assert malformed.status == "failed"


async def test_http_server_is_reported_as_skipped(tmp_path):
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "remote": {
                        "type": "http",
                        "url": "https://example.com/mcp?api_key=not-for-output",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    report = await audit_config(config)

    assert report["remote"].status == "skipped"
    assert report["remote"].error == "HTTP transport is not supported in v0.1.0"
    assert report.total_tokens == 0


async def test_failed_server_does_not_abort_other_config_servers(
    fixture_dir, tmp_path
):
    hang_command, hang_args = fake_command(fixture_dir, "hang")
    good_command, good_args = fake_command(fixture_dir)
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "slow": {"command": hang_command, "args": hang_args},
                    "good": {"command": good_command, "args": good_args},
                }
            }
        ),
        encoding="utf-8",
    )

    report = await audit_config(config, timeout=1)

    assert [(server.name, server.status) for server in report.servers] == [
        ("good", "ok"),
        ("slow", "failed"),
    ]
    assert report.tool_count == 2
