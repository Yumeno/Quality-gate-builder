"""Adapter base contract for Phase 1 detect (Step 6c).

This module defines the **data boundary** between ``qgb/core/`` (language-
agnostic) and ``qgb/adapters/`` (language-specific). Per P9 the two layers
must not bleed into each other:

* ``core`` calls adapters but never branches on language identity.
* adapters return :class:`DetectedProjectProfile` and never read
  ``policy.json``, never execute commands, never make adoption decisions.

The ``detect()`` contract is intentionally pure:

* Input: ``project_root: Path``.
* Output: a :class:`DetectedProjectProfile` if the adapter recognised the
  tree, otherwise ``None``.

The collected results are then composed by :mod:`qgb.core.detect` into a
:class:`DetectionResult` (selected best-confidence profile + the full
candidates list).

**Phase 1 out-of-scope** (documented here so future Step 6c-style
revisions do not silently relax the rules):

* Adapters do not run shell commands or import target packages.
* Adapters do not read lockfiles or perform dependency resolution
  (Codex 補修 6: this also covers ``[dependency-groups]``,
  ``[tool.uv]``, poetry ``group.<name>.dependencies``, and pip
  constraint files).
* Adapters do not handle monorepo sub-projects; the whole ``project_root``
  is treated as one unit.
* Adapters do not parse shebangs.
* Adapters do not return multiple framework / test_runner candidates;
  the most likely one is picked, others are not exposed.
* Adapters do not normalise filename case (Codex 補修 8: Windows
  filesystems are typically case-insensitive but ``Path.suffix`` is a
  literal string match; loose ``.PY`` will not be recognised as
  Python. Phase 1 assumes lowercase conventions; Phase 2 may add
  case-fold matching).
* ``confidence`` is a **heuristic ranking score**, not a probability.
  It is used to rank multiple matching adapters; it does not represent
  a calibrated belief.
* ``evidence[].where`` is **project-root-relative** (or a logical
  location like ``pyproject.toml[project.dependencies]``); absolute paths
  must not appear here.

**CLI vs. core fallback contract** (Codex 補修 1 — clarified):

* :func:`qgb.core.detect.run_detect` always returns a
  :class:`DetectionResult` whose ``selected`` is non-``None``. Missing
  / unreadable directories are observed by ``GenericAdapter`` and
  surface as ``dir_missing`` / ``dir_unreadable`` evidence on the
  generic profile.
* The CLI layer (``qgb detect``) still rejects ``--path`` values that
  do not exist or point at a file with ``EXIT_USAGE``; this preserves
  typo detection for interactive use. A path that exists and is a
  directory — even one whose contents we cannot read — flows through to
  ``run_detect`` and produces a generic profile.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class DetectionEvidence:
    """One observable that justified an adapter's match.

    * ``kind`` — short category tag (e.g. ``file_exists``,
      ``file_glob_match``, ``key_in_file``, ``fallback``). Adapters are
      free to define their own kinds; ``core.detect`` does not
      enumerate them.
    * ``where`` — project-root-relative path or logical location.
      Example: ``"pyproject.toml"``, ``"pyproject.toml[project.dependencies]"``.
      Absolute paths must not appear here (environment-dependent and would
      leak into JSON output).
    * ``note`` — optional human-readable detail.
    """

    kind: str
    where: str
    note: str = ""


@dataclass(frozen=True)
class DetectedProjectProfile:
    """Result a single adapter returns when it recognises the project.

    Field semantics (kept narrow on purpose so Step 6d can consume this
    without re-interpretation):

    * ``language`` — the canonical language tag (``"python"``,
      ``"node"``, ``"generic"``, ...). Required.
    * ``framework`` — auxiliary information only. May influence stage
      *naming* in Step 6d but must not be load-bearing for stage selection.
    * ``test_runner`` — the single most-likely test command category
      (``"pytest"``, ``"vitest"``, ...). One adapter returns at most one
      candidate; alternatives are not exposed in Phase 1.
    * ``confidence`` — heuristic ranking score in ``[0.0, 1.0]``. Used
      only to compare against other adapters; not a probability.
    * ``evidence`` — list of observable facts justifying the match.
    * ``adapter_name`` — name of the adapter that produced this profile
      (matches ``BaseAdapter.name``).
    """

    language: str
    framework: str | None
    test_runner: str | None
    confidence: float
    evidence: list[DetectionEvidence] = field(default_factory=list)
    adapter_name: str = ""


@dataclass(frozen=True)
class DetectionResult:
    """Aggregated outcome of all adapters for one ``project_root``.

    * ``selected`` — the profile with the highest ``confidence``. Ties
      are broken by the order adapters were registered in
      :mod:`qgb.core.detect`.
    * ``candidates`` — every adapter's match. The generic fallback is
      included only when no other adapter matched; otherwise it is
      excluded so callers can detect "no language-specific match" by
      its absence rather than by checking adapter_name.
    """

    selected: DetectedProjectProfile
    candidates: list[DetectedProjectProfile] = field(default_factory=list)


class BaseAdapter:
    """Abstract base for language- / ecosystem-specific adapters.

    Subclasses **must**:

    * set ``name`` as a class variable (matches what they will write
      into ``DetectedProjectProfile.adapter_name``).
    * override :meth:`detect` to return either a profile or ``None``.

    Subclasses **must not**:

    * write to disk (detection is read-only).
    * execute external commands.
    * import or instantiate target-language packages.
    """

    name: str = ""

    def detect(self, project_root: Path) -> DetectedProjectProfile | None:
        """Inspect ``project_root`` and return a profile if recognised."""
        raise NotImplementedError
