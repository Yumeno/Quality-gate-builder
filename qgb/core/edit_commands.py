"""Domain edit commands: ``qgb add-waiver`` / ``qgb add-knowledge``.

Phase 2 Step 2.3 で新設。Phase 1 では手編集だった waiver 付与と knowledge
追記を CLI 化する **orchestration 層** (store 層は :mod:`qgb.core.knowledge`、
patch 適用は :mod:`qgb.core.patch_apply` — Codex 計画レビュー指摘 9 の
2 module 構成)。

### atomicity の定義 (Codex Step 2.3 計画レビュー指摘 3 で確定)

``add-waiver`` は req-meta と knowledge.jsonl の **2 ファイル** を更新する。
quality-system 全体の transaction は提供しない (Step 2.2 と同じ境界)。
保証は:

* **file 単位の保証**: req-meta は patch substrate の atomic swap (sibling
  tmp + os.replace)。knowledge.jsonl は **append-only + partial-tail
  tolerant + idempotent recovery** であり、atomic swap とは異なる保証
  (Step 2.3 補修 B3: 保証境界を過大表現しない)
* **idempotent recovery**: コマンドは「req-meta が望む状態か」「knowledge
  entry が存在するか」を**独立に**判定し、欠けている方だけを埋める。
  req-meta 更新後に knowledge append が失敗しても、**再実行すれば収束**する

### ``--force`` の意味 (同指摘 1 で確定)

* 未 waive の stage への add-waiver: --force 不要 (waiver_reason の残骸が
  あっても上書き)
* 既 waive + 同一 reason: --force 不要、no-op success (idempotent)
* 既 waive + 異 reason: --force **必須**。force 時は req-meta の
  waiver_reason のみ更新し、knowledge.jsonl の既存 entry は**変更しない**
  (append-only、歴史保持)。CLI 出力で乖離を明示警告する。reason の正式な
  改訂 (supersede) は Phase 3 の revoke/supersede モデルで扱う

### ``add-knowledge`` の境界 (同指摘 4/5/10 で確定)

* 入力は単一 object または array (内部で list に正規化)
* ``created_at`` の自動補完は **しない** (入力 file が正本、P7)
* 既存 id は skip (idempotent)。``--force`` は **付けない** (append-only
  と意味論が衝突するため。spec 完了条件の「--force 有り」は add-waiver 側
  で充足)
* schema 違反が 1 件でもあれば **全件 reject** (all-or-nothing、部分
  append による中途半端な状態を作らない)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgb.core.evidence import make_timestamps
from qgb.core.json_pointer import encode as pointer_encode
from qgb.core.knowledge import (
    append_knowledge_entries,
    build_waiver_knowledge_entry,
    knowledge_jsonl_path,
    read_existing_ids,
    waiver_knowledge_id,
)
from qgb.core.patch_apply import PatchApplyError, apply_patch_doc_to_target
from qgb.core.schema import validate as schema_validate

__all__ = [
    "EditError",
    "AddWaiverResult",
    "AddKnowledgeResult",
    "add_waiver",
    "add_knowledge",
]


@dataclass(frozen=True)
class EditError(ValueError):
    """Raised when a domain edit command cannot proceed.

    ``reason`` enum (CLI / Step 2.5 Pattern B の安定判定用):

    * ``"req_not_found"`` — REQ meta file が存在しない
    * ``"req_meta_not_json"`` — REQ meta が JSON として読めない
    * ``"stage_not_found"`` — REQ meta の stages[] に stage_id が無い
    * ``"invalid_reason"`` — --reason が空 (F-007 違反)
    * ``"waiver_conflict"`` — 既 waive + 異 reason で --force 無し
    * ``"knowledge_not_json"`` — add-knowledge の入力 file が JSON でない
    * ``"invalid_knowledge_document"`` — object でも array でもない
    * ``"knowledge_schema_violation"`` — entry が knowledge schema 違反
    * patch substrate 由来 (PatchApplyError からの transcode):
      ``"target_path_invalid"`` / ``"target_schema_violation"`` /
      ``"validate_policy_blocker"`` / ``"io_error"`` 等はそのまま引き継ぐ
    """

    reason: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.message} (reason={self.reason})"


@dataclass
class AddWaiverResult:
    """Result of :func:`add_waiver` (success path, including no-op)."""

    req_id: str
    stage_id: str
    meta_changed: bool
    knowledge_appended: bool
    forced: bool
    no_op: bool
    would_write: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class AddKnowledgeResult:
    """Result of :func:`add_knowledge` (success path, including all-skip)."""

    appended_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)
    would_write: bool = False
    written: bool = False


# ---------------------------------------------------------------------------
# add-waiver
# ---------------------------------------------------------------------------


def _req_meta_rel(req_id: str) -> str:
    return f".quality-system/req/{req_id}.meta.json"


def add_waiver(
    project_root: Path,
    req_id: str,
    stage_id: str,
    reason: str,
    *,
    decided_by: str = "user",
    force: bool = False,
    dry_run: bool = False,
) -> AddWaiverResult:
    """Waive a stage of a REQ: update req-meta + record knowledge evidence.

    See module docstring for atomicity / --force semantics. The req-meta
    update goes through the Step 2.2 patch substrate (schema + validate-
    policy gated, atomic swap); the knowledge entry goes through the
    Step 2.3 store layer (append-only, idempotent).
    """
    if not reason or not reason.strip():
        raise EditError(
            reason="invalid_reason",
            message="--reason must be a non-empty string (F-007: the "
            "justification is recorded as evidence)",
        )

    meta_rel = _req_meta_rel(req_id)
    meta_path = project_root / ".quality-system" / "req" / f"{req_id}.meta.json"
    if not meta_path.is_file():
        raise EditError(
            reason="req_not_found",
            message=f"REQ meta does not exist: {meta_rel}",
        )

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EditError(
            reason="req_meta_not_json",
            message=f"cannot parse {meta_rel}: {exc}",
        ) from exc

    stages = meta.get("stages")
    stage_index = -1
    if isinstance(stages, list):
        for i, entry in enumerate(stages):
            if isinstance(entry, dict) and entry.get("stage_id") == stage_id:
                stage_index = i
                break
    if stage_index < 0:
        known = (
            [
                e.get("stage_id")
                for e in stages
                if isinstance(e, dict) and isinstance(e.get("stage_id"), str)
            ]
            if isinstance(stages, list)
            else []
        )
        raise EditError(
            reason="stage_not_found",
            message=(
                f"stage {stage_id!r} is not declared in {meta_rel} "
                f"(declared: {known})"
            ),
        )

    stage_entry = stages[stage_index]
    already_waived = bool(stage_entry.get("waived", False))
    existing_reason = stage_entry.get("waiver_reason", "")

    warnings: list[str] = []
    forced = False

    # --- knowledge state (judged BEFORE the force branch so the warning
    #     below can tell the truth about whether an entry exists — Step 2.3
    #     補修 B1, Codex 横断レビュー指摘 1) ---
    wid = waiver_knowledge_id(req_id, stage_id)
    knowledge_ids = read_existing_ids(knowledge_jsonl_path(project_root))
    knowledge_needs_append = wid not in knowledge_ids

    # --- decide whether the meta needs a patch (idempotent recovery: the
    #     meta state and the knowledge state are judged independently) ---
    meta_needs_patch: bool
    if already_waived:
        if existing_reason == reason:
            meta_needs_patch = False
        elif not force:
            raise EditError(
                reason="waiver_conflict",
                message=(
                    f"stage {stage_id!r} is already waived with a different "
                    f"reason ({existing_reason!r}). Re-run with --force to "
                    f"overwrite the req-meta reason (the existing "
                    f"knowledge.jsonl entry is preserved as audit history; "
                    f"formal reason revision is Phase 3 revoke/supersede)"
                ),
                detail={
                    "existing_reason": existing_reason,
                    "requested_reason": reason,
                },
            )
        else:
            meta_needs_patch = True
            forced = True
            if knowledge_needs_append:
                # 補修 B1 境界ケース: meta は waived/reason A だが knowledge
                # entry が欠けている (過去の append 失敗や手編集)。--force で
                # reason B にすると、新規 entry は新 reason B で作られる —
                # 「既存 entry が歴史を保持する」とは言わない (entry は無い)。
                warnings.append(
                    f"--force: req-meta waiver_reason updated to {reason!r}. "
                    f"No existing knowledge entry was found for this waiver, "
                    f"so a NEW entry records the new reason; the previous "
                    f"req-meta reason {existing_reason!r} has no knowledge "
                    f"evidence (it was never recorded or was hand-removed)"
                )
            else:
                warnings.append(
                    f"--force: req-meta waiver_reason updated to {reason!r}, "
                    f"but the existing knowledge.jsonl entry keeps the "
                    f"original reason {existing_reason!r} as audit history "
                    f"(Phase 3 revoke/supersede will provide formal revision)"
                )
    else:
        meta_needs_patch = True

    no_op = not meta_needs_patch and not knowledge_needs_append
    if no_op:
        return AddWaiverResult(
            req_id=req_id,
            stage_id=stage_id,
            meta_changed=False,
            knowledge_appended=False,
            forced=False,
            no_op=True,
            would_write=False,
            warnings=[],
        )

    # --- build the patch (only ops that change state) ---
    if meta_needs_patch:
        ops: list[dict[str, Any]] = []
        stage_ptr = pointer_encode(["stages", stage_index])
        if not already_waived:
            # RFC 6902 add replaces an existing key, so this also cleans up
            # a stale waiver_reason left behind by manual un-waiving.
            ops.append(
                {"op": "add", "path": f"{stage_ptr}/waived", "value": True}
            )
        ops.append(
            {
                "op": "add",
                "path": f"{stage_ptr}/waiver_reason",
                "value": reason,
            }
        )
        try:
            apply_patch_doc_to_target(
                project_root, meta_rel, ops, dry_run=dry_run
            )
        except PatchApplyError as exc:
            raise EditError(
                reason=exc.reason,
                message=exc.message,
                detail=exc.detail,
            ) from exc

    if dry_run:
        # Step 2.3 補修 A1: dry-run reports the WOULD-BE changes so a caller
        # can compare dry-run output against a later real run (the previous
        # hard-coded False made the dry-run result useless for that).
        return AddWaiverResult(
            req_id=req_id,
            stage_id=stage_id,
            meta_changed=meta_needs_patch,
            knowledge_appended=knowledge_needs_append,
            forced=forced,
            no_op=False,
            would_write=True,
            warnings=warnings,
        )

    # --- knowledge append (after the meta is in the desired state) ---
    knowledge_appended = False
    if knowledge_needs_append:
        ts = make_timestamps()
        entry = build_waiver_knowledge_entry(
            req_id,
            stage_id,
            reason,
            decided_by=decided_by,
            created_at=ts.rfc3339,
        )
        # Step 2.3 補修 B2 (Codex 横断レビュー指摘 2): the domain command
        # itself must not be able to write an invalid knowledge entry —
        # e.g. ``--decided-by ""`` would violate minLength 1. Validate the
        # generated entry exactly like add-knowledge validates user input.
        issues = schema_validate(entry, "knowledge")
        if issues:
            raise EditError(
                reason="knowledge_schema_violation",
                message=(
                    f"the generated waiver entry violates "
                    f"knowledge.schema.json ({len(issues)} issue(s)); "
                    f"nothing was appended (req-meta was already updated; "
                    f"re-run with valid inputs to converge)"
                ),
                detail={
                    "issues": [
                        {"path": i.path, "message": i.message} for i in issues
                    ]
                },
            )
        # Step 2.3 補修 A2: an I/O failure here would otherwise surface as
        # a raw OSError traceback at the CLI. The meta patch has already
        # succeeded at this point — that is the documented "per-file atomic
        # + idempotent recovery" window: wrap the error so the CLI prints a
        # structured reason, and re-running the command converges (the meta
        # is found already in the desired state, only the append retries).
        try:
            report = append_knowledge_entries(project_root, [entry])
        except OSError as exc:
            raise EditError(
                reason="io_error",
                message=(
                    f"req-meta was updated, but appending the waiver entry "
                    f"to knowledge.jsonl failed: {exc}. Re-run the same "
                    f"command to converge (idempotent recovery)"
                ),
            ) from exc
        knowledge_appended = bool(report.appended_ids)

    return AddWaiverResult(
        req_id=req_id,
        stage_id=stage_id,
        meta_changed=meta_needs_patch,
        knowledge_appended=knowledge_appended,
        forced=forced,
        no_op=False,
        would_write=True,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# add-knowledge
# ---------------------------------------------------------------------------


def add_knowledge(
    project_root: Path,
    file_path: Path,
    *,
    dry_run: bool = False,
) -> AddKnowledgeResult:
    """Append user-provided knowledge entries from a JSON file.

    See module docstring for the input / idempotency / all-or-nothing
    boundaries. The input file is the source of truth: entries are
    schema-validated as-is (no created_at backfill) and appended verbatim.
    """
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise EditError(
            reason="knowledge_not_json",
            message=f"knowledge file does not exist: {file_path}",
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise EditError(
            reason="knowledge_not_json",
            message=f"cannot parse {file_path}: {exc}",
        ) from exc

    if isinstance(raw, dict):
        entries: list[Any] = [raw]
    elif isinstance(raw, list):
        entries = raw
    else:
        raise EditError(
            reason="invalid_knowledge_document",
            message=(
                f"knowledge input must be an object or an array of objects, "
                f"got {type(raw).__name__}"
            ),
        )

    if not entries:
        return AddKnowledgeResult(would_write=False, written=False)

    # All-or-nothing schema validation (no partial append).
    all_issues: list[dict[str, Any]] = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            all_issues.append(
                {
                    "index": i,
                    "path": "",
                    "message": f"entry must be an object, got {type(entry).__name__}",
                }
            )
            continue
        for issue in schema_validate(entry, "knowledge"):
            all_issues.append(
                {
                    "index": i,
                    "path": issue.path,
                    "message": issue.message,
                }
            )
    if all_issues:
        raise EditError(
            reason="knowledge_schema_violation",
            message=(
                f"{len(all_issues)} schema issue(s) across {len(entries)} "
                f"entr(y/ies); nothing was appended (all-or-nothing)"
            ),
            detail={"issues": all_issues},
        )

    if dry_run:
        existing = read_existing_ids(knowledge_jsonl_path(project_root))
        would_append: list[str] = []
        would_skip: list[str] = []
        seen: set[str] = set(existing)
        for entry in entries:
            eid = entry.get("id")
            if isinstance(eid, str) and eid in seen:
                would_skip.append(eid)
            else:
                if isinstance(eid, str):
                    seen.add(eid)
                    would_append.append(eid)
        return AddKnowledgeResult(
            appended_ids=would_append,
            skipped_ids=would_skip,
            would_write=bool(would_append),
            written=False,
        )

    # Step 2.3 補修 A2: structured error instead of a raw OSError traceback.
    try:
        report = append_knowledge_entries(project_root, entries)
    except OSError as exc:
        raise EditError(
            reason="io_error",
            message=f"appending to knowledge.jsonl failed: {exc}",
        ) from exc
    return AddKnowledgeResult(
        appended_ids=report.appended_ids,
        skipped_ids=report.skipped_ids,
        would_write=bool(report.appended_ids),
        written=bool(report.appended_ids),
    )
