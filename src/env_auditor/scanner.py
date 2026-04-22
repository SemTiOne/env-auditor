from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from env_auditor.patterns import (
    DOCKERFILE_PATTERN,
    EXTENSION_MAP,
    SHELL_NOISE,
)

# Skip files larger than this (bytes) to avoid memory issues
FILE_SIZE_LIMIT = 1 * 1024 * 1024  # 1 MB

# Maximum line length to scan — protects against ReDoS on pathological input
MAX_LINE_LENGTH = 2000

# Pre-compiled constant — validates that a matched name is a real env var identifier.
# Uppercase only, starts with a letter, digits and underscores allowed.
_VALID_VAR_RE: re.Pattern[str] = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Default directories to always skip
DEFAULT_SKIP_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".env",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        "coverage",
        ".coverage",
    }
)


@dataclass
class Occurrence:
    """A single location where an env var was referenced."""

    file: str
    line: int


@dataclass
class DynamicRef:
    """A dynamic env var reference that cannot be statically audited."""

    file: str
    line: int
    raw: str


@dataclass
class ScanResult:
    """Aggregated result from scanning a directory."""

    # key -> list of occurrences
    references: dict[str, list[Occurrence]] = field(default_factory=dict)
    dynamic_refs: list[DynamicRef] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)

    @property
    def all_keys(self) -> frozenset[str]:
        """All env var names found in source code."""
        return frozenset(self.references.keys())


def scan_directory(
    root: Path,
    extra_exclude: Optional[list[Path]] = None,
) -> ScanResult:
    """Walk *root* recursively and extract all env var references.

    Security guarantees:
    - Symlinks are never followed (followlinks=False).
    - Files over 1 MB are skipped with a warning to stderr.
    - Lines over 2000 characters are skipped (ReDoS protection).
    - No file is imported, eval'd, or executed; all reading is raw text.
    - ``extra_exclude`` paths must be within root (enforced by caller).

    Args:
        root: Resolved absolute path to scan root.
        extra_exclude: Additional resolved absolute paths to exclude.

    Returns:
        ScanResult containing all references and dynamic refs found.
    """
    excluded_names: set[str] = set(DEFAULT_SKIP_DIRS)
    excluded_abs: set[Path] = set()

    if extra_exclude:
        for excl in extra_exclude:
            excluded_names.add(excl.name)
            excluded_abs.add(excl)

    excluded_names.update(_load_gitignore_dirs(root))

    result = ScanResult()

    for dirpath_str, dirnames, filenames in os.walk(str(root), followlinks=False):
        dirpath = Path(dirpath_str)

        # Prune excluded directories in-place so os.walk doesn't descend into them
        dirnames[:] = [
            d
            for d in dirnames
            if d not in excluded_names
            and not _is_symlink(dirpath / d)
            and (dirpath / d) not in excluded_abs
        ]

        for filename in filenames:
            filepath = dirpath / filename

            # Never follow symlinks
            if _is_symlink(filepath):
                continue

            _scan_file(filepath, root, result)

    return result


def _scan_file(filepath: Path, root: Path, result: ScanResult) -> None:
    """Scan a single file and accumulate results into *result*.

    Handles all I/O errors per-file — a single unreadable file never
    aborts the overall scan.

    Args:
        filepath: Absolute path to the file to scan.
        root: Scan root, used to compute relative paths for reporting.
        result: Mutable scan result to accumulate into.
    """
    # Guard: file size
    try:
        size = filepath.stat().st_size
    except OSError:
        return

    if size > FILE_SIZE_LIMIT:
        rel = _rel(filepath, root)
        print(
            f"env-auditor: warning: skipping {rel} (size {size} bytes exceeds 1 MB limit)",
            file=sys.stderr,
        )
        result.skipped_files.append(rel)
        return

    # Guard: applicable patterns exist for this file type
    patterns = _get_patterns(filepath)
    if not patterns:
        return

    # Guard: readable
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
    except (OSError, PermissionError, UnicodeDecodeError) as exc:
        rel = _rel(filepath, root)
        print(f"env-auditor: warning: cannot read {rel}: {exc}", file=sys.stderr)
        result.skipped_files.append(rel)
        return

    rel_path = _rel(filepath, root)
    lines = content.splitlines()

    for lineno, line in enumerate(lines, start=1):
        # ReDoS protection: pathological inputs with very long lines could cause
        # catastrophic backtracking in some regex engines.
        if len(line) > MAX_LINE_LENGTH:
            continue

        for lang_pattern in patterns:
            # Static patterns — extract named env var keys
            for regex in lang_pattern.static_patterns:
                for match in regex.finditer(line):
                    key = match.group(1)
                    if not _VALID_VAR_RE.match(key):
                        continue
                    # Filter well-known shell builtins from shell files
                    if lang_pattern.name == "Shell" and key in SHELL_NOISE:
                        continue
                    result.references.setdefault(key, []).append(
                        Occurrence(file=rel_path, line=lineno)
                    )

            # Dynamic patterns — flag for manual review, cannot statically audit
            for regex in lang_pattern.dynamic_patterns:
                for match in regex.finditer(line):
                    raw = match.group(0).strip()
                    result.dynamic_refs.append(
                        DynamicRef(file=rel_path, line=lineno, raw=raw)
                    )


def _rel(filepath: Path, root: Path) -> str:
    """Return the path of *filepath* relative to *root* as a string."""
    try:
        return str(filepath.relative_to(root))
    except ValueError:
        return str(filepath)


def _get_patterns(filepath: Path):
    """Return applicable LanguagePattern objects for *filepath*, or empty list."""
    name = filepath.name
    if name in ("Dockerfile", "dockerfile") or name.startswith("Dockerfile."):
        return [DOCKERFILE_PATTERN]
    return EXTENSION_MAP.get(filepath.suffix.lower(), [])


def _is_symlink(path: Path) -> bool:
    """Return True if *path* is a symlink. Never raises."""
    try:
        return path.is_symlink()
    except OSError:
        return False


def _load_gitignore_dirs(root: Path) -> set[str]:
    """Parse top-level .gitignore and return simple directory names to skip.

    Best-effort only — handles bare directory names, not globs or negations.

    Args:
        root: Project root containing the .gitignore file.

    Returns:
        Set of simple directory name strings.
    """
    gitignore = root / ".gitignore"
    names: set[str] = set()
    if not gitignore.is_file():
        return names
    try:
        for line in gitignore.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("!"):
                continue
            line = line.rstrip("/")
            if "/" not in line and "*" not in line:
                names.add(line)
    except OSError:
        pass
    return names
