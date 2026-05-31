"""Generic fallback adapter (Step 6c).

The generic adapter is the universal last-resort detector:

* It always returns a :class:`DetectedProjectProfile` — never ``None``.
* It claims no ``framework`` and no ``test_runner`` (Phase 1: those are
  the language-specific adapters' jobs).
* Its ``confidence`` is the lowest of all adapters so any matching
  language-specific adapter wins the selection in
  :mod:`qgb.core.detect`.

**Why "always returns a profile":** the calling convention of
:mod:`qgb.core.detect` is "ranking among candidates"; if no adapter
returns anything, ``selected`` would be undefined. Generic guarantees a
non-empty result.

**Why "no framework / no test_runner":** generic does not know the
target language, so it cannot meaningfully name a framework or a test
runner. Step 6d's design-stages will treat a generic profile as
"propose no language-specific stages; let the user write the contract by
hand".

**Phase 1 out-of-scope** (see :mod:`qgb.adapters.base` for the global
list; the generic-specific ones are):

* No content sniffing of files (e.g. shebang, magic bytes).
* No "approximate language" detection (e.g. "this looks like JS but
  there's no ``package.json``").
* No multi-language hint (e.g. "Python files present + Node files
  present"). That's a monorepo concern reserved for Phase 2.
"""

from __future__ import annotations

from pathlib import Path

from qgb.adapters.base import (
    BaseAdapter,
    DetectedProjectProfile,
    DetectionEvidence,
)

# Directories generic never walks into. Mirrors the global exclude list
# defined in adapters/base.py docstring (we keep them duplicated here as
# a constant so the runtime does not have to parse a docstring).
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

# Phase 1 ranking score for the fallback. Kept strictly below any
# language-specific adapter's lowest hit so a "weak python match"
# always still beats generic.
_GENERIC_CONFIDENCE = 0.1


class GenericAdapter(BaseAdapter):
    """Last-resort adapter; never returns ``None``."""

    name = "generic"

    def detect(self, project_root: Path) -> DetectedProjectProfile | None:
        evidence: list[DetectionEvidence] = []

        # Record whether project_root is a directory we can read at all.
        # We treat missing / unreadable directories as "the run will
        # produce a generic profile that says so" rather than raising,
        # so the calling CLI can still emit a stable JSON shape.
        if project_root.is_dir():
            visible, readable = self._top_level_visible(project_root)
            if not readable:
                # Codex 補修 3: unreadable directory must not be reported
                # as "empty". The two cases have different remediations
                # (chmod vs. populate) and conflating them obscures both.
                evidence.append(
                    DetectionEvidence(
                        kind="dir_unreadable",
                        where=".",
                        note="iterdir raised OSError",
                    )
                )
            elif visible:
                evidence.append(
                    DetectionEvidence(
                        kind="dir_readable",
                        where=".",
                        note=(
                            f"top-level entries (excluded dirs filtered): "
                            f"{len(visible)}"
                        ),
                    )
                )
                # Add up to a few concrete file evidences so the user
                # can see what generic actually saw. Cap at 5 to keep
                # JSON output reasonable.
                for entry in visible[:5]:
                    evidence.append(
                        DetectionEvidence(
                            kind="entry_observed",
                            where=entry.name,
                        )
                    )
            else:
                evidence.append(
                    DetectionEvidence(
                        kind="dir_empty",
                        where=".",
                        note="no top-level entries after applying excludes",
                    )
                )
        else:
            evidence.append(
                DetectionEvidence(
                    kind="dir_missing",
                    where=".",
                    note="project_root does not exist or is not a directory",
                )
            )

        return DetectedProjectProfile(
            language="generic",
            framework=None,
            test_runner=None,
            confidence=_GENERIC_CONFIDENCE,
            evidence=evidence,
            adapter_name=self.name,
        )

    @staticmethod
    def _top_level_visible(project_root: Path) -> tuple[list[Path], bool]:
        """Top-level entries with the exclude list applied.

        Returns ``(entries, readable)``. ``readable`` is ``False`` only
        when ``iterdir()`` raised ``OSError``; an empty directory still
        returns ``([], True)``.
        """
        try:
            entries = [
                entry
                for entry in sorted(project_root.iterdir())
                if entry.name not in _EXCLUDED_DIRS
            ]
        except OSError:
            return [], False
        return entries, True
