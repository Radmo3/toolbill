# Changelog

All notable changes to this project are documented in this file. The format
is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- If tiktoken cannot download the `o200k_base` tokenizer file (no network or a
  blocked proxy), `toolbill audit` now prints one line explaining how to fix it
  and exits with status 1 instead of showing a traceback. No servers are
  started. The Python API raises `TokenizerUnavailableError`.

## [0.1.2] - 2026-10-11

### Added

- Project URLs (Homepage, Repository, Issues, Changelog) in package metadata,
  shown in the PyPI sidebar.
- Test that fails if `README.md` contains a relative link.

### Fixed

- README links to `LICENSE`, `CHANGELOG.md`, `CONTRIBUTING.md`,
  `tests/fixtures`, and the license badge are now absolute GitHub URLs. They
  no longer 404 on the PyPI project page.

## [0.1.1] - 2026-10-11

### Added

- "Why" section in the README explaining what toolbill measures and why it
  matters.
- Help text for `--timeout`, `--model`, `--dry-run`, `--all-tools`, and
  `--json` in `toolbill audit --help`.
- `CHANGELOG.md` and `CONTRIBUTING.md`.

### Fixed

- `$COPILOT_HOME/mcp-config.json` (default `~/.copilot/mcp-config.json`) is
  now labeled `Copilot CLI` instead of `VS Code`. That file belongs to GitHub
  Copilot CLI. The label is also correct when `COPILOT_HOME` points to a
  custom directory.
- Error messages say "this release" instead of naming a specific version.

## [0.1.0] - 2026-10-10

### Added

- Initial release: `toolbill audit` CLI and `audit_config` / `audit_server`
  Python API.
- Config discovery for Claude Desktop, Claude Code, Cursor, VS Code, and
  portable `.mcp.json`.
- Per-server and per-tool token counts with description, schema, and
  annotation breakdowns, counted with `o200k_base`.
- `--dry-run`, `--all-tools`, `--json`, `--timeout`, and `--verbose`, with
  credential redaction in displayed output.

[Unreleased]: https://github.com/Radmo3/toolbill/compare/v0.1.2...HEAD
[0.1.2]: https://github.com/Radmo3/toolbill/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/Radmo3/toolbill/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Radmo3/toolbill/releases/tag/v0.1.0
