"""A terminal UI replacement for ``git diff``."""

from __future__ import annotations

import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

__all__ = ["__version__"]


def _pyproject_version() -> str:
    """Read the version from ``pyproject.toml`` in a source checkout."""
    path = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)["project"]["version"]
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return "0.0.0"


try:
    __version__ = version("gdiff")
except PackageNotFoundError:  # pragma: no cover - only when running uninstalled
    __version__ = _pyproject_version()
