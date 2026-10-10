import json
import re
import sys

from toolbill.cli import main, print_report
from toolbill.models import AuditReport, ServerReport, ToolReport


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
    assert "config file" in output
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


def _report_with_many_tools():
    tools = [
        ToolReport(name=f"tool_{index}", tokens=100 - index)
        for index in range(12)
    ]
    tools[0] = ToolReport(
        name="a_very_long_tool_name_that_must_not_be_truncated_or_run_into_tokens",
        tokens=100,
    )
    return AuditReport(
        servers=[
            ServerReport(name="server-with-an-unusually-long-name", tools=tools),
        ]
    )


def test_report_tables_align_long_names_and_limit_to_ten_by_default(capsys):
    report = _report_with_many_tools()

    print_report(report)

    output = capsys.readouterr().out
    lines = output.splitlines()
    detail_header_index = next(
        index for index, line in enumerate(lines) if "ANNOTATIONS" in line
    )
    detail_lines = lines[detail_header_index + 1 :]
    assert len(detail_lines) == 10
    assert "a_very_long_tool_name_that_must_not_be_truncated_or_run_into_tokens" in output
    assert "tool_11" not in output
    assert "TOOLTOKENS" not in output
    long_tool_row = next(
        line for line in detail_lines if "a_very_long_tool_name" in line
    )
    assert len(long_tool_row.split()) == 6

    summary_header = lines[0].split()
    total_row = next(line for line in lines if line.startswith("TOTAL"))
    assert summary_header[:5] == ["SERVER", "STATUS", "TOOLS", "TOKENS", "%"]
    assert re.search(r"TOTAL\s+12\s+1,134\s+100\.0%", total_row)


def test_all_tools_displays_full_list(capsys):
    print_report(_report_with_many_tools(), all_tools=True)

    output = capsys.readouterr().out
    lines = output.splitlines()
    detail_header_index = next(
        index for index, line in enumerate(lines) if "ANNOTATIONS" in line
    )
    assert len(lines[detail_header_index + 1 :]) == 12
    assert "tool_11" in output


def test_json_prints_full_report(tmp_path, capsys, fixture_dir):
    config = tmp_path / "mcp.json"
    config.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "healthy": {
                        "command": sys.executable,
                        "args": [str(fixture_dir / "fake_mcp_server.py"), "normal"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["audit", "--config", str(config), "--json"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["total_tokens"] > 0
    assert output["tool_count"] == 2
    assert output["servers"][0]["client"] == "config file"
    assert {tool["name"] for tool in output["servers"][0]["tools"]} == {
        "first_tool",
        "second_tool",
    }


def test_directory_config_has_plain_error(tmp_path, capsys):
    directory = tmp_path / "config-dir"
    directory.mkdir()

    exit_code = main(["audit", "--config", str(directory)])

    assert exit_code == 2
    assert capsys.readouterr().out.strip() == (
        f"{directory} is a directory; expected a JSON config file."
    )
