# Contributing to toolbill

Thanks for your interest in improving toolbill. Bug reports, documentation
fixes, and pull requests are welcome.

## Development setup

```bash
git clone https://github.com/Radmo3/toolbill.git
cd toolbill
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[test]"
pytest
```

toolbill supports Python 3.10 through 3.13. CI runs the test suite on each
of these versions.

## Guidelines

- **Stay read-only.** toolbill only measures. It must never proxy, rewrite,
  or modify a user's MCP configuration or servers.
- **Protect secrets.** Anything shown to the user (dry-run output, error
  messages, tables, JSON) must pass through the redaction helpers in
  `toolbill.discovery`. Never display environment variable values.
- **Cite client config formats.** When adding or changing discovery for an
  MCP client, link the client's official documentation in the README table
  and add a fixture under `tests/fixtures`.
- **Add tests.** New behavior and bug fixes need a test. Tests must not need
  network access; use `tests/fixtures/fake_mcp_server.py` instead of real
  servers.
- **Update the changelog.** Add an entry under an `Unreleased` heading in
  `CHANGELOG.md`.

## Reporting issues

Please include your toolbill version, Python version, operating system, and
the MCP client involved. Run `toolbill audit --dry-run` to see which configs
and servers were discovered. Its output is redacted, but please check it
before posting.

## License

By contributing, you agree that your contributions are licensed under the
[MIT License](LICENSE).
