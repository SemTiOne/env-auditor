from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from env_auditor.config import (
    EnvAuditorConfig,
    _dict_to_config,
    _minimal_toml_parse,
    load_config,
    merge_cli_into_config,
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def write_rc(tmp_path: Path, content: str, name: str = ".env-auditorrc") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ──────────────────────────────────────────────────────────────────────────────
# Default config
# ──────────────────────────────────────────────────────────────────────────────

def test_load_config_no_file_returns_defaults(tmp_path):
    cfg = load_config(tmp_path)
    assert cfg.env_files == [".env.example"]
    assert cfg.ignore_stale is False
    assert cfg.strict is False
    assert cfg.output_format == "text"


# ──────────────────────────────────────────────────────────────────────────────
# .env-auditorrc parsing
# ──────────────────────────────────────────────────────────────────────────────

def test_load_envcheckrc_basic(tmp_path):
    write_rc(tmp_path, """
        strict = true
        ignore_stale = true
        format = "json"
    """)
    cfg = load_config(tmp_path)
    assert cfg.strict is True
    assert cfg.ignore_stale is True
    assert cfg.output_format == "json"


def test_load_envcheckrc_env_files_list(tmp_path):
    write_rc(tmp_path, 'env_files = [".env.example", ".env.staging"]\n')
    cfg = load_config(tmp_path)
    assert ".env.example" in cfg.env_files
    assert ".env.staging" in cfg.env_files


def test_load_envcheckrc_exclude_dirs(tmp_path):
    write_rc(tmp_path, 'exclude_dirs = ["vendor", "third_party"]\n')
    cfg = load_config(tmp_path)
    assert "vendor" in cfg.exclude_dirs
    assert "third_party" in cfg.exclude_dirs


def test_load_envcheckrc_ignore_keys(tmp_path):
    write_rc(tmp_path, 'ignore_keys = ["CI", "HOME"]\n')
    cfg = load_config(tmp_path)
    assert "CI" in cfg.ignore_keys
    assert "HOME" in cfg.ignore_keys


def test_load_envcheckrc_required_keys(tmp_path):
    write_rc(tmp_path, 'required_keys = ["DATABASE_URL", "SECRET_KEY"]\n')
    cfg = load_config(tmp_path)
    assert "DATABASE_URL" in cfg.required_keys


def test_load_envcheckrc_unknown_key_warns(tmp_path, capsys):
    write_rc(tmp_path, 'unknown_option = "whatever"\n')
    load_config(tmp_path)
    err = capsys.readouterr().err
    assert "unknown config key" in err


def test_load_envcheckrc_comments_ignored(tmp_path):
    write_rc(tmp_path, """
        # This is a comment
        strict = true
        # ignore_stale = true
    """)
    cfg = load_config(tmp_path)
    assert cfg.strict is True
    assert cfg.ignore_stale is False


# ──────────────────────────────────────────────────────────────────────────────
# pyproject.toml [tool.env-auditor]
# ──────────────────────────────────────────────────────────────────────────────

def test_load_pyproject_toml_section(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[tool.env-auditor]\nstrict = true\nformat = "json"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert cfg.strict is True
    assert cfg.output_format == "json"


def test_load_pyproject_toml_no_section_returns_defaults(tmp_path):
    p = tmp_path / "pyproject.toml"
    p.write_text('[build-system]\nrequires = ["hatchling"]\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.env_files == [".env.example"]


# ──────────────────────────────────────────────────────────────────────────────
# merge_cli_into_config
# ──────────────────────────────────────────────────────────────────────────────

def test_merge_cli_overrides_env_files():
    cfg = EnvAuditorConfig(env_files=[".env.example"])
    merged = merge_cli_into_config(cfg, env_files=[".env.production"])
    assert merged.env_files == [".env.production"]


def test_merge_cli_strict_flag():
    cfg = EnvAuditorConfig(strict=False)
    merged = merge_cli_into_config(cfg, strict=True)
    assert merged.strict is True


def test_merge_cli_none_does_not_override():
    cfg = EnvAuditorConfig(strict=True)
    merged = merge_cli_into_config(cfg, strict=None)
    assert merged.strict is True


def test_merge_cli_appends_exclude_dirs():
    cfg = EnvAuditorConfig(exclude_dirs=["vendor"])
    merged = merge_cli_into_config(cfg, exclude_dirs=["generated"])
    assert "vendor" in merged.exclude_dirs
    assert "generated" in merged.exclude_dirs


def test_merge_cli_format_override():
    cfg = EnvAuditorConfig(output_format="text")
    merged = merge_cli_into_config(cfg, output_format="json")
    assert merged.output_format == "json"


def test_merge_cli_ignore_stale():
    cfg = EnvAuditorConfig(ignore_stale=False)
    merged = merge_cli_into_config(cfg, ignore_stale=True)
    assert merged.ignore_stale is True


def test_merge_cli_ignore_missing():
    cfg = EnvAuditorConfig(ignore_missing=False)
    merged = merge_cli_into_config(cfg, ignore_missing=True)
    assert merged.ignore_missing is True


# ──────────────────────────────────────────────────────────────────────────────
# _minimal_toml_parse
# ──────────────────────────────────────────────────────────────────────────────

def test_minimal_toml_parse_string(tmp_path):
    p = write_rc(tmp_path, 'format = "json"\n')
    result = _minimal_toml_parse(p)
    assert result["format"] == "json"


def test_minimal_toml_parse_bool_true(tmp_path):
    p = write_rc(tmp_path, "strict = true\n")
    result = _minimal_toml_parse(p)
    assert result["strict"] is True


def test_minimal_toml_parse_bool_false(tmp_path):
    p = write_rc(tmp_path, "ignore_stale = false\n")
    result = _minimal_toml_parse(p)
    assert result["ignore_stale"] is False


def test_minimal_toml_parse_list(tmp_path):
    p = write_rc(tmp_path, 'env_files = [".env.example", ".env.staging"]\n')
    result = _minimal_toml_parse(p)
    assert result["env_files"] == [".env.example", ".env.staging"]


def test_minimal_toml_parse_ignores_comments(tmp_path):
    p = write_rc(tmp_path, "# comment\nstrict = true\n")
    result = _minimal_toml_parse(p)
    assert "strict" in result


def test_minimal_toml_parse_ignores_blank_lines(tmp_path):
    p = write_rc(tmp_path, "\n\nstrict = true\n\n")
    result = _minimal_toml_parse(p)
    assert result["strict"] is True


# ──────────────────────────────────────────────────────────────────────────────
# _dict_to_config
# ──────────────────────────────────────────────────────────────────────────────

def test_dict_to_config_valid(tmp_path):
    p = tmp_path / ".env-auditorrc"
    cfg = _dict_to_config({"strict": True, "output_format": "json"}, p)
    assert cfg.strict is True
    assert cfg.output_format == "json"


def test_dict_to_config_unknown_key_warns(tmp_path, capsys):
    p = tmp_path / ".env-auditorrc"
    _dict_to_config({"nonexistent_key": "value"}, p)
    err = capsys.readouterr().err
    assert "unknown config key" in err


# ──────────────────────────────────────────────────────────────────────────────
# env_auditor.toml filename
# ──────────────────────────────────────────────────────────────────────────────

def test_load_envcheck_toml_filename(tmp_path):
    p = tmp_path / "env-auditor.toml"
    p.write_text('strict = true\n', encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.strict is True
