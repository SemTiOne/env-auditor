from __future__ import annotations

from importlib.metadata import version, PackageNotFoundError

try:
    __version__: str = version("env-auditor")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0-dev"

__all__ = ["__version__"]
