from __future__ import annotations

import textwrap
from pathlib import Path

from env_auditor.config import (
    CONFIG_FILE_SIZE_LIMIT,
    EnvAuditorConfig,
    _dict_to_config,
    _minimal_toml_parse,
    _parse_toml_file,
    load_config,
    load_config_from_file,
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
    write_rc(
        tmp_path,
        """
        strict = true
        ignore_stale = true
        format = "json"
    """,
    )
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
    write_rc(
        tmp_path,
        """
        # This is a comment
        strict = true
        # ignore_stale = true
    """,
    )
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


def test_load_pyproject_toml_env_auditor_scalar_does_not_crash(tmp_path, capsys):
    """Regression test: [tool.env-auditor] can be any TOML value, not just a
    table, e.g. `[tool]\\nenv-auditor = "oops"` is valid, unusual TOML.
    Previously this crashed with an uncaught AttributeError ('str' object
    has no attribute 'items') instead of falling back to defaults with a
    warning like every other malformed-config path does."""
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "x"\n\n[tool]\nenv-auditor = "oops, not a table"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)  # must not raise
    assert cfg.strict is False  # defaults
    err = capsys.readouterr().err
    assert "not a table" in err


def test_load_pyproject_toml_tool_scalar_does_not_crash(tmp_path):
    """Same regression, one level up: a top-level `tool = "..."` scalar
    (not a table at all) must also fall back to defaults, not crash."""
    p = tmp_path / "pyproject.toml"
    p.write_text('tool = "oops"\n\n[project]\nname = "x"\n', encoding="utf-8")
    cfg = load_config(tmp_path)  # must not raise
    assert cfg.strict is False


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


def test_minimal_toml_parse_nested_section(tmp_path):
    """Regression test for Bug 1: on Python 3.10 without tomli installed,
    _minimal_toml_parse must build a nested dict from [section.subsection]
    headers so [tool.env-auditor] can be found by _parse_toml_file, instead
    of flattening every section into one shared top-level namespace (which
    made the section undiscoverable and caused load_config to silently
    fall back to defaults)."""
    p = write_rc(
        tmp_path,
        """
        [build-system]
        requires = ["hatchling"]

        [tool.env-auditor]
        strict = true
        format = "json"
        ignore_keys = ["CI", "HOME"]
        """,
        name="pyproject.toml",
    )
    result = _minimal_toml_parse(p)
    assert "tool" in result, "section header did not create a nested dict"
    assert result["tool"]["env-auditor"]["strict"] is True
    assert result["tool"]["env-auditor"]["format"] == "json"
    assert result["tool"]["env-auditor"]["ignore_keys"] == ["CI", "HOME"]
    # build-system's keys must not leak into the top-level namespace
    assert "requires" not in result


def test_parse_toml_file_pyproject_via_fallback_parser(tmp_path, monkeypatch):
    """Integration regression test for Bug 1: force both tomllib and tomli
    imports to fail (simulating Python 3.10 without tomli installed) and
    confirm _parse_toml_file still finds [tool.env-auditor] through the
    fallback parser, rather than returning None and silently defaulting."""
    import builtins

    real_import = builtins.__import__

    def blocking_import(name, *args, **kwargs):
        if name in ("tomllib", "tomli"):
            raise ImportError(f"simulated: {name} unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocking_import)

    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[build-system]\nrequires = ["hatchling"]\n\n'
        '[tool.env-auditor]\nstrict = true\nformat = "json"\n',
        encoding="utf-8",
    )
    result = _parse_toml_file(p, is_pyproject=True)
    assert result is not None
    assert result["strict"] is True
    assert result["format"] == "json"


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


def test_dict_to_config_wrong_type_list_value_warns(tmp_path, capsys):
    """Regression test for Bug 5: a list-typed config key given a value that
    is neither a list nor a string (e.g. a bare bool) must warn on stderr
    and leave the default in place, instead of being silently ignored."""
    p = tmp_path / ".env-auditorrc"
    cfg = _dict_to_config({"ignore_keys": True}, p)
    err = capsys.readouterr().err
    assert "expects a list" in err
    assert cfg.ignore_keys == []  # default untouched


# ──────────────────────────────────────────────────────────────────────────────
# load_config_from_file (explicit --config FILE)
# ──────────────────────────────────────────────────────────────────────────────


def test_load_config_from_file_reads_nonstandard_filename(tmp_path):
    """Regression test for Bug 2: --config myconfig.toml (a name not in
    CONFIG_FILENAMES) must actually be parsed, not silently ignored in favor
    of auto-discovering .env-auditorrc/env-auditor.toml/pyproject.toml in
    the same directory.

    Note on TOML dispatch: whether a file is parsed with [tool.env-auditor]
    section lookup or as flat key=value pairs is decided by filename, same
    as auto-discovery. Only a file literally named pyproject.toml gets
    section lookup; any other name (like this one) is flat-style, matching
    .env-auditorrc conventions."""
    p = tmp_path / "myconfig.toml"
    p.write_text("strict = true\n", encoding="utf-8")
    cfg = load_config_from_file(p)
    assert cfg.strict is True


def test_load_config_from_file_no_section_warns_and_defaults(tmp_path, capsys):
    """A file explicitly named pyproject.toml but lacking [tool.env-auditor]
    must warn and fall back to defaults, same as auto-discovery would."""
    p = tmp_path / "pyproject.toml"
    p.write_text('[build-system]\nrequires = ["hatchling"]\n', encoding="utf-8")
    cfg = load_config_from_file(p)
    err = capsys.readouterr().err
    assert "no [tool.env-auditor] section" in err
    assert cfg.strict is False  # default


def test_load_config_from_file_oversized_warns_and_defaults(tmp_path, capsys):
    p = tmp_path / "myconfig.toml"
    p.write_text(
        "strict = true\n" + "# padding\n" * (CONFIG_FILE_SIZE_LIMIT // 10),
        encoding="utf-8",
    )
    cfg = load_config_from_file(p)
    err = capsys.readouterr().err
    assert "size limit" in err
    assert cfg.strict is False  # oversized file rejected, default used


def test_load_config_from_file_pyproject_named_file(tmp_path):
    """An explicit --config path can itself be named pyproject.toml, in
    which case it must still be read as a [tool.env-auditor] section, not
    as a flat .env-auditorrc-style file."""
    p = tmp_path / "pyproject.toml"
    p.write_text("[tool.env-auditor]\nstrict = true\n", encoding="utf-8")
    cfg = load_config_from_file(p)
    assert cfg.strict is True


# ──────────────────────────────────────────────────────────────────────────────
# env_auditor.toml filename
# ──────────────────────────────────────────────────────────────────────────────


def test_load_envcheck_toml_filename(tmp_path):
    p = tmp_path / "env-auditor.toml"
    p.write_text("strict = true\n", encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.strict is True
