"""Python project adapter (Step 6c).

Phase 1 detection is **static and shallow**: marker files, top-level
``*.py`` count, and dependency / tool-section grep inside
``pyproject.toml``. No interpreter inspection, no virtualenv probing,
no shebang parsing.

Signals weighed (in rough order of strength):

1. Marker files (``pyproject.toml`` > ``setup.py``/``setup.cfg`` >
   ``requirements*.txt``).
2. Framework hint from ``pyproject.toml`` dependencies.
3. ``test_runner`` hint from pyproject (``pytest`` dependency,
   ``[tool.pytest...]`` section, or ``tests/test_*.py`` convention).
4. Loose ``*.py`` files at the project root (cap: must be 2+ at root
   excluding obvious tooling).

The confidence score is **heuristic ranking**, not probability. The
rough scale is:

* all three (marker + framework + runner) → 0.85–0.95
* marker only → 0.55–0.7
* loose ``*.py`` only → 0.25–0.4 (still strictly above generic 0.1)

**Phase 1 out-of-scope** (see :mod:`qgb.adapters.base` for the
universal list; the python-specific ones are):

* Reading lockfiles (``poetry.lock``, ``pdm.lock``, ``uv.lock``) or
  resolving extras / markers / constraints.
* Running ``python -m`` introspection or importing the project.
* Detecting alternative test runners (``unittest`` discovery,
  ``nose``, ``ward``). Phase 1 names at most ``pytest``.
* Recognising more than one framework simultaneously (e.g. fastapi
  + celery). The first hit wins, in fastapi → django → flask order.
* Source layouts beyond top-level / ``src/`` (Phase 2 adapters may add
  ``app/``, ``apps/``, etc.).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from qgb.adapters.base import (
    BaseAdapter,
    DetectedProjectProfile,
    DetectionEvidence,
)

try:
    # Standard library since Python 3.11.
    import tomllib as _tomllib  # type: ignore[import-not-found]

    _HAS_TOMLLIB = True
except ImportError:  # pragma: no cover - Python 3.10 fallback path.
    _tomllib = None  # type: ignore[assignment]
    _HAS_TOMLLIB = False


_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        ".idea",
        ".vscode",
    }
)

# Framework names recognised in pyproject dependencies. Order matters:
# the first match wins (Phase 1 single-framework limitation).
_FRAMEWORKS: tuple[tuple[str, str], ...] = (
    ("fastapi", "fastapi"),
    ("django", "django"),
    ("flask", "flask"),
)


@dataclass
class _Signals:
    """Internal aggregate of what was found, used to rank confidence."""

    has_pyproject: bool = False
    has_setup_py: bool = False
    has_setup_cfg: bool = False
    has_requirements: bool = False
    loose_py_count: int = 0
    framework: str | None = None
    test_runner: str | None = None
    evidence: list[DetectionEvidence] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.evidence is None:
            self.evidence = []

    def any_marker(self) -> bool:
        return (
            self.has_pyproject
            or self.has_setup_py
            or self.has_setup_cfg
            or self.has_requirements
        )


class PythonAdapter(BaseAdapter):
    name = "python"

    def detect(
        self, project_root: Path
    ) -> DetectedProjectProfile | None:
        if not project_root.is_dir():
            return None

        # Codex 補修 2: any OSError while scanning (PermissionError,
        # FileNotFoundError on stale dirs, NotADirectoryError on race)
        # falls through to ``None`` so :func:`qgb.core.detect.run_detect`
        # can still reach the generic fallback.
        try:
            sig = self._scan(project_root)
        except OSError:
            return None

        # Reject trees that do not look Python at all: no marker file and
        # fewer than 2 top-level ``*.py`` files.
        if not sig.any_marker() and sig.loose_py_count < 2:
            return None

        confidence = self._rank(sig)
        return DetectedProjectProfile(
            language="python",
            framework=sig.framework,
            test_runner=sig.test_runner,
            confidence=confidence,
            evidence=sig.evidence,
            adapter_name=self.name,
        )

    # ------------------------------------------------------------------

    def _scan(self, project_root: Path) -> _Signals:
        sig = _Signals()

        # Marker files at top level.
        for marker in ("pyproject.toml", "setup.py", "setup.cfg"):
            if (project_root / marker).is_file():
                sig.evidence.append(
                    DetectionEvidence(kind="file_exists", where=marker)
                )
                if marker == "pyproject.toml":
                    sig.has_pyproject = True
                elif marker == "setup.py":
                    sig.has_setup_py = True
                else:
                    sig.has_setup_cfg = True

        for req in sorted(project_root.glob("requirements*.txt")):
            if req.is_file():
                sig.evidence.append(
                    DetectionEvidence(kind="file_exists", where=req.name)
                )
                sig.has_requirements = True

        # Loose ``*.py`` at top level (excluding hidden / excluded dirs
        # by virtue of iterating only the root).
        loose_py = [
            p
            for p in project_root.iterdir()
            if p.is_file() and p.suffix == ".py" and not p.name.startswith(".")
        ]
        sig.loose_py_count = len(loose_py)
        if sig.loose_py_count >= 2:
            sig.evidence.append(
                DetectionEvidence(
                    kind="file_glob_match",
                    where="*.py",
                    note=f"{sig.loose_py_count} files at project root",
                )
            )

        # framework + test_runner from pyproject.toml.
        if sig.has_pyproject:
            self._enrich_from_pyproject(project_root, sig)

        # tests/ + test_*.py convention -> pytest (even without pyproject).
        if sig.test_runner is None:
            self._enrich_from_tests_dir(project_root, sig)

        return sig

    def _enrich_from_pyproject(
        self, project_root: Path, sig: _Signals
    ) -> None:
        pyproject = project_root / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return

        parsed: dict | None = None
        if _HAS_TOMLLIB and _tomllib is not None:
            try:
                parsed = _tomllib.loads(text)
            except Exception:  # noqa: BLE001 - tomllib raises various subclasses.
                parsed = None

        if parsed is not None:
            self._enrich_from_parsed_pyproject(parsed, sig)
        else:
            # Fallback for Python 3.10 (no tomllib): coarse regex grep.
            self._enrich_from_pyproject_text(text, sig)

    def _enrich_from_parsed_pyproject(
        self, parsed: dict, sig: _Signals
    ) -> None:
        deps_text = self._collect_dependency_strings(parsed)

        for keyword, name in _FRAMEWORKS:
            if self._dep_matches(deps_text, keyword):
                sig.framework = name
                sig.evidence.append(
                    DetectionEvidence(
                        kind="key_in_file",
                        where="pyproject.toml[project.dependencies]",
                        note=f"contains {keyword}",
                    )
                )
                break

        if self._dep_matches(deps_text, "pytest"):
            sig.test_runner = "pytest"
            sig.evidence.append(
                DetectionEvidence(
                    kind="key_in_file",
                    where="pyproject.toml[project.dependencies]",
                    note="contains pytest",
                )
            )

        # [tool.pytest...] section is a strong runner hint.
        tool = parsed.get("tool")
        if isinstance(tool, dict) and isinstance(tool.get("pytest"), dict):
            if sig.test_runner is None:
                sig.test_runner = "pytest"
            sig.evidence.append(
                DetectionEvidence(
                    kind="key_in_file",
                    where="pyproject.toml[tool.pytest]",
                    note="section present",
                )
            )

    def _enrich_from_pyproject_text(
        self, text: str, sig: _Signals
    ) -> None:
        """3.10 fallback: regex grep for known keywords."""
        lowered = text.lower()
        for keyword, name in _FRAMEWORKS:
            if re.search(rf"\b{re.escape(keyword)}\b", lowered):
                sig.framework = name
                sig.evidence.append(
                    DetectionEvidence(
                        kind="key_in_file",
                        where="pyproject.toml",
                        note=f"text contains {keyword}",
                    )
                )
                break
        if re.search(r"\bpytest\b", lowered):
            sig.test_runner = "pytest"
            sig.evidence.append(
                DetectionEvidence(
                    kind="key_in_file",
                    where="pyproject.toml",
                    note="text contains pytest",
                )
            )

    def _enrich_from_tests_dir(
        self, project_root: Path, sig: _Signals
    ) -> None:
        tests_dir = project_root / "tests"
        if not tests_dir.is_dir():
            return
        try:
            entries = list(tests_dir.iterdir())
        except OSError:
            return
        test_files = [
            p
            for p in entries
            if p.is_file()
            and p.suffix == ".py"
            and (p.name.startswith("test_") or p.name.endswith("_test.py"))
        ]
        if len(test_files) >= 2:
            sig.test_runner = "pytest"
            sig.evidence.append(
                DetectionEvidence(
                    kind="dir_convention",
                    where="tests/",
                    note=f"{len(test_files)} test_*.py files",
                )
            )

    @staticmethod
    def _collect_dependency_strings(parsed: dict) -> list[str]:
        """Pull every plausible dependency declaration into a flat list."""
        out: list[str] = []
        project = parsed.get("project")
        if isinstance(project, dict):
            deps = project.get("dependencies")
            if isinstance(deps, list):
                out.extend(str(d) for d in deps)
            opt = project.get("optional-dependencies")
            if isinstance(opt, dict):
                for group in opt.values():
                    if isinstance(group, list):
                        out.extend(str(d) for d in group)
        # poetry-style: [tool.poetry.dependencies]
        tool = parsed.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                p_deps = poetry.get("dependencies")
                if isinstance(p_deps, dict):
                    out.extend(p_deps.keys())
                p_dev = poetry.get("dev-dependencies")
                if isinstance(p_dev, dict):
                    out.extend(p_dev.keys())
        return out

    @staticmethod
    def _dep_matches(deps: list[str], keyword: str) -> bool:
        """Loose match: 'fastapi>=0.110' / 'Flask~=3.0' both count."""
        keyword_l = keyword.lower()
        for dep in deps:
            dep_l = dep.lower()
            # Strip extras and version specifiers crudely.
            head = re.split(r"[\[\s<>=!~;]", dep_l, maxsplit=1)[0]
            if head == keyword_l:
                return True
        return False

    # ------------------------------------------------------------------

    @staticmethod
    def _rank(sig: _Signals) -> float:
        """Heuristic ranking score (not probability)."""
        # All three strong signals.
        if sig.has_pyproject and sig.framework and sig.test_runner:
            return 0.9
        # pyproject + one extra hint.
        if sig.has_pyproject and (sig.framework or sig.test_runner):
            return 0.75
        # Marker only.
        if sig.any_marker():
            return 0.6
        # Loose .py files only.
        if sig.loose_py_count >= 5:
            return 0.4
        if sig.loose_py_count >= 2:
            return 0.3
        # Shouldn't reach here because detect() pre-filtered.
        return 0.0
