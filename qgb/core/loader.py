"""Read the JSON sources of truth a `qgb run` needs.

Phase 1 entry points used by ``preflight`` and ``runner``:

* :func:`load_policy` - read ``.quality-system/policy.json``.
* :func:`load_req_meta` - read ``.quality-system/req/<REQ>.meta.json``.
* :func:`load_contract` - read a contract.json by path.
* :func:`load_config` - read ``.quality-system/config.json`` (for project name etc.).

Each helper raises :class:`LoaderError` for "file missing" or "JSON broken"
so callers can turn that into a NOT_READY diagnostic with a clear ``kind``.
This module performs *no* schema validation; that is :mod:`qgb.core.validate`'s
job (called by ``preflight`` before the runner sees anything).

The split between loader and validate keeps single responsibility: the
loader knows *where files live and how to read them*; validate knows
*whether their content conforms to the bundled schemas*.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LoaderErrorKind = Literal[
    "missing_file",
    "invalid_json",
    "wrong_type",
]


@dataclass(frozen=True)
class LoaderError(Exception):
    """A spec file could not be loaded."""

    kind: LoaderErrorKind
    path: Path
    message: str

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"[{self.kind}] {self.path}: {self.message}"


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise LoaderError(
            kind="missing_file",
            path=path,
            message=f"required spec file is missing: {path}",
        )
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise LoaderError(
            kind="invalid_json",
            path=path,
            message=f"invalid JSON: {exc}",
        ) from exc
    except OSError as exc:
        raise LoaderError(
            kind="missing_file",
            path=path,
            message=f"failed to read {path}: {exc}",
        ) from exc


def _expect_dict(payload: Any, path: Path) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise LoaderError(
            kind="wrong_type",
            path=path,
            message=f"top-level value must be an object, got {type(payload).__name__}",
        )
    return payload


# ---- public ---------------------------------------------------------------


def quality_system_root(project_root: Path) -> Path:
    """Return the canonical ``.quality-system/`` directory under ``project_root``."""
    return project_root / ".quality-system"


def load_config(project_root: Path) -> dict[str, Any]:
    path = quality_system_root(project_root) / "config.json"
    return _expect_dict(_read_json(path), path)


def load_policy(project_root: Path) -> dict[str, Any]:
    path = quality_system_root(project_root) / "policy.json"
    return _expect_dict(_read_json(path), path)


def req_meta_path(project_root: Path, req_id: str) -> Path:
    return quality_system_root(project_root) / "req" / f"{req_id}.meta.json"


def load_req_meta(project_root: Path, req_id: str) -> dict[str, Any]:
    path = req_meta_path(project_root, req_id)
    return _expect_dict(_read_json(path), path)


def resolve_project_relative(
    project_root: Path, ref: str, field_name: str
) -> Path:
    """Resolve ``ref`` relative to ``project_root`` and reject path escapes.

    Shared safety boundary for any project-rooted path coming from a JSON
    spec file (``contract_ref``, ``contract.target``, ``contract.schema``,
    etc.). Rejecting escapes here protects the runner from ever reading
    files outside the target project, which matters for both correctness
    (P7: the basis must only cite project-internal evidence) and safety
    (NF-007: a contract must not be able to point ``qgb run`` at
    arbitrary filesystem locations).

    Rejected (LoaderError, kind=``wrong_type``):

    * Absolute paths — the input contract is "project-rooted relative",
      not "any local path"; accepting an absolute path even when it
      happens to fall under the project would let users write specs
      that silently break when the project moves on disk (P9: input
      contracts must be unambiguous).
    * Paths that resolve outside the project root — even via ``..`` or
      a symlink whose ``resolve()`` lands elsewhere.
    """
    if Path(ref).is_absolute():
        raise LoaderError(
            kind="wrong_type",
            path=Path(ref),
            message=(
                f"{field_name} {ref!r} is an absolute path; "
                f"must be project-rooted relative (e.g. "
                f"'.quality-system/contracts/REQ-APP-001/S1.json')"
            ),
        )
    candidate = (project_root / ref).resolve()
    root_resolved = project_root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise LoaderError(
            kind="wrong_type",
            path=candidate,
            message=(
                f"{field_name} {ref!r} resolves outside the project root"
            ),
        ) from exc
    return candidate


def load_contract(project_root: Path, contract_ref: str) -> dict[str, Any]:
    """Resolve ``contract_ref`` relative to the project root and load it.

    REQ meta records ``contract_ref`` as a project-rooted relative path
    (e.g. ``.quality-system/contracts/REQ-APP-001/S1.json``). The loader is
    careful not to interpret absolute paths or path-escape attempts: a
    contract_ref that resolves outside the project root is rejected.
    """
    candidate = resolve_project_relative(project_root, contract_ref, "contract_ref")
    return _expect_dict(_read_json(candidate), candidate)


def project_context_path(project_root: Path) -> Path:
    """Return the canonical ``.quality-system/project-context.json`` path.

    Phase 3 Step 3.0 で導入。対象プロジェクトの自己定義 (機械正本)。
    """
    return quality_system_root(project_root) / "project-context.json"


def load_project_context(project_root: Path) -> dict[str, Any] | None:
    """Load ``.quality-system/project-context.json`` if present.

    Returns ``None`` when the file does not exist (Phase 3 Step 3.0: the
    file is optional — a project that has not yet declared its context
    simply omits the field from propose-context output as ``null``).

    Raises :class:`LoaderError` when the file exists but is unreadable or
    not a JSON object. Schema validation is performed by ``qgb validate``,
    not here (P9: the loader only handles read + shape; semantic checks
    belong to the validate path).

    BOM-tolerant via the shared ``_read_json`` helper (utf-8-sig).
    """
    path = project_context_path(project_root)
    if not path.is_file():
        return None
    return _expect_dict(_read_json(path), path)
