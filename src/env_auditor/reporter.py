from __future__ import annotations

import json
from typing import Any

from env_auditor.colors import get_colors
from env_auditor.differ import DiffResult
from env_auditor.scanner import ScanResult


def render_text(
    diff: DiffResult,
    scan: ScanResult,
    *,
    passed: bool,
    use_color: bool = True,
    ignore_stale: bool = False,
    ignore_missing: bool = False,
    ignore_keys: set[str] | None = None,
) -> str:
    """Render a human-readable audit report.

    Args:
        passed: The final pass/fail verdict, computed by the caller (which
            has access to --strict and all effective-set logic). This is
            passed in rather than recomputed here so the displayed
            "Result: PASS/FAIL" can never disagree with the process's
            actual exit code. Previously this function computed its own
            (incomplete) notion of "passed" that ignored --strict entirely,
            so a stale-only failure under --strict displayed "Result: PASS"
            while the process exited 1.
    """
    c = get_colors(use_color)
    ignore_keys = ignore_keys or set()
    lines: list[str] = []
    sep = "─" * 42

    lines.append(f"{c.BOLD}env-auditor{c.RESET} — environment variable audit")
    lines.append(sep)
    lines.append("")

    undoc = sorted(diff.undocumented - ignore_keys)
    req_missing = sorted(diff.required_missing)

    if undoc:
        lines.append(
            f"{c.RED}✗  {len(undoc)} undocumented variable{'s' if len(undoc) != 1 else ''}"
            f" (in code, missing from .env.example){c.RESET}"
        )
        for key in undoc:
            occurrences = scan.references.get(key, [])
            occ_str = ", ".join(f"{o.file}:{o.line}" for o in occurrences[:5])
            if len(occurrences) > 5:
                occ_str += f" (+{len(occurrences) - 5} more)"
            lines.append(f"   {c.BOLD}{key:<30}{c.RESET} {c.DIM}{occ_str}{c.RESET}")
        lines.append("")
    else:
        lines.append(f"{c.GREEN}✓  No undocumented variables{c.RESET}")
        lines.append("")

    if req_missing:
        lines.append(
            f"{c.RED}✗  {len(req_missing)} required variable{'s' if len(req_missing) != 1 else ''}"
            f" missing from env file (required_keys){c.RESET}"
        )
        for key in req_missing:
            lines.append(f"   {c.BOLD}{key}{c.RESET}")
        lines.append("")

    if not ignore_stale:
        stale = sorted(diff.stale - ignore_keys)
        if stale:
            lines.append(
                f"{c.YELLOW}⚠  {len(stale)} stale variable{'s' if len(stale) != 1 else ''}"
                f" (in .env.example, not found in code){c.RESET}"
            )
            for key in stale:
                lines.append(f"   {key}")
            lines.append("")

    if not ignore_missing:
        missing = sorted(diff.missing_values - ignore_keys)
        if missing:
            lines.append(
                f"○  {len(missing)} variable{'s' if len(missing) != 1 else ''} with no"
                f" default value (empty in .env.example)"
            )
            for key in missing:
                lines.append(f"   {key}")
            lines.append("")

    if scan.dynamic_refs:
        n_dyn = len(scan.dynamic_refs)
        lines.append(
            f"{c.CYAN}⚡  {n_dyn} dynamic reference{'s' if n_dyn != 1 else ''}"
            f" (runtime key construction — cannot audit statically){c.RESET}"
        )
        for ref in scan.dynamic_refs:
            lines.append(f"   {c.DIM}{ref.file}:{ref.line}{c.RESET}  →  {ref.raw}")
        lines.append("")

    lines.append(sep)

    result_label = f"{c.GREEN}PASS{c.RESET}" if passed else f"{c.RED}FAIL{c.RESET}"
    exit_note = "" if passed else "  (exit code 1)"
    lines.append(f"Result: {result_label}{exit_note}")

    if not passed and not undoc and not req_missing and ignore_stale:
        # The only other failure condition (--strict + stale vars) is true,
        # but --ignore-stale hid the stale section above. Without this note
        # the report would show FAIL with no visible reason at all.
        lines.append(
            f"{c.DIM}(failed due to stale variables under --strict;"
            f" rerun without --ignore-stale to see them){c.RESET}"
        )

    return "\n".join(lines)


def render_json(
    diff: DiffResult,
    scan: ScanResult,
    *,
    passed: bool,
    ignore_stale: bool = False,
    ignore_missing: bool = False,
    ignore_keys: set[str] | None = None,
) -> str:
    """Render a machine-readable JSON audit report.

    Args:
        passed: See render_text, the caller-computed pass/fail verdict,
            kept as the single source of truth shared with the exit code.
    """
    ignore_keys = ignore_keys or set()
    undoc = sorted(diff.undocumented - ignore_keys)
    req_missing = sorted(diff.required_missing)

    undocumented_list = [
        {
            "key": key,
            "occurrences": [
                {"file": o.file, "line": o.line} for o in scan.references.get(key, [])
            ],
        }
        for key in undoc
    ]

    dynamic_list = [
        {"file": r.file, "line": r.line, "raw": r.raw} for r in scan.dynamic_refs
    ]

    payload: dict[str, Any] = {
        "result": "pass" if passed else "fail",
        "summary": {
            "undocumented": len(undoc),
            "required_missing": len(req_missing),
            "stale": len(diff.stale - ignore_keys) if not ignore_stale else 0,
            "missing_values": len(diff.missing_values - ignore_keys)
            if not ignore_missing
            else 0,
            "dynamic_refs": len(scan.dynamic_refs),
        },
        "undocumented": undocumented_list,
        "required_missing": req_missing,
    }

    if not ignore_stale:
        payload["stale"] = sorted(diff.stale - ignore_keys)
    if not ignore_missing:
        payload["missing_values"] = sorted(diff.missing_values - ignore_keys)

    if not passed and not undoc and not req_missing and ignore_stale:
        payload["note"] = (
            "Failed due to stale variables under --strict; rerun without "
            "--ignore-stale to see them (suppressed from this output)."
        )

    payload["dynamic_refs"] = dynamic_list

    return json.dumps(payload, indent=2)
