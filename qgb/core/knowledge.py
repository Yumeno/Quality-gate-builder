"""Knowledge store operations for .quality-system/knowledge/knowledge.jsonl.

Phase 2 Step 2.3 で新設 (Codex 計画レビュー指摘 9: knowledge store 操作と
domain edit workflow を分離する P9 構成)。本 module は **store 層**:

* :func:`append_knowledge_entries` — append-only + partial-tail tolerant な
  追記。Phase 1 Step 7 で `evidence._record_waiver_knowledge` に確立した
  ロジックをここに移植・共通化 (evidence 側は本関数へ委譲)。
* :func:`build_waiver_knowledge_entry` — waiver entry の唯一の builder。
  `qgb run` 時の自動記録と `qgb add-waiver` の即時記録が**同じ shape** を
  書くことを保証する (Codex 計画レビュー指摘 2: builder 共通化でズレ防止)。
* :func:`check_knowledge_orphans` — knowledge.jsonl 内で参照される REQ /
  stage の存在検査 (Step 2.3 の orphan check 本体)。validate-policy が
  消費する。

**knowledge.jsonl は patch substrate の対象外** (Step 2.2 完結時の申し送り):
append-only JSONL は「行の追記」だけが正当な編集で、JSON Patch の
add/replace/remove とは編集モデルが異なる。Step 2.5 (Pattern B) の proposal
適用でも knowledge への書き込みは本 module 経由に限る。

orphan check の severity 設計 (Codex 計画レビュー指摘 6/7):

* kind=waiver で applies_to の REQ が存在しない → **blocker**
  (waiver は現在の判定除外に使われる operational knowledge。対象 REQ が
  消えたら安全側に倒す。spec 完了条件「add-waiver 後に REQ 削除で検出」)
* kind=waiver で stage_id が当該 REQ-meta の stages[] に存在しない →
  **blocker** (同上)
* 非 waiver kind で applies_to の REQ が存在しない → **warning**
  (歴史的知識・外部出典は REQ 削除後も価値を持ちうる)
* applies_to が REQ パターン (``REQ-``) に一致しない自由文字列は検査対象外
* malformed line / partial tail は silent skip (validate の責務、P9)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__ = [
    "AppendReport",
    "OrphanFinding",
    "append_knowledge_entries",
    "build_waiver_knowledge_entry",
    "check_knowledge_orphans",
    "knowledge_jsonl_path",
    "read_existing_ids",
    "waiver_knowledge_id",
]


# Same shape as scaffold's REQ_ID_PATTERN; kept local so the store layer
# doesn't import from scaffold (P9).
_REQ_ID_RE = re.compile(r"^REQ-[A-Z0-9]+-[0-9]{3,}$")


def knowledge_jsonl_path(project_root: Path) -> Path:
    """Return the canonical knowledge.jsonl path for a project."""
    return project_root / ".quality-system" / "knowledge" / "knowledge.jsonl"


@dataclass
class AppendReport:
    """Result of :func:`append_knowledge_entries`."""

    appended_ids: list[str] = field(default_factory=list)
    skipped_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OrphanFinding:
    """A knowledge entry whose referenced REQ / stage no longer exists.

    ``severity`` mirrors PreflightSeverity ("blocker" / "warning") but is a
    plain string here so this module stays import-light (preflight imports
    knowledge, not the other way around — no cycle).
    """

    knowledge_id: str
    knowledge_kind: str
    applies_to: str
    stage_id: str
    severity: str
    message: str


# ---------------------------------------------------------------------------
# Append (moved from evidence._record_waiver_knowledge, Step 7 lineage)
# ---------------------------------------------------------------------------


def read_existing_ids(kjsonl: Path) -> set[str]:
    """Collect the ``id`` of every parseable entry in knowledge.jsonl.

    Malformed lines (including a partial tail) are skipped silently —
    surfacing them is ``qgb validate``'s responsibility (P9).

    Step 2.4 補修 A2: bytes are decoded with ``errors="replace"`` so a
    tail torn mid-multi-byte-character (the crash-mid-append shape this
    reader exists to tolerate — reasons routinely contain Japanese) lands
    in the same skip branch as a text-level torn tail instead of raising
    ``UnicodeDecodeError`` out of every caller.
    """
    existing: set[str] = set()
    if not kjsonl.is_file():
        return existing
    for line in kjsonl.read_bytes().decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        # 補修 B1: a line carrying U+FFFD was byte-corrupted; its id (or
        # any other field) cannot be trusted, so derive nothing from it.
        # qgb validate reports the corruption loudly (P9).
        if "�" in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and isinstance(entry.get("id"), str):
            existing.add(entry["id"])
    return existing


def append_knowledge_entries(
    project_root: Path, entries: list[dict[str, Any]]
) -> AppendReport:
    """Append entries to knowledge.jsonl, skipping ids that already exist.

    Behaviour (Phase 1 Step 7 で確立、Step 2.3 で store 層へ移植):

    * Idempotent: an entry whose ``id`` already exists is recorded in
      ``skipped_ids`` and NOT rewritten (a user-edited reason is preserved).
    * Partial-tail tolerant: if the existing file does not end with a
      newline, a newline is written first so the new entries land on
      their own lines and stay parseable.
    * Append-only: existing lines are never modified or reordered. Each
      entry is written as one ``write()`` call (document + newline in a
      single string — Step 2.3 補修 B3).

    保証境界 (Step 2.3 補修 B3, Codex 横断レビュー指摘 3): これは
    **append-only + partial-tail tolerant + idempotent recovery** であって、
    req-meta 側の atomic swap (sibling tmp + os.replace) とは**異なる**。
    write 途中のクラッシュは partial tail を残しうるが、次回の読み手
    (validate / read_existing_ids) は partial tail を skip し、次回の
    書き手は改行を前置してから append するので、ファイルは常に回復可能。

    Caller is responsible for schema-validating ``entries`` beforehand
    (edit_commands does; evidence's waiver builder emits known-good shape).
    """
    report = AppendReport()
    if not entries:
        return report

    kjsonl = knowledge_jsonl_path(project_root)
    kjsonl.parent.mkdir(parents=True, exist_ok=True)

    existing_ids = read_existing_ids(kjsonl)

    to_append: list[dict[str, Any]] = []
    for entry in entries:
        eid = entry.get("id")
        if isinstance(eid, str) and eid in existing_ids:
            report.skipped_ids.append(eid)
            continue
        to_append.append(entry)
        if isinstance(eid, str):
            existing_ids.add(eid)

    if not to_append:
        return report

    needs_leading_newline = False
    if kjsonl.is_file() and kjsonl.stat().st_size > 0:
        with kjsonl.open("rb") as fh:
            fh.seek(-1, 2)
            needs_leading_newline = fh.read(1) != b"\n"

    with kjsonl.open("a", encoding="utf-8") as fh:
        if needs_leading_newline:
            fh.write("\n")
        for entry in to_append:
            # One write() per entry (B3): document and newline in a single
            # string narrows the partial-tail window to within one entry.
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
            eid = entry.get("id")
            if isinstance(eid, str):
                report.appended_ids.append(eid)

    return report


# ---------------------------------------------------------------------------
# Waiver entry builder (single source of shape, Codex 計画レビュー指摘 2)
# ---------------------------------------------------------------------------


def waiver_knowledge_id(req_id: str, stage_id: str) -> str:
    """Canonical knowledge.jsonl id for a per-(REQ, stage) waiver.

    Phase 2 Step 2.3: moved here from ``qgb.core.evidence`` so the store
    layer owns the id format; evidence re-exports for backward compat.
    The ``gate.json#basis`` row is this id prefixed with ``KNOWLEDGE-``
    (see ``evidence.build_basis``).
    """
    return f"WAIVER-{req_id}-{stage_id}"


def build_waiver_knowledge_entry(
    req_id: str,
    stage_id: str,
    reason: str,
    *,
    decided_by: str = "user",
    created_at: str,
) -> dict[str, Any]:
    """Build the canonical ``kind: waiver`` knowledge entry.

    Used by BOTH ``qgb run`` (evidence._record_waiver_knowledge) and
    ``qgb add-waiver`` (edit_commands.add_waiver) so the two paths can
    never drift apart. The id format is owned by
    :func:`waiver_knowledge_id` (``WAIVER-<REQ>-<stage>``).
    """
    return {
        "id": waiver_knowledge_id(req_id, stage_id),
        "kind": "waiver",
        "title": f"Waiver for {req_id} / {stage_id}",
        "applies_to": req_id,
        "stage_id": stage_id,
        "reason": reason,
        "decided_by": decided_by,
        "source_type": "user",
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Orphan check (Step 2.3 軸 4)
# ---------------------------------------------------------------------------


def _req_meta_exists(project_root: Path, req_id: str) -> bool:
    return (
        project_root / ".quality-system" / "req" / f"{req_id}.meta.json"
    ).is_file()


def _req_meta_stage_ids(project_root: Path, req_id: str) -> set[str] | None:
    """Return the stage_id set declared in a REQ meta, or None if unreadable.

    Unreadable / malformed meta is NOT an orphan finding — schema problems
    are ``qgb validate`` / preflight territory (P9). Returning None makes
    the stage-level check skip rather than false-positive.
    """
    meta_path = (
        project_root / ".quality-system" / "req" / f"{req_id}.meta.json"
    )
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    stages = meta.get("stages")
    if not isinstance(stages, list):
        return None
    ids: set[str] = set()
    for entry in stages:
        if isinstance(entry, dict) and isinstance(entry.get("stage_id"), str):
            ids.add(entry["stage_id"])
    return ids


def check_knowledge_orphans(project_root: Path) -> list[OrphanFinding]:
    """Scan knowledge.jsonl for entries referencing missing REQs / stages.

    See module docstring for the severity design. Findings are returned in
    file order (stable for tests and reports).

    Step 2.4 補修 A2: decoded with ``errors="replace"`` for the same
    reason as :func:`read_existing_ids` — this scan is advisory context
    for ``qgb check`` and must not crash on a byte-torn partial tail.
    """
    findings: list[OrphanFinding] = []
    kjsonl = knowledge_jsonl_path(project_root)
    if not kjsonl.is_file():
        return findings

    for line in kjsonl.read_bytes().decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        # 補修 B1: never derive findings from a byte-corrupted line — a
        # garbled applies_to would fabricate a bogus orphan blocker.
        # qgb validate reports the corruption loudly (P9).
        if "�" in line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            # Malformed / partial tail: validate's territory, skip here.
            continue
        if not isinstance(entry, dict):
            continue

        kind = entry.get("kind")
        eid = entry.get("id")
        if not isinstance(kind, str) or not isinstance(eid, str):
            continue

        applies = entry.get("applies_to")
        applies_list: list[str] = []
        if isinstance(applies, str):
            applies_list = [applies]
        elif isinstance(applies, list):
            applies_list = [a for a in applies if isinstance(a, str)]

        for target in applies_list:
            if not _REQ_ID_RE.match(target):
                # Free-form applies_to (not a REQ reference): out of scope.
                continue
            if not _req_meta_exists(project_root, target):
                severity = "blocker" if kind == "waiver" else "warning"
                findings.append(
                    OrphanFinding(
                        knowledge_id=eid,
                        knowledge_kind=kind,
                        applies_to=target,
                        stage_id=str(entry.get("stage_id", "")),
                        severity=severity,
                        message=(
                            f"knowledge entry {eid!r} (kind={kind}) refers to "
                            f"{target!r} but no such REQ meta exists"
                        ),
                    )
                )
                continue

            # REQ exists. For waivers, the stage must also exist in that
            # REQ's meta (policy-level existence is preflight's own
            # unknown_stage_id check — not duplicated here, P9).
            if kind == "waiver":
                stage_id = entry.get("stage_id")
                if not isinstance(stage_id, str) or not stage_id:
                    continue  # schema violation — validate's territory
                stage_ids = _req_meta_stage_ids(project_root, target)
                if stage_ids is None:
                    continue  # unreadable meta — preflight's territory
                if stage_id not in stage_ids:
                    findings.append(
                        OrphanFinding(
                            knowledge_id=eid,
                            knowledge_kind=kind,
                            applies_to=target,
                            stage_id=stage_id,
                            severity="blocker",
                            message=(
                                f"waiver {eid!r} refers to stage "
                                f"{stage_id!r} which is not declared in "
                                f"{target}'s meta stages[]"
                            ),
                        )
                    )

    return findings
