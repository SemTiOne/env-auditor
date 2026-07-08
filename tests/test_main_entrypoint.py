"""Tests for the `python -m env_auditor` entry point.

env_auditor/__main__.py is a thin two-line re-export module that is never
imported by any other test (all other tests call env_auditor.cli.main()
directly), so its module-level statements previously showed as 0% covered.
Running it as a real subprocess both closes that coverage gap and more
importantly, is the only test in the suite that verifies `python -m
env_auditor` actually works, since importing env_auditor.cli directly
would not have caught a broken __main__.py (e.g. a typo in its import).
"""
from __future__ import annotations

import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest


def test_dunder_main_runs_in_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Execute __main__.py in-process via runpy so coverage.py can actually
    measure it (a subprocess, as used below, runs outside the coverage
    instrumentation of the test process and would otherwise leave these two
    lines permanently reported as 0% covered)."""
    (tmp_path / "app.py").write_text(
        'import os\nos.environ["DATABASE_URL"]\n', encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text("DATABASE_URL=x\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["env-auditor", str(tmp_path)])

    with pytest.raises(SystemExit) as exc:
        runpy.run_module("env_auditor", run_name="__main__")
    assert exc.value.code == 0


def test_python_dash_m_env_auditor_runs(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(
        'import os\nos.environ["DATABASE_URL"]\n', encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text("DATABASE_URL=x\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-m", "env_auditor", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0
    assert "PASS" in result.stdout


def test_cli_survives_non_utf8_stdout_encoding(tmp_path: Path) -> None:
    """Regression test: on Windows, non-console output (piped, redirected to
    a file, or captured by a CI runner) defaults to the system's legacy
    codepage, commonly cp1252, which cannot encode the Unicode symbols
    (✓ ✗ ⚠ ─) used throughout the report. Without main() forcing UTF-8 on
    sys.stdout/stderr, `print(output)` crashes with UnicodeEncodeError any
    time the tool isn't writing to a real UTF-8-native console.

    This is simulated here via PYTHONIOENCODING rather than requiring an
    actual Windows runner, so it's caught on every platform in CI, not just
    discovered after a Windows-only failure."""
    (tmp_path / "app.py").write_text(
        'import os\nos.environ["DATABASE_URL"]\n', encoding="utf-8"
    )
    (tmp_path / ".env.example").write_text("DATABASE_URL=x\n", encoding="utf-8")

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "cp1252"  # simulate Windows' non-UTF8 default

    result = subprocess.run(
        [sys.executable, "-m", "env_auditor", str(tmp_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, (
        f"crashed under cp1252 stdout encoding — stderr:\n{result.stderr}"
    )
    assert "PASS" in result.stdout
