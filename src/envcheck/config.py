from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace as dataclass_replace
from pathlib import Path
from typing import Optional

# Config file is searched in this order within the scan root.
CONFIG_FILENAMES = (".envcheckrc", "envcheck.toml", "pyproject.toml")

# Key used inside pyproject.toml
PYPROJECT_KEY = "tool.envcheck"


@dataclass
class EnvCheckConfig:
    """Resolved configuration for an envcheck run.

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

    format: str = "text"
    """Output format: 'text' or 'json'."""

    # Allowlist / denylist overrides
    ignore_keys: list[str] = field(default_factory=list)
    """Specific variable names to always ignore in all categories."""

    required_keys: list[str] = field(default_factory=list)
    """Keys that MUST be documented; always flagged if missing."""


def load_config(scan_root: Path) -> EnvCheckConfig:
    """Search for and parse a config file within *scan_root*.

    Looks for ``.envcheckrc``, ``envcheck.toml``, or ``[tool.envcheck]``
    inside ``pyproject.toml``.  Returns default config if none is found.

    Config file format (.envcheckrc / envcheck.toml — TOML):

    .. code-block:: toml

        env_files = [".env.example", ".env.staging"]
        exclude_dirs = ["vendor", "third_party"]
        ignore_stale = false
        ignore_missing = false
        strict = false
        format = "text"
        ignore_keys = ["CI", "HOME"]
        required_keys = ["DATABASE_URL", "SECRET_KEY"]

    Args:
        scan_root: Resolved absolute path to the project root.

    Returns:
        Populated EnvCheckConfig (defaults if no config file found).
    """
    for filename in CONFIG_FILENAMES:
        candidate = scan_root / filename
        if not candidate.is_file():
            continue

        try:
            raw = _parse_toml_file(candidate, filename == "pyproject.toml")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print(
                f"envcheck: warning: could not parse config {candidate}: {exc}",
                file=sys.stderr,
            )
            return EnvCheckConfig()

        if raw is None:
            continue

        return _dict_to_config(raw, candidate)

    return EnvCheckConfig()


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _parse_toml_file(path: Path, is_pyproject: bool) -> Optional[dict]:
    """Parse *path* as TOML and return the envcheck section, or None.

    Uses stdlib ``tomllib`` (Python 3.11+) or ``tomli`` fallback.
    Falls back to a minimal hand-rolled parser for simple .envcheckrc files
    on Python 3.10 without tomli installed.

    Args:
        path: Path to the TOML file.
        is_pyproject: If True, look for ``[tool.envcheck]`` section.

    Returns:
        Dict of config values, or None if the section doesn't exist.
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
            # Fallback: minimal key=value / key = ["list"] parser
            data = _minimal_toml_parse(path)

    if is_pyproject:
        tool = data.get("tool", {})
        section = tool.get("envcheck")
        return section  # None if not present
    else:
        return data or None


def _minimal_toml_parse(path: Path) -> dict:
    """Hand-rolled TOML subset parser for .envcheckrc on Python 3.10.

    Handles:
    - ``key = "string"``
    - ``key = true / false``
    - ``key = ["a", "b"]``
    - Comments (``#``)
    - Blank lines

    Args:
        path: Path to the config file.

    Returns:
        Dict of parsed key/value pairs.
    """
    import re

    result: dict = {}
    text = path.read_text(encoding="utf-8", errors="replace")

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        # Boolean
        if value.lower() == "true":
            result[key] = True
        elif value.lower() == "false":
            result[key] = False
        # List: ["a", "b", "c"]
        elif value.startswith("["):
            items = re.findall(r'"([^"]*)"', value)
            result[key] = items
        # Quoted string
        elif value.startswith('"') and value.endswith('"'):
            result[key] = value[1:-1]
        elif value.startswith("'") and value.endswith("'"):
            result[key] = value[1:-1]
        else:
            result[key] = value

    return result


def _dict_to_config(raw: dict, source: Path) -> EnvCheckConfig:
    """Convert a raw dict from TOML into an EnvCheckConfig.

    Unknown keys are warned about but ignored.

    Args:
        raw: Parsed TOML dict.
        source: Path to the config file (for warning messages).

    Returns:
        EnvCheckConfig populated from *raw*.
    """
    known_keys = {f.name for f in EnvCheckConfig.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    cfg = EnvCheckConfig()

    for key, value in raw.items():
        if key not in known_keys:
            print(
                f"envcheck: warning: unknown config key '{key}' in {source}",
                file=sys.stderr,
            )
            continue

        expected_type = EnvCheckConfig.__dataclass_fields__[key].type  # type: ignore[attr-defined]

        # Coerce types gracefully
        try:
            if "bool" in str(expected_type):
                setattr(cfg, key, bool(value))
            elif "list" in str(expected_type):
                if isinstance(value, list):
                    setattr(cfg, key, [str(v) for v in value])
                elif isinstance(value, str):
                    setattr(cfg, key, [value])
            elif "str" in str(expected_type):
                setattr(cfg, key, str(value))
        except (TypeError, ValueError) as exc:
            print(
                f"envcheck: warning: invalid value for '{key}' in {source}: {exc}",
                file=sys.stderr,
            )

    return cfg


def merge_cli_into_config(
    cfg: EnvCheckConfig,
    *,
    env_files: Optional[list[str]] = None,
    exclude_dirs: Optional[list[str]] = None,
    ignore_stale: Optional[bool] = None,
    ignore_missing: Optional[bool] = None,
    strict: Optional[bool] = None,
    format: Optional[str] = None,
) -> EnvCheckConfig:
    """Apply CLI overrides onto *cfg*, returning a new merged config.

    CLI flags take precedence over config file values.  Only non-None
    arguments override the config.

    Args:
        cfg: Base config loaded from file (or defaults).
        env_files: CLI --env values.
        exclude_dirs: CLI --exclude values.
        ignore_stale: CLI --ignore-stale flag.
        ignore_missing: CLI --ignore-missing flag.
        strict: CLI --strict flag.
        format: CLI --format value.

    Returns:
        New EnvCheckConfig with CLI overrides applied.
    """
    overrides: dict = {}
    if env_files is not None:
        overrides["env_files"] = env_files
    if exclude_dirs is not None:
        overrides["exclude_dirs"] = (cfg.exclude_dirs or []) + exclude_dirs
    if ignore_stale is not None and ignore_stale:
        overrides["ignore_stale"] = True
    if ignore_missing is not None and ignore_missing:
        overrides["ignore_missing"] = True
    if strict is not None and strict:
        overrides["strict"] = True
    if format is not None:
        overrides["format"] = format

    return dataclass_replace(cfg, **overrides)
