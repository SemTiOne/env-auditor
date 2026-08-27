from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

# Env var name: uppercase, starts with letter, underscores/digits allowed
ENV_VAR_NAME = r"([A-Z][A-Z0-9_]*)"

# All patterns are pre-compiled constants — never constructed from user input.
# _DYNAMIC_JS and _DYNAMIC_PY below are unused module-level refs that were
# previously dead code — removed. Dynamic patterns live inside LanguagePattern.


@dataclass
class LanguagePattern:
    """A named collection of compiled regexes for one language."""

    name: str
    extensions: Sequence[str]
    static_patterns: Sequence[re.Pattern[str]]
    dynamic_patterns: Sequence[re.Pattern[str]] = field(default_factory=list)
    line_filter: re.Pattern[str] | None = None
    """If set, static_patterns/dynamic_patterns are only applied to lines that
    match this filter first. Used by Docker: the KEY= continuation pattern
    (which has no anchor of its own) must not fire on RUN/LABEL/CMD lines that
    happen to contain shell-local KEY=value assignments, e.g.
    ``RUN DEBIAN_FRONTEND=noninteractive apt-get install -y curl``, that is
    a build-time shell variable, not a container ENV declaration, and must
    not be reported as an (un)documented application variable."""


LANGUAGE_PATTERNS: list[LanguagePattern] = [
    LanguagePattern(
        name="JavaScript/TypeScript",
        extensions=[".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"],
        static_patterns=[
            re.compile(r"process\.env\." + ENV_VAR_NAME),
            re.compile(r"process\.env\['" + ENV_VAR_NAME + r"'\]"),
            re.compile(r'process\.env\["' + ENV_VAR_NAME + r'"\]'),
        ],
        dynamic_patterns=[
            re.compile(r"process\.env\[(?!['\"])(.*?)\]"),
        ],
    ),
    LanguagePattern(
        name="Python",
        extensions=[".py"],
        static_patterns=[
            re.compile(r"os\.environ\['" + ENV_VAR_NAME + r"'\]"),
            re.compile(r'os\.environ\["' + ENV_VAR_NAME + r'"\]'),
            re.compile(r"os\.environ\.get\('" + ENV_VAR_NAME + r"'"),
            re.compile(r'os\.environ\.get\("' + ENV_VAR_NAME + r'"'),
            re.compile(r"os\.getenv\('" + ENV_VAR_NAME + r"'"),
            re.compile(r'os\.getenv\("' + ENV_VAR_NAME + r'"'),
            re.compile(r"environ\['" + ENV_VAR_NAME + r"'\]"),
            re.compile(r'environ\["' + ENV_VAR_NAME + r'"\]'),
        ],
        dynamic_patterns=[
            re.compile(r"os\.environ\[(?!['\"])(.*?)\]"),
            re.compile(r"os\.environ\.get\((?!['\"])(.*?)[,)]"),
            re.compile(r"os\.getenv\((?!['\"])(.*?)[,)]"),
        ],
    ),
    LanguagePattern(
        name="Go",
        extensions=[".go"],
        static_patterns=[
            re.compile(r'os\.Getenv\("' + ENV_VAR_NAME + r'"\)'),
            re.compile(r'os\.LookupEnv\("' + ENV_VAR_NAME + r'"\)'),
        ],
        dynamic_patterns=[
            re.compile(r"os\.Getenv\((?!\")[^)]+\)"),
            re.compile(r"os\.LookupEnv\((?!\")[^)]+\)"),
        ],
    ),
    LanguagePattern(
        name="Shell",
        extensions=[".sh", ".bash", ".zsh"],
        static_patterns=[
            re.compile(r"\$\{" + ENV_VAR_NAME + r"\}"),
            re.compile(r"\$" + ENV_VAR_NAME + r"\b"),
        ],
        dynamic_patterns=[],
    ),
    LanguagePattern(
        name="Docker",
        extensions=[],  # matched by filename in scanner._get_patterns, not
        # extension. Do not add "" here: EXTENSION_MAP registers every
        # entry in `extensions` verbatim, so extensions=[""] previously
        # made *every* extensionless file (Makefile, LICENSE, README, ...)
        # fall through to Docker's ENV/ARG patterns via the generic
        # EXTENSION_MAP[""] lookup, not just genuine Dockerfiles.
        static_patterns=[
            # ENV KEY=val (new style, single) or ENV KEY value (deprecated style)
            re.compile(r"^\s*ENV\s+" + ENV_VAR_NAME),
            # ENV KEY1=val1 KEY2=val2 KEY3=val3 — additional vars after the first
            # (Docker's recommended single-line multi-assignment style, used to
            # reduce image layer count). Scoped to ENV/ARG lines only via
            # line_filter below. This pattern has no anchor of its own and
            # would otherwise match KEY=value tokens on RUN/LABEL/CMD lines too
            # (e.g. RUN DEBIAN_FRONTEND=noninteractive apt-get install ...).
            re.compile(r"(?<=\s)" + ENV_VAR_NAME + r"="),
            # ARG KEY or ARG KEY=default
            re.compile(r"^\s*ARG\s+" + ENV_VAR_NAME),
        ],
        dynamic_patterns=[],
        line_filter=re.compile(r"^\s*(?:ENV|ARG)\s"),
    ),
    LanguagePattern(
        name="Ruby",
        extensions=[".rb", ".rake"],
        static_patterns=[
            re.compile(r"ENV\['" + ENV_VAR_NAME + r"'\]"),
            re.compile(r'ENV\["' + ENV_VAR_NAME + r'"\]'),
            re.compile(r"ENV\.fetch\('" + ENV_VAR_NAME + r"'"),
            re.compile(r'ENV\.fetch\("' + ENV_VAR_NAME + r'"'),
        ],
        dynamic_patterns=[
            re.compile(r"ENV\[(?!['\"])(.*?)\]"),
            re.compile(r"ENV\.fetch\((?!['\"])(.*?)[,)]"),
        ],
    ),
]

# Extension -> list of LanguagePattern (fast lookup)
EXTENSION_MAP: dict[str, list[LanguagePattern]] = {}
for _lp in LANGUAGE_PATTERNS:
    for _ext in _lp.extensions:
        EXTENSION_MAP.setdefault(_ext, []).append(_lp)

# Dockerfile is matched by basename
DOCKERFILE_PATTERN: LanguagePattern = next(
    lp for lp in LANGUAGE_PATTERNS if lp.name == "Docker"
)

# Names that are almost always false positives in shell patterns
SHELL_NOISE: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
        "PWD",
        "TERM",
        "LANG",
        "LC_ALL",
        "IFS",
        "PS1",
        "PS2",
        "OLDPWD",
        "SHLVL",
        "LOGNAME",
        "MAIL",
        "HOSTNAME",
    }
)
