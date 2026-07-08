from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field, replace as dataclass_replace
from pathlib import Path
from typing import Any, Optional

# Config file is searched in this order within the scan root.
CONFIG_FILENAMES = (".env-auditorrc", "env-auditor.toml", "pyproject.toml")

# Maximum config file size — prevents memory exhaustion from a crafted config
CONFIG_FILE_SIZE_LIMIT = 512 * 1024  # 512 KB

# Pre-compiled for _minimal_toml_parse — never constructed from user input
_LIST_ITEMS_RE: re.Pattern[str] = re.compile(r'"([^"]*)"')


@dataclass
class EnvAuditorConfig:
    """Resolved configuration for an env-auditor run.

    CLI flags always override config file values.
    """

    env_files: list[str] = field(default_factory=lambda: [".env.example"])
    """Env files to treat as source of truth."""

    exclude_dirs: list[str] = field(default_factory=list)
    """Additional directories to exclude from scanning."""

    ignore_stale: bool = False
    """If True, stale variables are not reported."""

    ignore_missing: bool = False
    """If True, variables with empty values are not reported."""

    strict: bool = False
    """If True, exit 1 on stale variables too."""

    output_format: str = "text"
    """Output format: 'text' or 'json'. Named to avoid shadowing builtin."""

    ignore_keys: list[str] = field(default_factory=list)
    """Specific variable names to always ignore in all categories."""

    required_keys: list[str] = field(default_factory=list)
    """Keys that MUST be documented; always flagged if missing."""


def load_config(scan_root: Path) -> EnvAuditorConfig:
    """Search for and parse a config file within *scan_root*.

    Looks for ``.env-auditorrc``, ``env-auditor.toml``, or
    ``[tool.env-auditor]`` inside ``pyproject.toml``. Returns default
    config if none is found or if the file exceeds the size limit.

    Args:
        scan_root: Resolved absolute path to the project root.

    Returns:
        Populated EnvAuditorConfig (defaults if no config file found).
    """
    for filename in CONFIG_FILENAMES:
        candidate = scan_root / filename
        if not candidate.is_file():
            continue

        raw, hard_error = _read_config_raw(candidate)
        if hard_error:
            # A candidate that exists but is broken (unreadable, unparseable)
            # stops the search here rather than silently falling through to
            # a different config file the user may not know exists.
            return EnvAuditorConfig()
        if raw is None:
            # File parsed fine but has no env-auditor section for us (e.g. a
            # pyproject.toml without [tool.env-auditor]), keep looking.
            continue

        return _dict_to_config(raw, candidate)

    return EnvAuditorConfig()


def load_config_from_file(path: Path) -> EnvAuditorConfig:
    """Load config from an explicitly specified file path.

    Unlike :func:`load_config`, which auto-discovers config files by name
    within a directory, this function reads exactly the file given,
    regardless of its name.  Used by the ``--config FILE`` CLI flag.

    Args:
        path: Resolved absolute path to the config file.

    Returns:
        Populated EnvAuditorConfig (defaults if the file cannot be parsed).
    """
    raw, _hard_error = _read_config_raw(path)
    if raw is None:
        print(
            f"env-auditor: warning: no [tool.env-auditor] section found in "
            f"{path}, using defaults",
            file=sys.stderr,
        )
        return EnvAuditorConfig()

    return _dict_to_config(raw, path)


def _read_config_raw(path: Path) -> tuple[Optional[dict[str, Any]], bool]:
    """Validate size, parse path as TOML, and return its env-auditor section.

    Shared by :func:`load_config` (auto-discovery) and
    :func:`load_config_from_file` (explicit ``--config``) to avoid duplicating
    the size-limit check and parse-error handling in both places.

    Args:
        path: Path to a config file that is known to exist.

    Returns:
        ``(raw, hard_error)`` where:
        - ``raw`` is the parsed env-auditor section dict, or ``None`` if the
          file parsed cleanly but has no such section (e.g. pyproject.toml
          without ``[tool.env-auditor]``).
        - ``hard_error`` is ``True`` if the file could not be stat'd, exceeded
          the size limit, or failed to parse. Callers should not treat a
          hard error the same as "no section found".
    """
    try:
        size = path.stat().st_size
    except OSError as exc:
        print(
            f"env-auditor: warning: cannot stat config file {path}: {exc}",
            file=sys.stderr,
        )
        return None, True

    if size > CONFIG_FILE_SIZE_LIMIT:
        print(
            f"env-auditor: warning: config file {path} exceeds "
            f"{CONFIG_FILE_SIZE_LIMIT // 1024} KB size limit, using defaults",
            file=sys.stderr,
        )
        return None, True

    try:
        raw = _parse_toml_file(path, is_pyproject=(path.name == "pyproject.toml"))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(
            f"env-auditor: warning: could not parse config {path}: {exc}",
            file=sys.stderr,
        )
        return None, True

    return raw, False


def _parse_toml_file(path: Path, is_pyproject: bool) -> Optional[dict[str, Any]]:
    """Parse *path* as TOML and return the env-auditor section, or None.

    Uses stdlib ``tomllib`` (Python 3.11+) with ``tomli`` fallback,
    then falls back to a minimal hand-rolled parser for Python 3.10
    without tomli installed.

    Args:
        path: Path to the TOML file.
        is_pyproject: If True, look for ``[tool.env-auditor]`` section.

    Returns:
        Dict of config values, or None if the section does not exist.
    """
    try:
        import tomllib  # Python 3.11+
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except ImportError:
            data = _minimal_toml_parse(path)

    if is_pyproject:
        tool = data.get("tool", {})
        if not isinstance(tool, dict):
            # A pyproject.toml with a top-level `tool = "..."` scalar instead
            # of a table is unusual but valid TOML, treat it the same as
            # "no [tool.env-auditor] section" rather than crashing below.
            return None
        section = tool.get("env-auditor")
        if section is not None and not isinstance(section, dict):
            print(
                f"env-auditor: warning: [tool.env-auditor] in {path} is not "
                f"a table (got {type(section).__name__}), using defaults",
                file=sys.stderr,
            )
            return None
        return section
    return data or None


def _minimal_toml_parse(path: Path) -> dict[str, Any]:
    """Hand-rolled TOML subset parser for .env-auditorrc on Python 3.10.

    Handles: string, bool, list of strings, comments, blank lines, and
    nested section headers ([section] / [section.subsection]).  Section
    headers produce a nested dict so that ``[tool.env-auditor]`` values
    end up under ``result["tool"]["env-auditor"]``, matching what the real
    tomllib/tomli parsers return.

    Uses pre-compiled regex — never constructs patterns from user input.

    Args:
        path: Path to the config file.

    Returns:
        Nested dict of parsed key/value pairs.
    """
    result: dict[str, Any] = {}
    current_node: dict[str, Any] = result   # pointer into result at the current section
    text = path.read_text(encoding="utf-8", errors="replace")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("[") and line.endswith("]"):
            section_str = line[1:-1].strip()
            parts = [
                p.strip().strip('"').strip("'")
                for p in section_str.split(".")
            ]
            current_node = result
            for part in parts:
                current_node = current_node.setdefault(part, {})
            continue

        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if value.lower() == "true":
            current_node[key] = True
        elif value.lower() == "false":
            current_node[key] = False
        elif value.startswith("["):
            # Use pre-compiled regex — not constructed from user input
            current_node[key] = _LIST_ITEMS_RE.findall(value)
        elif value.startswith('"') and value.endswith('"'):
            current_node[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            current_node[key] = value[1:-1]
        else:
            current_node[key] = value

    return result


def _dict_to_config(raw: dict[str, Any], source: Path) -> EnvAuditorConfig:
    """Convert a raw dict from TOML into an EnvAuditorConfig.

    Unknown keys are warned about but ignored. Type coercion is strict —
    invalid values are skipped with a warning rather than crashing.

    Args:
        raw: Parsed TOML dict.
        source: Path to the config file (for warning messages).

    Returns:
        EnvAuditorConfig populated from *raw*.
    """
    # Map old key name 'format' to 'output_format' for backwards compat
    if "format" in raw and "output_format" not in raw:
        raw = dict(raw)
        raw["output_format"] = raw.pop("format")

    known_keys = set(EnvAuditorConfig.__dataclass_fields__.keys())
    cfg = EnvAuditorConfig()

    for key, value in raw.items():
        if key not in known_keys:
            print(
                f"env-auditor: warning: unknown config key '{key}' in {source}",
                file=sys.stderr,
            )
            continue

        field_type = str(
            EnvAuditorConfig.__dataclass_fields__[key].type
        )

        try:
            if "bool" in field_type:
                setattr(cfg, key, bool(value))
            elif "list" in field_type:
                if isinstance(value, list):
                    setattr(cfg, key, [str(v) for v in value])
                elif isinstance(value, str):
                    setattr(cfg, key, [value])
                else:
                    print(
                        f"env-auditor: warning: config key '{key}' in {source} "
                        f"expects a list or string, got {type(value).__name__} "
                        f"— ignored",
                        file=sys.stderr,
                    )
            elif "str" in field_type:
                str_value = str(value)
                # Validate output_format against allowed values
                if key == "output_format" and str_value not in ("text", "json"):
                    print(
                        f"env-auditor: warning: invalid output_format '{str_value}' "
                        f"in {source}, using 'text'",
                        file=sys.stderr,
                    )
                    str_value = "text"
                setattr(cfg, key, str_value)
            else:  # pragma: no cover
                # Defensive: every current EnvAuditorConfig field is bool,
                # list[str], or str, so this branch is unreachable today.
                # It exists so that adding a field of a new type in the
                # future fails loudly here instead of silently dropping
                # the user's config value with no trace.
                print(
                    f"env-auditor: warning: config key '{key}' in {source} "
                    f"has unhandled type '{field_type}' — ignored",
                    file=sys.stderr,
                )
        except (TypeError, ValueError) as exc:
            print(
                f"env-auditor: warning: invalid value for '{key}' in {source}: {exc}",
                file=sys.stderr,
            )

    return cfg


def merge_cli_into_config(
    cfg: EnvAuditorConfig,
    *,
    env_files: Optional[list[str]] = None,
    exclude_dirs: Optional[list[str]] = None,
    ignore_stale: Optional[bool] = None,
    ignore_missing: Optional[bool] = None,
    strict: Optional[bool] = None,
    output_format: Optional[str] = None,
) -> EnvAuditorConfig:
    """Apply CLI overrides onto *cfg*, returning a new merged config.

    CLI flags take precedence over config file values. Only non-None
    arguments override the config.

    Args:
        cfg: Base config loaded from file (or defaults).
        env_files: CLI --env values.
        exclude_dirs: CLI --exclude values.
        ignore_stale: CLI --ignore-stale flag.
        ignore_missing: CLI --ignore-missing flag.
        strict: CLI --strict flag.
        output_format: CLI --format value.

    Returns:
        New EnvAuditorConfig with CLI overrides applied.
    """
    overrides: dict[str, Any] = {}
    if env_files is not None:
        overrides["env_files"] = env_files
    if exclude_dirs is not None:
        overrides["exclude_dirs"] = (cfg.exclude_dirs or []) + exclude_dirs
    if ignore_stale:
        overrides["ignore_stale"] = True
    if ignore_missing:
        overrides["ignore_missing"] = True
    if strict:
        overrides["strict"] = True
    if output_format is not None:
        # Validate against allowed values — prevents arbitrary string injection
        if output_format not in ("text", "json"):
            print(
                f"env-auditor: warning: invalid output_format '{output_format}', "
                "using 'text'",
                file=sys.stderr,
            )
            output_format = "text"
        overrides["output_format"] = output_format

    return dataclass_replace(cfg, **overrides)
