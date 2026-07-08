from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiffResult:
    """Result of diffing code references against documented env files.

    All fields contain env var names as strings. ``undocumented`` and
    ``stale`` are disjoint by construction (each is a one-sided set
    difference of the same two sets). ``missing_values`` is independent of
    both and can overlap with ``stale``, a variable can be simultaneously
    declared with an empty value and unreferenced anywhere in code; both
    facts are worth surfacing rather than merged into one category.
    """

    undocumented: frozenset[str]
    """Keys found in source code but not in any env file."""

    stale: frozenset[str]
    """Keys in env files but not found anywhere in source code."""

    missing_values: frozenset[str]
    """Keys present in env files with an empty value (likely required, no default)."""

    required_missing: frozenset[str] = frozenset()
    """Keys listed in required_keys config that are absent from every env file."""


def diff_keys(
    code_keys: frozenset[str],
    documented_keys: frozenset[str],
    empty_keys: frozenset[str],
) -> DiffResult:
    """Compute the three diff categories from code refs vs env file keys.

    This is a pure function — no side effects, no I/O.

    Args:
        code_keys: All env var names found by scanning source files.
        documented_keys: All keys found in one or more env files.
        empty_keys: Subset of documented_keys whose value is empty string.

    Returns:
        DiffResult with undocumented/stale/missing_values populated.
        required_missing stays at its default (empty). required_keys
        enforcement happens in cli.py, which has the ignore_keys context
        needed to compute it; diff_keys itself has no config access.
    """
    undocumented = code_keys - documented_keys
    stale = documented_keys - code_keys
    # missing_values: present in env files with no value
    # We report all empty keys, regardless of whether they appear in code.
    missing_values = empty_keys

    return DiffResult(
        undocumented=frozenset(undocumented),
        stale=frozenset(stale),
        missing_values=frozenset(missing_values),
    )
