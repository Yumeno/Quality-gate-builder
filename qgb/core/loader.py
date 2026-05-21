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
        with path.open("r", encoding="utf-8") as fh:
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


def load_contract(project_root: Path, contract_ref: str) -> dict[str, Any]:
    """Resolve ``contract_ref`` relative to the project root and load it.

    REQ meta records ``contract_ref`` as a project-rooted relative path
    (e.g. ``.quality-system/contracts/REQ-APP-001/S1.json``). The loader is
    careful not to interpret absolute paths or path-escape attempts: a
    contract_ref that resolves outside the project root is rejected.
    """
    candidate = (project_root / contract_ref).resolve()
    root_resolved = project_root.resolve()
    try:
        candidate.relative_to(root_resolved)
    except ValueError as exc:
        raise LoaderError(
            kind="wrong_type",
            path=candidate,
            message=(
                f"contract_ref {contract_ref!r} resolves outside the project root"
            ),
        ) from exc
    return _expect_dict(_read_json(candidate), candidate)
