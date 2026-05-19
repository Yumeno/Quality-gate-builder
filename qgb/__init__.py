"""quality-gate-builder: generates trace-based quality gates for arbitrary target projects."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("quality-gate-builder")
except PackageNotFoundError:
    # Package is not installed (running directly from a source tree without
    # an editable install). Fall back to a sentinel so qgb --version still
    # produces output during development.
    __version__ = "0+unknown"
