from __future__ import annotations

import os
import sys
from typing import IO


def supports_color(stream: IO[str] = sys.stdout) -> bool:
    """Return True if *stream* looks like a color-capable terminal.

    Respects the ``NO_COLOR`` and ``FORCE_COLOR`` environment variables
    per the https://no-color.org/ and https://force-color.org/ specs.

    Args:
        stream: Output stream to check. Defaults to stdout.

    Returns:
        True if ANSI color codes should be emitted.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    return hasattr(stream, "isatty") and stream.isatty()


class Colors:
    """ANSI escape code constants for terminal output."""

    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"


class NoColors:
    """Drop-in replacement for Colors that emits no escape codes."""

    RED = ""
    YELLOW = ""
    CYAN = ""
    GREEN = ""
    BLUE = ""
    MAGENTA = ""
    DIM = ""
    BOLD = ""
    RESET = ""


def get_colors(use_color: bool) -> Colors | NoColors:
    """Return the appropriate color set based on *use_color*.

    Args:
        use_color: If True, return ANSI-enabled Colors; otherwise NoColors.

    Returns:
        Colors or NoColors instance.
    """
    return Colors() if use_color else NoColors()
