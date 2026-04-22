from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# Pre-compiled constants — never constructed from user input.
_VALID_KEY_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class ParsedEnvFile:
    """Result of parsing a single .env-style file.

    Values are held only to detect emptiness.  They are never logged,
    printed, or returned to the caller — only the key names are exposed.
    """

    path: Path
    keys_with_values: dict[str, str] = field(default_factory=dict)

    @property
    def all_keys(self) -> frozenset[str]:
        """All documented key names."""
        return frozenset(self.keys_with_values.keys())

    @property
    def empty_keys(self) -> frozenset[str]:
        """Keys that are present but have an empty value (required, no default)."""
        return frozenset(k for k, v in self.keys_with_values.items() if v == "")


def parse_env_file(path: Path) -> Optional[ParsedEnvFile]:
    """Parse a dotenv-format file and return its keys.

    Sensitive value protection: values are stored only to detect emptiness.
    They are never logged, printed, or exposed outside this module.

    Supported syntax:
    - ``KEY=value`` — key with value
    - ``KEY=`` — key with empty value (flagged as potentially required)
    - ``KEY="quoted value"`` or ``KEY='quoted value'``
    - ``# comment`` — skipped
    - Blank lines — skipped
    - ``KEY=value # inline comment`` — comment stripped
    - ``KEY=first \\`` / continuation lines

    Args:
        path: Absolute path to the env file.

    Returns:
        ParsedEnvFile on success, None if the file cannot be read.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError) as exc:
        print(f"envcheck: warning: cannot read {path}: {exc}", file=sys.stderr)
        return None

    result = ParsedEnvFile(path=path)
    lines = text.splitlines()
    i = 0

    while i < len(lines):
        line = lines[i]

        # Handle backslash line continuation
        while line.endswith("\\") and i + 1 < len(lines):
            line = line[:-1] + lines[i + 1]
            i += 1
        i += 1

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue

        key, _, raw_value = stripped.partition("=")
        key = key.strip()

        if not key or not _VALID_KEY_RE.match(key):
            continue

        # Strip inline comment before quote removal, then strip quotes.
        # Value is stored only for emptiness detection — never exposed.
        value = _strip_quotes(_strip_inline_comment(raw_value))

        # Last-write-wins for duplicate keys (standard dotenv behaviour)
        result.keys_with_values[key] = value

    return result


def parse_env_files(paths: list[Path]) -> ParsedEnvFile:
    """Parse multiple env files and return a merged result (union of all keys).

    For keys that appear in multiple files, the last file's value wins.

    Args:
        paths: Ordered list of env file paths to parse.

    Returns:
        Merged ParsedEnvFile. If *paths* is empty, returns an empty result.
    """
    merged = ParsedEnvFile(path=Path("(merged)"))
    for p in paths:
        parsed = parse_env_file(p)
        if parsed is not None:
            merged.keys_with_values.update(parsed.keys_with_values)
    return merged


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _strip_quotes(value: str) -> str:
    """Remove matching surrounding single or double quotes from *value*."""
    if len(value) >= 2:
        if (value[0] == '"' and value[-1] == '"') or (
            value[0] == "'" and value[-1] == "'"
        ):
            return value[1:-1]
    return value


def _strip_inline_comment(value: str) -> str:
    """Remove a trailing inline comment from an unquoted value.

    Quoted values are returned unchanged — the caller strips quotes first.

    Examples:
        ``foo  # comment`` → ``foo``
        ``"foo # not a comment"`` → ``"foo # not a comment"`` (unchanged)
    """
    if value.startswith('"') or value.startswith("'"):
        return value
    if " #" in value:
        return value[: value.index(" #")].rstrip()
    return value
