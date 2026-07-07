from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from env_auditor.cli import main


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_project(
    tmp_path: Path,
    code: str = "",
    env_content: str = "",
    code_filename: str = "app.py",
    env_filename: str = ".env.example",
) -> tuple[Path, Path]:
    code_file = tmp_path / code_filename
    code_file.write_text(textwrap.dedent(code), encoding="utf-8")
    env_file = tmp_path / env_filename
    env_file.write_text(textwrap.dedent(env_content), encoding="utf-8")
    return code_file, env_file


# ──────────────────────────────────────────────────────────────────────────────
# Exit codes
# ──────────────────────────────────────────────────────────────────────────────

def test_exit_0_on_clean_project(tmp_path):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["DATABASE_URL"]\n',
        env_content="DATABASE_URL=postgres://localhost/db\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 0


def test_exit_1_on_undocumented_vars(tmp_path):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["UNDOC_KEY"]\n',
        env_content="OTHER_KEY=value\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 1


def test_exit_2_on_bad_args(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["/nonexistent/path/that/does/not/exist"])
    assert exc.value.code == 2


def test_exit_2_on_invalid_path(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path / "not_a_dir.txt")])
    assert exc.value.code == 2


# ──────────────────────────────────────────────────────────────────────────────
# JSON output
# ──────────────────────────────────────────────────────────────────────────────

def test_json_format_valid_json(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["UNDOC_KEY"]\n',
        env_content="OTHER_KEY=value\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
        ])
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "result" in data
    assert "undocumented" in data
    assert "summary" in data


def test_json_format_fail_result(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["UNDOC_KEY"]\n',
        env_content="OTHER_KEY=value\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
        ])
    data = json.loads(capsys.readouterr().out)
    assert data["result"] == "fail"
    keys = [item["key"] for item in data["undocumented"]]
    assert "UNDOC_KEY" in keys


def test_json_format_pass_result(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["DATABASE_URL"]\n',
        env_content="DATABASE_URL=postgres://localhost\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
        ])
    data = json.loads(capsys.readouterr().out)
    assert data["result"] == "pass"
    assert data["undocumented"] == []


def test_json_includes_stale(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
        ])
    data = json.loads(capsys.readouterr().out)
    assert "STALE_KEY" in data["stale"]


def test_json_includes_occurrences(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["UNDOC_KEY"]\n',
        env_content="OTHER=val\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
        ])
    data = json.loads(capsys.readouterr().out)
    item = next(i for i in data["undocumented"] if i["key"] == "UNDOC_KEY")
    assert len(item["occurrences"]) >= 1
    assert "file" in item["occurrences"][0]
    assert "line" in item["occurrences"][0]


# ──────────────────────────────────────────────────────────────────────────────
# --strict flag
# ──────────────────────────────────────────────────────────────────────────────

def test_strict_exits_1_on_stale(tmp_path):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--strict",
        ])
    assert exc.value.code == 1


def test_strict_exits_0_when_clean(tmp_path):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["CLEAN_KEY"]\n',
        env_content="CLEAN_KEY=value\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--strict",
        ])
    assert exc.value.code == 0


def test_no_strict_exits_0_on_stale_only(tmp_path):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
        ])
    assert exc.value.code == 0


# ──────────────────────────────────────────────────────────────────────────────
# --ignore-stale
# ──────────────────────────────────────────────────────────────────────────────

def test_ignore_stale_suppresses_stale_output(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--ignore-stale",
        ])
    out = capsys.readouterr().out
    assert "STALE_KEY" not in out


def test_ignore_stale_json_excludes_stale(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--format", "json",
            "--ignore-stale",
        ])
    data = json.loads(capsys.readouterr().out)
    assert "stale" not in data


# ──────────────────────────────────────────────────────────────────────────────
# --no-color
# ──────────────────────────────────────────────────────────────────────────────

def test_no_color_flag(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["UNDOC_KEY"]\n',
        env_content="OTHER=val\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--no-color",
        ])
    out = capsys.readouterr().out
    assert "\033[" not in out


# ──────────────────────────────────────────────────────────────────────────────
# Default .env.example discovery
# ──────────────────────────────────────────────────────────────────────────────

def test_default_env_example_used(tmp_path):
    (tmp_path / ".env.example").write_text("MY_VAR=value\n", encoding="utf-8")
    (tmp_path / "app.py").write_text('os.environ["MY_VAR"]\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path)])
    assert exc.value.code == 0


# ──────────────────────────────────────────────────────────────────────────────
# Path traversal rejection
# ──────────────────────────────────────────────────────────────────────────────

def test_exclude_path_outside_root_rejected(tmp_path):
    (tmp_path / ".env.example").write_text("", encoding="utf-8")
    (tmp_path / "app.py").write_text("", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--exclude", "/etc",
        ])
    assert exc.value.code == 2


# ──────────────────────────────────────────────────────────────────────────────
# Coverage: reporter color paths and missing-values output
# ──────────────────────────────────────────────────────────────────────────────

def test_text_output_shows_missing_values(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["SECRET_KEY"]\n',
        env_content="SECRET_KEY=\n",
    )
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--env", str(tmp_path / ".env.example"), "--no-color"])
    out = capsys.readouterr().out
    assert "SECRET_KEY" in out


def test_text_output_shows_dynamic_refs(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nval = os.environ[some_key]\n',
        env_content="SOME_KEY=val\n",
    )
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--env", str(tmp_path / ".env.example"), "--no-color"])
    out = capsys.readouterr().out
    assert "dynamic reference" in out


def test_ignore_missing_suppresses_section(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["SECRET_KEY"]\n',
        env_content="SECRET_KEY=\n",
    )
    with pytest.raises(SystemExit):
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--ignore-missing",
            "--no-color",
        ])
    out = capsys.readouterr().out
    assert "no default value" not in out


def test_multiple_env_files(tmp_path):
    (tmp_path / "app.py").write_text('import os\nos.environ["FOO"]\nos.environ["BAR"]\n', encoding="utf-8")
    (tmp_path / "a.env").write_text("FOO=val\n", encoding="utf-8")
    (tmp_path / "b.env").write_text("BAR=val\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / "a.env"),
            "--env", str(tmp_path / "b.env"),
        ])
    assert exc.value.code == 0


# ──────────────────────────────────────────────────────────────────────────────
# Config file integration
# ──────────────────────────────────────────────────────────────────────────────

def test_config_file_strict_via_envcheckrc(tmp_path, capsys):
    """Also verifies the printed text agrees with the exit code, regression
    test for a bug found during review where render_text computed its own
    incomplete 'passed' flag (only checking undocumented/required_missing,
    never --strict + stale), so a stale-only failure under --strict printed
    'Result: PASS' while the process exited 1."""
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    (tmp_path / ".env-auditorrc").write_text("strict = true\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Result: FAIL" in out
    assert "Result: PASS" not in out


def test_strict_stale_only_failure_json_result_matches_exit_code(tmp_path, capsys):
    """Same regression as above, JSON output. A scripted CI consumer trusts
    payload["result"], it must never say "pass" while the process exits 1."""
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    (tmp_path / ".env-auditorrc").write_text(
        'strict = true\nformat = "json"\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "fail"


def test_strict_with_ignore_stale_explains_hidden_failure(tmp_path, capsys):
    """Regression test: --strict + --ignore-stale together previously exited
    1 (correctly) but the stale section was hidden from the report, leaving
    a "Result: FAIL" with zero visible explanation. A note must now explain
    why, in both text and JSON output."""
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--strict", "--ignore-stale",
        ])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "STALE_KEY" not in out  # still suppressed, as --ignore-stale promises
    assert "Result: FAIL" in out
    assert "--ignore-stale" in out  # but the reason is no longer silent

    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--strict", "--ignore-stale", "--format", "json",
        ])
    assert exc.value.code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["result"] == "fail"
    assert "stale" not in payload
    assert "note" in payload


def test_config_file_ignore_keys(tmp_path, capsys):
    make_project(
        tmp_path,
        code='import os\nos.environ["IGNORED_KEY"]\nos.environ["REAL_KEY"]\n',
        env_content="REAL_KEY=val\n",
    )
    (tmp_path / ".env-auditorrc").write_text('ignore_keys = ["IGNORED_KEY"]\n', encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example"), "--no-color"])
    # IGNORED_KEY is suppressed, REAL_KEY is documented -> should pass
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "IGNORED_KEY" not in out


def test_explicit_config_flag(tmp_path):
    """Regression test for Bug 2: --config myconfig.toml must actually be
    read. Uses strict=true + a stale var so the assertion can only pass if
    the config file's content genuinely took effect. A config value equal
    to the default (as the previous version of this test used) would pass
    whether or not --config was honored at all."""
    make_project(
        tmp_path,
        code='import os\nurl = os.environ["USED_KEY"]\n',
        env_content="USED_KEY=val\nSTALE_KEY=old\n",
    )
    cfg_path = tmp_path / "myconfig.toml"
    cfg_path.write_text("strict = true\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--env", str(tmp_path / ".env.example"),
            "--config", str(cfg_path),
        ])
    assert exc.value.code == 1


def test_explicit_config_flag_missing_file(tmp_path):
    make_project(tmp_path, code="", env_content="")
    with pytest.raises(SystemExit) as exc:
        main([
            str(tmp_path),
            "--config", str(tmp_path / "nonexistent.toml"),
        ])
    assert exc.value.code == 2


# ──────────────────────────────────────────────────────────────────────────────
# required_keys enforcement
# ──────────────────────────────────────────────────────────────────────────────

def test_required_keys_missing_fails(tmp_path):
    """Regression test for Bug 3: required_keys was parsed from config but
    never enforced anywhere. A required key absent from every env file must
    now cause exit code 1, even with no code references and no other
    findings at all."""
    make_project(
        tmp_path,
        code="import os\n",
        env_content="OTHER_KEY=val\n",
    )
    (tmp_path / ".env-auditorrc").write_text(
        'required_keys = ["DATABASE_URL", "SECRET_KEY"]\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 1


def test_required_keys_present_passes(tmp_path):
    make_project(
        tmp_path,
        code="import os\n",
        env_content="DATABASE_URL=postgres://localhost/db\n",
    )
    (tmp_path / ".env-auditorrc").write_text(
        'required_keys = ["DATABASE_URL"]\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 0


def test_required_keys_respects_ignore_keys(tmp_path):
    """A required key that's also in ignore_keys must not block a pass.
    Ignore_keys is an explicit, deliberate opt-out."""
    make_project(
        tmp_path,
        code="import os\n",
        env_content="",
    )
    (tmp_path / ".env-auditorrc").write_text(
        'required_keys = ["OPTIONAL_IN_CI"]\n'
        'ignore_keys = ["OPTIONAL_IN_CI"]\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 0


def test_required_keys_shown_in_json_output(tmp_path, capsys):
    make_project(tmp_path, code="import os\n", env_content="")
    (tmp_path / ".env-auditorrc").write_text(
        'required_keys = ["API_KEY"]\nformat = "json"\n', encoding="utf-8"
    )
    with pytest.raises(SystemExit) as exc:
        main([str(tmp_path), "--env", str(tmp_path / ".env.example")])
    assert exc.value.code == 1
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["result"] == "fail"
    assert "API_KEY" in payload["required_missing"]
    assert payload["summary"]["required_missing"] == 1
