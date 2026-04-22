from __future__ import annotations

import argparse
import re
import sys
from dataclasses import replace as dataclass_replace
from pathlib import Path
from typing import Optional

from env_auditor import __version__
from env_auditor.colors import supports_color
from env_auditor.config import (
    EnvCheckConfig,
    _dict_to_config,
    _parse_toml_file,
    load_config,
    merge_cli_into_config,
)
from env_auditor.differ import diff_keys
from env_auditor.parser import parse_env_files
from env_auditor.reporter import render_json, render_text
from env_auditor.scanner import scan_directory


# ──────────────────────────────────────────────────────────────────────────────
# Argument parser
# ──────────────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    """Build and return the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="env-auditor",
        description="Audit environment variable consistency across a codebase.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        default=".",
        help="Root directory to scan. Defaults to current directory.",
    )
    parser.add_argument(
        "--env",
        metavar="FILE",
        action="append",
        dest="env_files",
        default=None,
        help=(
            "Env file(s) to treat as source of truth. "
            "Can be specified multiple times. Default: .env.example"
        ),
    )
    parser.add_argument(
        "--ignore-stale",
        action="store_true",
        default=False,
        help="Do not report stale variables.",
    )
    parser.add_argument(
        "--ignore-missing",
        action="store_true",
        default=False,
        help="Do not report variables with empty values.",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default=None,
        help="Output format. Default: text",
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        default=False,
        help="Disable ANSI color output.",
    )
    parser.add_argument(
        "--exclude",
        metavar="DIR",
        action="append",
        dest="exclude_dirs",
        default=None,
        help=(
            "Additional directories to exclude from scanning. "
            "Can be specified multiple times."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 on stale variables too, not just undocumented ones.",
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        default=None,
        help="Path to config file. Default: auto-discover .env-auditorrc in scan root.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"env-auditor {__version__}",
    )
    parser.add_argument(
        "-h",
        "--help",
        action="help",
        help="Show this message and exit.",
    )
    return parser


# ──────────────────────────────────────────────────────────────────────────────
# Path validation
# ──────────────────────────────────────────────────────────────────────────────

def _resolve_scan_root(raw_path: str) -> Path:
    """Resolve and validate the scan root directory.

    Args:
        raw_path: Raw path string from CLI argument.

    Returns:
        Resolved absolute Path.

    Raises:
        SystemExit(2): If the path does not exist or is not a directory.
    """
    try:
        resolved = Path(raw_path).resolve()
    except (OSError, ValueError) as exc:
        _die(f"Invalid path '{raw_path}': {exc}")
    if not resolved.exists():
        _die(f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        _die(f"Path is not a directory: {resolved}")
    return resolved


def _resolve_env_files(raw_files: list[str], scan_root: Path) -> list[Path]:
    """Resolve and validate env file paths, warning on missing files.

    Args:
        raw_files: Raw file path strings from CLI or config.
        scan_root: Resolved scan root used for relative path resolution.

    Returns:
        List of resolved Paths for files that exist.
    """
    paths: list[Path] = []
    for raw in raw_files:
        p = Path(raw)
        if not p.is_absolute():
            p = scan_root / p
        try:
            resolved = p.resolve()
        except (OSError, ValueError) as exc:
            _die(f"Invalid env file path '{raw}': {exc}")
        if not resolved.exists():
            print(
                f"env-auditor: warning: env file not found: {resolved}",
                file=sys.stderr,
            )
            continue
        if not resolved.is_file():
            _die(f"Env path is not a file: {resolved}")
        paths.append(resolved)
    return paths


def _resolve_exclude_dirs(raw_dirs: list[str], scan_root: Path) -> list[Path]:
    """Resolve --exclude paths, rejecting any that escape the scan root.

    Security: path traversal is rejected — each resolved path must be
    a descendant of scan_root.

    Args:
        raw_dirs: Raw directory strings from CLI or config.
        scan_root: Resolved absolute scan root.

    Returns:
        List of resolved absolute Paths within scan_root.
    """
    resolved_list: list[Path] = []
    for raw in raw_dirs:
        # Strip newlines to prevent any injection via crafted input
        raw_safe = re.sub(r"[\r\n]", "", raw)
        p = Path(raw_safe)
        if not p.is_absolute():
            p = scan_root / p
        try:
            resolved = p.resolve()
        except (OSError, ValueError) as exc:
            _die(f"Invalid exclude path '{raw_safe}': {exc}")
        try:
            resolved.relative_to(scan_root)
        except ValueError:
            _die(
                f"Excluded path '{raw_safe}' resolves to '{resolved}', "
                f"which is outside scan root '{scan_root}'. "
                f"Path traversal rejected."
            )
        resolved_list.append(resolved)
    return resolved_list


def _die(msg: str) -> None:
    """Print an error to stderr and exit with code 2 (tool error)."""
    print(f"env-auditor: error: {msg}", file=sys.stderr)
    sys.exit(2)


# ──────────────────────────────────────────────────────────────────────────────
# Config loading
# ──────────────────────────────────────────────────────────────────────────────

def _build_config(args: argparse.Namespace, scan_root: Path) -> EnvCheckConfig:
    """Load config file and apply CLI overrides on top.

    Config file is auto-discovered in scan_root unless ``--config`` is given.
    CLI flags always win over config file values.

    Args:
        args: Parsed CLI arguments.
        scan_root: Resolved scan root.

    Returns:
        Final merged EnvCheckConfig.
    """
    if args.config:
        config_path = Path(args.config).resolve()
        if not config_path.is_file():
            _die(f"Config file not found: {config_path}")
        try:
            raw = _parse_toml_file(config_path, config_path.name == "pyproject.toml")
            cfg = _dict_to_config(raw or {}, config_path)
        except (OSError, ValueError, KeyError) as exc:
            _die(f"Could not parse config file {config_path}: {exc}")
    else:
        cfg = load_config(scan_root)

    return merge_cli_into_config(
        cfg,
        env_files=args.env_files,
        exclude_dirs=args.exclude_dirs,
        ignore_stale=args.ignore_stale or None,
        ignore_missing=args.ignore_missing or None,
        strict=args.strict or None,
        format=args.format,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Audit pipeline
# ──────────────────────────────────────────────────────────────────────────────

def _run_audit(
    scan_root: Path,
    cfg: EnvCheckConfig,
    use_color: bool,
) -> tuple[int, str]:
    """Execute the full audit pipeline.

    Args:
        scan_root: Resolved absolute path to scan.
        cfg: Merged configuration.
        use_color: Whether to emit ANSI color codes in text output.

    Returns:
        ``(exit_code, rendered_output)`` tuple.
    """
    env_paths = _resolve_env_files(cfg.env_files, scan_root)
    if not env_paths:
        print(
            "env-auditor: warning: no env files found; "
            "all code references will be reported as undocumented.",
            file=sys.stderr,
        )

    extra_exclude: list[Path] = []
    if cfg.exclude_dirs:
        extra_exclude = _resolve_exclude_dirs(cfg.exclude_dirs, scan_root)

    scan_result = scan_directory(scan_root, extra_exclude=extra_exclude or None)
    parsed_env = parse_env_files(env_paths)
    diff = diff_keys(
        code_keys=scan_result.all_keys,
        documented_keys=parsed_env.all_keys,
        empty_keys=parsed_env.empty_keys,
    )

    ignore_keys: set[str] = set(cfg.ignore_keys) if cfg.ignore_keys else set()
    fmt = cfg.format or "text"

    if fmt == "json":
        output = render_json(
            diff,
            scan_result,
            ignore_stale=cfg.ignore_stale,
            ignore_missing=cfg.ignore_missing,
            ignore_keys=ignore_keys,
        )
    else:
        output = render_text(
            diff,
            scan_result,
            use_color=use_color,
            ignore_stale=cfg.ignore_stale,
            ignore_missing=cfg.ignore_missing,
            ignore_keys=ignore_keys,
        )

    effective_undoc = diff.undocumented - ignore_keys
    effective_stale = diff.stale - ignore_keys

    if effective_undoc:
        return 1, output
    if cfg.strict and effective_stale:
        return 1, output
    return 0, output


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def main(argv: Optional[list[str]] = None) -> None:
    """Parse arguments, run the audit, and exit with the appropriate code.

    Exit codes:
        0 — clean (no undocumented vars; no stale with --strict)
        1 — undocumented variables found (or stale with --strict)
        2 — tool error (bad arguments, unreadable config, etc.)
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve color preference before any output.
    # --no-color disables color without mutating os.environ.
    use_color = (not args.no_color) and supports_color()

    scan_root = _resolve_scan_root(args.path)
    cfg = _build_config(args, scan_root)

    exit_code, output = _run_audit(scan_root, cfg, use_color)
    print(output)
    sys.exit(exit_code)
