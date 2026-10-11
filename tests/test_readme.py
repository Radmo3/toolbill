import re
from pathlib import Path

README = Path(__file__).parents[1] / "README.md"
ABSOLUTE = re.compile(r"^(https?://|mailto:|#)")


def _link_targets(text: str) -> list[str]:
    text = re.sub(r"(?ms)^```.*?^```", "", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    inline = re.findall(r"\]\(\s*<?([^)\s>]+)", text)
    reference = re.findall(r"(?m)^\s{0,3}\[[^\]]+\]:\s*<?(\S+?)>?(?:\s|$)", text)
    html = re.findall(r"""(?i)\b(?:href|src)\s*=\s*["']([^"']+)""", text)
    return inline + reference + html


def test_readme_links_are_absolute():
    # PyPI renders the README without the repository, so relative links 404.
    relative = [
        target
        for target in _link_targets(README.read_text(encoding="utf-8"))
        if not ABSOLUTE.match(target)
    ]
    assert relative == [], f"README.md has relative links: {relative}"


def test_link_check_detects_relative_links():
    sample = "[![b](https://x/y.svg)](LICENSE) [a](docs/a.md)\n[ref]: CHANGELOG.md\n"
    assert [t for t in _link_targets(sample) if not ABSOLUTE.match(t)] == [
        "LICENSE",
        "docs/a.md",
        "CHANGELOG.md",
    ]
