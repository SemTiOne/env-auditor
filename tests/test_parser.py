from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from env_auditor.parser import parse_env_file, parse_env_files, ParsedEnvFile


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def write_env(tmp_path: Path, content: str, name: str = ".env.example") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Basic parsing
# ──────────────────────────────────────────────────────────────────────────────

def test_simple_key_value(tmp_path):
    p = write_env(tmp_path, "FOO=bar\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.keys_with_values["FOO"] == "bar"


def test_empty_value(tmp_path):
    p = write_env(tmp_path, "EMPTY_KEY=\n")
    result = parse_env_file(p)
    assert result is not None
    assert "EMPTY_KEY" in result.all_keys
    assert "EMPTY_KEY" in result.empty_keys
    assert result.keys_with_values["EMPTY_KEY"] == ""


def test_comment_lines_skipped(tmp_path):
    p = write_env(tmp_path, "# This is a comment\nFOO=bar\n")
    result = parse_env_file(p)
    assert result is not None
    assert "FOO" in result.all_keys
    assert len(result.all_keys) == 1


def test_blank_lines_skipped(tmp_path):
    p = write_env(tmp_path, "\n\nFOO=bar\n\n")
    result = parse_env_file(p)
    assert result is not None
    assert len(result.all_keys) == 1


def test_quoted_double(tmp_path):
    p = write_env(tmp_path, 'FOO="hello world"\n')
    result = parse_env_file(p)
    assert result is not None
    assert result.keys_with_values["FOO"] == "hello world"


def test_quoted_single(tmp_path):
    p = write_env(tmp_path, "FOO='hello world'\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.keys_with_values["FOO"] == "hello world"


def test_multiline_backslash(tmp_path):
    p = write_env(tmp_path, "FOO=first \\\n  second\n")
    result = parse_env_file(p)
    assert result is not None
    assert "FOO" in result.all_keys


def test_duplicate_keys_last_wins(tmp_path):
    p = write_env(tmp_path, "FOO=first\nFOO=last\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.keys_with_values["FOO"] == "last"


def test_windows_line_endings(tmp_path):
    p = tmp_path / "win.env"
    p.write_bytes(b"WIN_KEY=win_value\r\nWIN_EMPTY=\r\n")
    result = parse_env_file(p)
    assert result is not None
    assert "WIN_KEY" in result.all_keys
    assert "WIN_EMPTY" in result.empty_keys


def test_inline_comment_stripped(tmp_path):
    p = write_env(tmp_path, "FOO=bar # inline comment\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.keys_with_values["FOO"] == "bar"


def test_invalid_key_skipped(tmp_path):
    p = write_env(tmp_path, "123INVALID=value\nVALID=yes\n")
    result = parse_env_file(p)
    assert result is not None
    assert "VALID" in result.all_keys
    assert "123INVALID" not in result.all_keys


def test_unreadable_file_returns_none(tmp_path):
    import os
    import sys
    if sys.platform == "win32":
        pytest.skip("chmod file locking not reliable on Windows")
    if hasattr(os, "getuid") and os.getuid() == 0:
        pytest.skip("chmod restrictions do not apply to root")
    p = tmp_path / "noread.env"
    p.write_text("FOO=bar", encoding="utf-8")
    p.chmod(0o000)
    try:
        result = parse_env_file(p)
        assert result is None
    finally:
        p.chmod(0o644)


# ──────────────────────────────────────────────────────────────────────────────
# Multi-file merge
# ──────────────────────────────────────────────────────────────────────────────

def test_merge_two_files(tmp_path):
    p1 = write_env(tmp_path, "FOO=foo\n", "a.env")
    p2 = write_env(tmp_path, "BAR=bar\n", "b.env")
    merged = parse_env_files([p1, p2])
    assert "FOO" in merged.all_keys
    assert "BAR" in merged.all_keys


def test_merge_last_file_wins_on_duplicate(tmp_path):
    p1 = write_env(tmp_path, "FOO=first\n", "a.env")
    p2 = write_env(tmp_path, "FOO=second\n", "b.env")
    merged = parse_env_files([p1, p2])
    assert merged.keys_with_values["FOO"] == "second"


def test_merge_empty_list(tmp_path):
    merged = parse_env_files([])
    assert len(merged.all_keys) == 0


def test_all_keys_property(tmp_path):
    p = write_env(tmp_path, "FOO=bar\nBAZ=\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.all_keys == frozenset({"FOO", "BAZ"})


def test_empty_keys_property(tmp_path):
    p = write_env(tmp_path, "FOO=bar\nBAZ=\nQUX=\n")
    result = parse_env_file(p)
    assert result is not None
    assert result.empty_keys == frozenset({"BAZ", "QUX"})
