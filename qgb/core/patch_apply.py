"""Apply a JSON Patch to a target file under .quality-system/, atomically.

Phase 2 Step 2.2 (prejournal §6.1 / §6.5) で新設。Step 2.2 の中核。

### フロー (案 X、prejournal §3 参照)

1. target を Read で parse (``json.load``)
2. patch を Read で parse、schema 検証 (``patch.schema.json``)
3. patch を ``apply_patch(doc, patch)`` で memory 上に適用 (副作用ゼロ、
   :class:`qgb.core.patch.PatchError` で reject)
4. 適用後の doc を :func:`qgb.core.schema.validate` で **対象 schema** に
   照らす (policy.json なら ``policy``、contract.json なら ``contract``、
   req-meta.json なら ``req-meta``)
5. 適用後の doc を override seam 経由で preflight にかけて整合性確認
   (Step 2.1 で確立した ``_collect_dollar_refs`` /
   ``_is_internal_pointer_ref`` 経路もここで走る)。検査範囲は target 種別で
   異なる: REQ_META / CONTRACT は当該 REQ の per-REQ 検査、**POLICY は
   Step 2.5 で project-wide + 既存全 REQ の same-world 検査に強化**
   (Step 2.2 当初の project-wide のみだと、stage rename patch が「policy
   単体は健全」のまま既存 REQ を unknown_stage_id で壊す盲点があった —
   prejournal phase2-step2-5 §2)
6. すべて pass したら sibling tmp に書く → ``os.replace`` で atomic swap
7. どこかで失敗したら原本は touch しない

### single-file atomic の境界 (Codex 指摘 7)

本モジュールが保証するのは **「target file 単体の atomicity」**。
``.quality-system/`` 全体の transaction ではない。例えば:

* ``policy.json`` を patch して新しい stage を追加し、続けて contract.json
  を追加するワークフローは、Step 2.2 では「2 回の ``qgb patch`` 呼び出し」
  になり、両方の atomic swap が成功したかは呼び出し側の責務
* multi-file rollback (Phase 3 送り) は本モジュールでは扱わない

### `--dry-run` 仕様 (Codex 指摘 9)

dry_run=True のときは 1-5 を完全に実行、6 を **skip**。tmp は作らない、
原本は touch しない、result に ``"would_write": True`` を載せる。
Step 2.4 (``qgb check`` / ``qgb dev``) で再利用するための seam。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from qgb.core.loader import LoaderError, resolve_project_relative
from qgb.core.patch import PatchError, apply_patch
from qgb.core.preflight import (
    PreflightReport,
    collect_same_world_blockers,
    collect_same_world_warnings,
    validate_policy_preflight,
    validate_policy_preflight_same_world,
)
from qgb.core.schema import validate as schema_validate

__all__ = [
    "PatchApplyError",
    "PatchApplyResult",
    "TargetKind",
    "ALLOWED_TARGETS",
    "apply_patch_doc_to_target",
    "apply_patch_to_target",
    "classify_target",
]


class TargetKind(str, Enum):
    """Recognised patch targets under ``.quality-system/`` (Phase 2 Step 2.2)."""

    POLICY = "policy"
    REQ_META = "req-meta"
    CONTRACT = "contract"


# Allowed project-relative target paths. ``contract`` is matched by prefix
# (``.quality-system/contracts/<REQ>/<stage>.json``); the other two are exact.
ALLOWED_TARGETS: dict[str, TargetKind] = {
    ".quality-system/policy.json": TargetKind.POLICY,
}


@dataclass(frozen=True)
class PatchApplyError(ValueError):
    """Raised when ``apply_patch_to_target`` fails.

    ``reason`` enum (Step 2.5 Pattern B の安定判定用):

    * ``"target_path_invalid"`` — absolute path / path escape / non-allowed file
    * ``"target_not_found"`` — file does not exist
    * ``"target_not_json"`` — target parses as something other than JSON
    * ``"patch_not_json"`` — patch document parses fails
    * ``"patch_schema_violation"`` — patch document violates patch.schema.json
    * ``"patch_apply_failed"`` — :class:`PatchError` from apply_patch
    * ``"target_schema_violation"`` — patched doc violates its own schema
    * ``"validate_policy_blocker"`` — patched project view has blockers
    * ``"io_error"`` — read/write/replace failed
    """

    reason: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.message} (reason={self.reason})"


@dataclass
class PatchApplyResult:
    """Successful (or successful-but-skipped) result of a patch apply.

    Step 2.5 Pattern B が消費する想定の構造化フィールド。
    """

    target: Path
    target_kind: TargetKind
    would_write: bool
    written: bool
    warnings: list[str] = field(default_factory=list)
    preflight_report: PreflightReport | None = None


# ---------------------------------------------------------------------------
# Target classification
# ---------------------------------------------------------------------------


def classify_target(project_root: Path, target_rel: str) -> tuple[Path, TargetKind]:
    """Resolve ``target_rel`` under project_root and identify its kind.

    Codex 計画レビュー指摘 10:

    * Absolute paths are rejected.
    * ``..``-escapes / symlink escapes are rejected (R1 guard via
      :func:`resolve_project_relative`).
    * Only ``.quality-system/policy.json``, ``.quality-system/req/<REQ>.meta.json``,
      and ``.quality-system/contracts/<REQ>/<stage>.json`` are accepted.

    Raises :class:`PatchApplyError` (``reason="target_path_invalid"``) on
    anything else.
    """
    if os.path.isabs(target_rel):
        raise PatchApplyError(
            reason="target_path_invalid",
            message=f"target must be project-relative, got absolute path: {target_rel}",
        )

    try:
        resolved = resolve_project_relative(project_root, target_rel, "target")
    except LoaderError as exc:
        raise PatchApplyError(
            reason="target_path_invalid",
            message=str(exc),
        ) from exc

    # Normalize the relative form for kind detection.
    norm = target_rel.replace("\\", "/")

    if norm == ".quality-system/policy.json":
        return resolved, TargetKind.POLICY

    if norm.startswith(".quality-system/req/") and norm.endswith(".meta.json"):
        # .quality-system/req/<REQ>.meta.json
        # Step 2.2 補修 A2 (Codex / subagent correctness 中): canonical
        # layout は exactly 3 segments (``.quality-system/req/<REQ>.meta.json``)。
        # ネスト (``.quality-system/req/sub/X.meta.json``) は CONTRACT 同様 reject。
        segments = norm.split("/")
        if len(segments) != 3:
            raise PatchApplyError(
                reason="target_path_invalid",
                message=(
                    f"REQ-meta target must be "
                    f".quality-system/req/<REQ>.meta.json with exactly 3 "
                    f"segments (got {target_rel!r})"
                ),
            )
        return resolved, TargetKind.REQ_META

    if norm.startswith(".quality-system/contracts/") and norm.endswith(".json"):
        # .quality-system/contracts/<REQ>/<stage>.json
        # Reject deeper nesting (must be exactly 4 segments).
        segments = norm.split("/")
        if len(segments) != 4:
            raise PatchApplyError(
                reason="target_path_invalid",
                message=(
                    f"contract target must be .quality-system/contracts/<REQ>/<stage>.json"
                    f" (got {target_rel!r})"
                ),
            )
        return resolved, TargetKind.CONTRACT

    raise PatchApplyError(
        reason="target_path_invalid",
        message=(
            f"target {target_rel!r} is not one of the Phase 2 Step 2.2 allowed "
            f"paths (.quality-system/policy.json, "
            f".quality-system/req/<REQ>.meta.json, "
            f".quality-system/contracts/<REQ>/<stage>.json)"
        ),
    )


# ---------------------------------------------------------------------------
# Patch loading + schema validation
# ---------------------------------------------------------------------------


def _load_json_file(path: Path, *, reason_on_error: str) -> Any:
    """Read+parse a JSON file. Returns parsed value or raises PatchApplyError."""
    try:
        with path.open("r", encoding="utf-8-sig") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise PatchApplyError(
            reason=reason_on_error if reason_on_error != "patch_not_json" else "io_error",
            message=f"file not found: {path}",
        ) from exc
    except OSError as exc:
        raise PatchApplyError(
            reason="io_error",
            message=f"read error on {path}: {exc}",
        ) from exc
    except json.JSONDecodeError as exc:
        raise PatchApplyError(
            reason=reason_on_error,
            message=f"invalid JSON in {path}: {exc}",
        ) from exc


def _validate_patch_against_schema(patch: Any, patch_path: Path) -> None:
    """Validate the patch document against ``patch.schema.json``."""
    issues = schema_validate(patch, "patch")
    if issues:
        formatted = [
            {"path": i.path, "message": i.message, "schema_path": i.schema_path}
            for i in issues
        ]
        raise PatchApplyError(
            reason="patch_schema_violation",
            message=(
                f"patch {patch_path} violates patch.schema.json "
                f"({len(issues)} issue(s))"
            ),
            detail={"issues": formatted},
        )


def _validate_target_against_schema(
    patched: Any, kind: TargetKind, target: Path
) -> None:
    """Validate the patched doc against its own type's schema."""
    issues = schema_validate(patched, kind.value)
    if issues:
        formatted = [
            {"path": i.path, "message": i.message, "schema_path": i.schema_path}
            for i in issues
        ]
        raise PatchApplyError(
            reason="target_schema_violation",
            message=(
                f"patched {target} violates {kind.value}.schema.json "
                f"({len(issues)} issue(s))"
            ),
            detail={"issues": formatted},
        )


# ---------------------------------------------------------------------------
# Project-wide validation via override seam (案 X)
# ---------------------------------------------------------------------------


def _run_validate_policy_with_override(
    project_root: Path,
    kind: TargetKind,
    target_rel: str,
    patched: Any,
) -> list[tuple[str | None, PreflightReport]]:
    """Run the preflight with the patched doc as an in-memory override.

    The seam introduced in :func:`qgb.core.preflight.validate_policy_preflight`
    (Phase 2 Step 2.2 案 X) lets us check the patched view without touching
    disk. Returns ``(scope, report)`` pairs — scope is the REQ id the
    report was resolved for, or ``None`` for the project-wide pass.

    Step 2.5: the POLICY branch now runs
    :func:`validate_policy_preflight_same_world` (project-wide + every
    existing REQ against the same patched policy). REQ_META / CONTRACT
    keep their single per-REQ report — a meta/contract edit can only
    affect its own REQ's resolution.
    """
    if kind is TargetKind.POLICY:
        return validate_policy_preflight_same_world(
            project_root, policy_override=patched
        )
    if kind is TargetKind.REQ_META:
        # Derive REQ id from path: .quality-system/req/<REQ>.meta.json
        req_id = _req_id_from_meta_path(target_rel)
        return [(req_id, validate_policy_preflight(
            project_root, req_id=req_id, req_meta_override=patched
        ))]
    if kind is TargetKind.CONTRACT:
        # Derive contract_ref (already canonical) and REQ id from path.
        req_id = _req_id_from_contract_path(target_rel)
        return [(req_id, validate_policy_preflight(
            project_root,
            req_id=req_id,
            contract_overrides={target_rel.replace("\\", "/"): patched},
        ))]
    raise PatchApplyError(
        reason="target_path_invalid",
        message=f"unknown target kind: {kind}",
    )


def _req_id_from_meta_path(target_rel: str) -> str:
    """Extract REQ id from ``.quality-system/req/<REQ>.meta.json``."""
    norm = target_rel.replace("\\", "/")
    # norm = .quality-system/req/<REQ>.meta.json
    filename = norm.split("/")[-1]
    return filename[: -len(".meta.json")]


def _req_id_from_contract_path(target_rel: str) -> str:
    """Extract REQ id from ``.quality-system/contracts/<REQ>/<stage>.json``."""
    norm = target_rel.replace("\\", "/")
    return norm.split("/")[2]


# ---------------------------------------------------------------------------
# Atomic write (Step 6d / Step 7 で確立した sibling tmp + os.replace)
# ---------------------------------------------------------------------------


def _atomic_write_json(target: Path, doc: Any) -> None:
    """Write ``doc`` to ``target`` atomically via sibling tmp + os.replace.

    Format:
    * UTF-8, ``ensure_ascii=False``
    * Indented 2 spaces (matches qgb init / scaffold conventions)
    * Trailing newline
    * Sibling tmp uses ``tempfile.NamedTemporaryFile`` in target's parent dir
    * On any failure during write/replace, the tmp file is removed and
      ``PatchApplyError(reason="io_error")`` is raised. ``target`` is
      either left unchanged (write failed) or replaced (os.replace succeeded).
    """
    parent = target.parent
    encoded = (
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")

    tmp_fd: int | None = None
    tmp_path: Path | None = None
    try:
        # Step 2.2 補修 A4 (Codex / subagent windows 高反映): suffix=".tmp"
        # を明示。Phase 1 Step 6d / 7 で確立した ``qgb/core/design_stages.py``
        # の atomic write pattern と一貫性を保つ。
        tmp_fd, tmp_name = tempfile.mkstemp(
            prefix=target.name + ".tmp-",
            suffix=".tmp",
            dir=str(parent),
        )
        tmp_path = Path(tmp_name)
        with os.fdopen(tmp_fd, "wb") as fh:
            tmp_fd = None
            fh.write(encoded)
        # os.replace is atomic on POSIX and Win32 within the same volume.
        os.replace(tmp_path, target)
        tmp_path = None  # ownership transferred
    except OSError as exc:
        if tmp_path is not None and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
        if tmp_fd is not None:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        raise PatchApplyError(
            reason="io_error",
            message=f"failed to write {target}: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_patch_to_target(
    project_root: Path,
    target_rel: str,
    patch_path: Path,
    *,
    dry_run: bool = False,
) -> PatchApplyResult:
    """Apply a JSON Patch file to a target under .quality-system/.

    See module docstring for the full flow (steps 1-7). The order is
    spec-locked: schema → patch → apply → target schema → validate-policy
    → swap. Any earlier failure leaves the target file untouched.

    :param project_root: project root (the directory containing
        ``.quality-system/``).
    :param target_rel: project-relative path to the target file
        (e.g. ``.quality-system/policy.json``).
    :param patch_path: path to the patch JSON file (any location on disk;
        Phase 2 Step 2.2 doesn't restrict where the patch lives).
    :param dry_run: when True, perform all validations but do NOT write.
        ``would_write`` in the result indicates whether a real run would
        have written.
    :returns: :class:`PatchApplyResult` on success (including dry-run).
    :raises PatchApplyError: on any of the 8 reason codes (see class).
    """
    # 3 (file front-end). Read the patch document; everything after parse
    # is shared with the in-memory entry point below (Step 2.3 切り出し).
    patch_doc = _load_json_file(patch_path, reason_on_error="patch_not_json")
    return apply_patch_doc_to_target(
        project_root, target_rel, patch_doc, dry_run=dry_run
    )


def apply_patch_doc_to_target(
    project_root: Path,
    target_rel: str,
    patch_doc: Any,
    *,
    dry_run: bool = False,
) -> PatchApplyResult:
    """Apply an in-memory JSON Patch document to a target file.

    Phase 2 Step 2.3 で :func:`apply_patch_to_target` から切り出した
    **core 内部向けの低水準 API** (Codex Step 2.3 計画レビュー指摘 8)。
    `qgb add-waiver` (edit_commands) のような domain edit command が patch
    を file 経由でなく直接組み立てて流すための入口。

    file path 版との意味一致 (テストで固定):

    * patch schema 検証 / apply / target schema 検証 / validate-policy /
      atomic swap / dry-run の全段が file path 版と同一コード経路
    * 違いは「patch document を file から読むか引数で受けるか」のみ
    """
    # 1. Resolve target.
    target, kind = classify_target(project_root, target_rel)
    if not target.exists():
        raise PatchApplyError(
            reason="target_not_found",
            message=f"target file does not exist: {target}",
        )

    # 2. Read target as JSON.
    original = _load_json_file(target, reason_on_error="target_not_json")

    # 3. Validate the patch document shape.
    _validate_patch_against_schema(patch_doc, Path("<in-memory>"))

    # 4. Apply patch in memory.
    try:
        patched = apply_patch(original, patch_doc)
    except PatchError as exc:
        raise PatchApplyError(
            reason="patch_apply_failed",
            message=str(exc),
            detail={
                "op_index": exc.op_index,
                "patch_reason": exc.reason,
                "pointer": exc.pointer,
            },
        ) from exc

    # 5a. Validate against target schema.
    _validate_target_against_schema(patched, kind, target)

    # 5b. Validate the patched view via the override seam. POLICY targets
    # get the Step 2.5 same-world treatment (project-wide + every
    # existing REQ); REQ_META / CONTRACT stay single per-REQ reports.
    reports = _run_validate_policy_with_override(
        project_root, kind, target_rel, patched
    )
    blockers = collect_same_world_blockers(reports)
    if blockers:
        # Surface blockers in a structured way; warnings are recorded but
        # not blocking (Step 6a severity 規約). ``scope`` tells callers
        # (and Phase 5 skills) WHICH REQ a policy change breaks.
        blocker_kinds = [b["kind"] for b in blockers]
        raise PatchApplyError(
            reason="validate_policy_blocker",
            message=(
                f"patched view has {len(blocker_kinds)} blocker(s): "
                f"{blocker_kinds}"
            ),
            detail={"blockers": blockers},
        )

    warnings = [
        f"{w['kind']} at {w['where']}: {w['message']}"
        for w in collect_same_world_warnings(reports)
    ]
    # Backward-compat: PatchApplyResult.preflight_report stays a single
    # report — the project-wide one for POLICY (reports[0]), the per-REQ
    # one otherwise.
    preflight_report = reports[0][1]

    if dry_run:
        return PatchApplyResult(
            target=target,
            target_kind=kind,
            would_write=True,
            written=False,
            warnings=warnings,
            preflight_report=preflight_report,
        )

    # 6. Atomic swap.
    _atomic_write_json(target, patched)

    return PatchApplyResult(
        target=target,
        target_kind=kind,
        would_write=True,
        written=True,
        warnings=warnings,
        preflight_report=preflight_report,
    )
