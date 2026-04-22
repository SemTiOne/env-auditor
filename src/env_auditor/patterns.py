from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

# Env var name: uppercase, starts with letter, underscores/digits allowed
ENV_VAR_NAME = r"([A-Z][A-Z0-9_]*)"

# Dynamic reference patterns (cannot statically audit) — per language
_DYNAMIC_JS = re.compile(r"process\.env\[(?!['\"])" + r"([^\]]+)" + r"\]")
_DYNAMIC_PY = re.compile(
    r"os\.environ\[(?!['\"])"
    r"([^\]]+)"
    r"\]|os\.environ\.get\((?!['\"])"
    r"([^,)]+)"
    r"[,)]|os\.getenv\((?!['\"])"
    r"([^,)]+)"
    r"[,)]"
)


@dataclass
class LanguagePattern:
    """A named collection of compiled regexes for one language."""

    name: str
    extensions: Sequence[str]
    static_patterns: Sequence[re.Pattern[str]]
    dynamic_patterns: Sequence[re.Pattern[str]] = field(default_factory=list)


# All patterns are pre-compiled constants — never constructed from user input.
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
        extensions=[""],  # matched by filename, not extension
        static_patterns=[
            re.compile(r"^\s*ENV\s+" + ENV_VAR_NAME, re.MULTILINE),
            re.compile(r"^\s*ARG\s+" + ENV_VAR_NAME, re.MULTILINE),
        ],
        dynamic_patterns=[],
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
