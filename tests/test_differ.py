from __future__ import annotations

import pytest

from env_auditor.differ import diff_keys, DiffResult


def test_undocumented_keys():
    code = frozenset({"FOO", "BAR", "UNDOC"})
    documented = frozenset({"FOO", "BAR"})
    empty = frozenset()
    result = diff_keys(code, documented, empty)
    assert result.undocumented == frozenset({"UNDOC"})
    assert result.stale == frozenset()


def test_stale_keys():
    code = frozenset({"FOO"})
    documented = frozenset({"FOO", "STALE_KEY"})
    empty = frozenset()
    result = diff_keys(code, documented, empty)
    assert result.stale == frozenset({"STALE_KEY"})
    assert result.undocumented == frozenset()


def test_missing_values():
    code = frozenset({"FOO", "SECRET"})
    documented = frozenset({"FOO", "SECRET"})
    empty = frozenset({"SECRET"})
    result = diff_keys(code, documented, empty)
    assert result.missing_values == frozenset({"SECRET"})


def test_all_three_categories():
    code = frozenset({"FOO", "UNDOC"})
    documented = frozenset({"FOO", "STALE"})
    empty = frozenset({"FOO"})
    result = diff_keys(code, documented, empty)
    assert result.undocumented == frozenset({"UNDOC"})
    assert result.stale == frozenset({"STALE"})
    assert result.missing_values == frozenset({"FOO"})


def test_empty_inputs():
    result = diff_keys(frozenset(), frozenset(), frozenset())
    assert result.undocumented == frozenset()
    assert result.stale == frozenset()
    assert result.missing_values == frozenset()


def test_identical_sets():
    keys = frozenset({"FOO", "BAR", "BAZ"})
    result = diff_keys(keys, keys, frozenset())
    assert result.undocumented == frozenset()
    assert result.stale == frozenset()


def test_all_undocumented():
    code = frozenset({"A", "B", "C"})
    result = diff_keys(code, frozenset(), frozenset())
    assert result.undocumented == code
    assert result.stale == frozenset()


def test_all_stale():
    documented = frozenset({"X", "Y", "Z"})
    result = diff_keys(frozenset(), documented, frozenset())
    assert result.stale == documented
    assert result.undocumented == frozenset()


def test_missing_values_independent_of_code_presence():
    """Empty keys in env files are reported even if not referenced in code."""
    code = frozenset({"FOO"})
    documented = frozenset({"FOO", "ORPHAN_EMPTY"})
    empty = frozenset({"ORPHAN_EMPTY"})
    result = diff_keys(code, documented, empty)
    assert "ORPHAN_EMPTY" in result.missing_values


def test_returns_frozensets():
    result = diff_keys(frozenset({"A"}), frozenset({"B"}), frozenset())
    assert isinstance(result.undocumented, frozenset)
    assert isinstance(result.stale, frozenset)
    assert isinstance(result.missing_values, frozenset)


# ──────────────────────────────────────────────────────────────────────────────
# Reporter ignore_keys integration
# ──────────────────────────────────────────────────────────────────────────────

def test_ignore_keys_removes_from_undocumented():
    from env_auditor.differ import diff_keys
    from env_auditor.scanner import ScanResult
    from env_auditor.reporter import render_text, render_json
    import json

    code = frozenset({"FOO", "IGNORED"})
    documented = frozenset({"FOO"})
    diff = diff_keys(code, documented, frozenset())
    scan = ScanResult()

    text = render_text(diff, scan, use_color=False, ignore_keys={"IGNORED"})
    assert "IGNORED" not in text
    assert "No undocumented" in text

    data = json.loads(render_json(diff, scan, ignore_keys={"IGNORED"}))
    assert data["result"] == "pass"
    assert all(item["key"] != "IGNORED" for item in data["undocumented"])


def test_ignore_keys_removes_from_stale():
    from env_auditor.differ import diff_keys
    from env_auditor.scanner import ScanResult
    from env_auditor.reporter import render_text

    code = frozenset({"FOO"})
    documented = frozenset({"FOO", "STALE_BUT_IGNORED"})
    diff = diff_keys(code, documented, frozenset())
    scan = ScanResult()

    text = render_text(diff, scan, use_color=False, ignore_keys={"STALE_BUT_IGNORED"})
    assert "STALE_BUT_IGNORED" not in text
