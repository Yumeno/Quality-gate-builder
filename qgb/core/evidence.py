"""Serialise a run's results to gate.json / summary.md / stage logs.

Two output trees (matches detailed-design.md §7.4, §7.5, §8.7 and philosophy P7):

* **Volatile** ``artifacts/<REQ>/runs/<timestamp_utc>-<run_id>/``
    - Every run lands here regardless of outcome.
    - ``timestamp_utc`` is the wall-clock instant of the run (seconds
      precision). ``run_id`` (``r0001``-``rffff``) is a per-second
      monotonic counter assigned at reservation time; it absorbs
      same-second collisions without falsifying the timestamp.
    - ``QGB_KEEP_RUNS`` (default 10) caps how many run-dirs are kept;
      older ones are deleted oldest-first.
* **Curated** ``evidence/<REQ>/latest/``
    - Updated by ``qgb run`` only.
    - Byte-for-byte equal contents to the volatile copy, so reviewers can
      diff curated/latest without surprises.

What lands in each:

* ``gate.json``     - the strict (curated) / permissive (volatile) gate report.
* ``summary.md``    - human-readable summary, identical in both copies.
* ``stages/<id>.log`` - per-stage execution log; ``stages[].log_ref``
                          in gate.json references this filename.

Phase 1 ``basis[]`` shape (§7.5):

* ``REQ-<id>``
* ``POLICY-<policy_id>`` (or ``POLICY-default`` when missing)
* ``CONTRACT-<REQ>-<stage_id>`` for every adopted stage (in REQ meta order).
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from qgb import __version__
from qgb.core.decision import Decision
from qgb.core.preflight import AdoptedStage
from qgb.core.runner import StageResult


@dataclass(frozen=True)
class Timestamps:
    """Compact and RFC3339 forms of the same UTC instant."""

    compact: str       # YYYY-MM-DDTHHMMSSZ
    rfc3339: str       # YYYY-MM-DDTHH:MM:SSZ


@dataclass(frozen=True)
class EvidenceWriteResult:
    """Where evidence was written."""

    run_dir: Path
    curated_dir: Path
    gate_path_curated: Path
    gate_path_volatile: Path


# ---------------------------------------------------------------------------


def make_timestamps(now: datetime | None = None) -> Timestamps:
    """Generate the two timestamp forms from a single UTC instant.

    Both forms describe the same wall-clock instant (seconds precision).
    The compact form (no separators in time) is what feeds the first
    segment of ``paths.run_dir`` because Windows forbids ``:`` in path
    segments. Collision avoidance lives in :func:`_reserve_run_dir` and
    does **not** touch the timestamp; collisions are absorbed by
    ``run_id`` so this function stays wall-clock-honest.
    """
    instant = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(
        microsecond=0
    )
    return _timestamps_from_instant(instant)


def _timestamps_from_instant(instant: datetime) -> Timestamps:
    instant = instant.astimezone(timezone.utc).replace(microsecond=0)
    compact = instant.strftime("%Y-%m-%dT%H%M%SZ")
    rfc3339 = instant.strftime("%Y-%m-%dT%H:%M:%SZ")
    return Timestamps(compact=compact, rfc3339=rfc3339)


# run_id space: 'r' + 4 lowercase hex digits, r0001..rffff = 65535 slots/second.
_RUN_ID_MIN = 1
_RUN_ID_MAX = 0xFFFF


def _format_run_id(n: int) -> str:
    return f"r{n:04x}"


class RunDirReservationError(RuntimeError):
    """No free run_id slot could be reserved within the same second."""


def _reserve_run_dir(
    runs_root: Path, timestamps: Timestamps
) -> tuple[Path, str]:
    """Reserve a run_dir atomically by picking the next free ``run_id``.

    Two ``qgb run`` invocations inside the same wall-clock second would
    otherwise share a directory and the second run would overwrite the
    first's volatile evidence (P7 violation: every run must have its own
    durable trace until ``QGB_KEEP_RUNS`` decides to prune it).

    Step 5 三次補修: ``timestamp_utc`` now stays as wall-clock truth.
    Collisions are absorbed by walking ``run_id`` forward (``r0001`` ->
    ``r0002`` -> ...) within the same second; the directory layout
    becomes ``<timestamp_utc>-<run_id>``. ``mkdir(exist_ok=False)`` is
    the locking primitive: two parallel processes that pick the same
    ``run_id`` will see one ``mkdir`` succeed and the other raise
    ``FileExistsError`` and move on.

    Returns a tuple of ``(reserved_run_dir, run_id)``. Raises
    :class:`RunDirReservationError` when every slot in
    ``r0001``..``rffff`` is already taken for this second — that
    indicates either a bug or a system under denial-of-service-like
    pressure, and a loud failure beats a silent schema-invalid gate.
    """
    runs_root.mkdir(parents=True, exist_ok=True)
    for n in range(_RUN_ID_MIN, _RUN_ID_MAX + 1):
        run_id = _format_run_id(n)
        candidate = runs_root / f"{timestamps.compact}-{run_id}"
        try:
            candidate.mkdir(parents=False, exist_ok=False)
        except FileExistsError:
            continue
        return candidate, run_id

    raise RunDirReservationError(
        f"could not reserve a run_id under {runs_root} for {timestamps.compact}: "
        f"all {_RUN_ID_MAX} slots are taken"
    )


def build_basis(
    req_id: str, policy: dict[str, Any] | None, adopted: list[AdoptedStage]
) -> list[str]:
    """Phase 1 ``basis[]`` per detailed-design.md §7.5.

    Step 7 D: each waived stage contributes a
    ``KNOWLEDGE-WAIVER-<REQ>-<stage>`` row so the gate auditor can
    follow the waiver back to ``knowledge.jsonl``.
    """
    policy_id = "default"
    if policy and isinstance(policy.get("policy_id"), str):
        policy_id = policy["policy_id"]
    out = [req_id, f"POLICY-{policy_id}"]
    out.extend(f"CONTRACT-{req_id}-{stage.stage_id}" for stage in adopted)
    for stage in adopted:
        if stage.waived:
            out.append(f"KNOWLEDGE-{waiver_knowledge_id(req_id, stage.stage_id)}")
    return out


def waiver_knowledge_id(req_id: str, stage_id: str) -> str:
    """Canonical knowledge.jsonl id for a per-(REQ, stage) waiver."""
    return f"WAIVER-{req_id}-{stage_id}"


def build_gate_document(
    *,
    req_id: str,
    phase: str,
    timestamps: Timestamps,
    run_id: str,
    decision: Decision,
    adopted: list[AdoptedStage],
    results: list[StageResult],
    basis: list[str],
    run_dir_rel: str,
    curated_latest_rel: str,
) -> dict[str, Any]:
    """Assemble the dict that becomes gate.json (both copies).

    Step 6+7 統合レビュー補修 (Codex A6): if the runner produced no
    result for an adopted stage (which should not happen in normal
    operation but could appear after refactors or partial failures),
    we **must not** silently drop the stage from ``stages_payload``.
    Dropping it would leave gate.json with fewer stages than were
    adopted, breaking the "every adopted stage is judgement material"
    contract and confusing auditors. Instead, we synthesise a
    ``result=failed`` entry naming the missing stage so the gate
    evidence is internally consistent and the failure is visible.
    """
    stages_payload: list[dict[str, Any]] = []
    results_by_id = {r.stage_id: r for r in results}
    for stage in adopted:
        r = results_by_id.get(stage.stage_id)
        if r is None:
            # Step 6+7 統合レビュー RA1: distinguish runner-integrity
            # failure from a normal stage failure. ``synthetic: true`` +
            # ``synthetic_reason`` lets an auditor see that the missing
            # result is an internal evidence gap (the runner did not
            # produce a result for an adopted stage) rather than a
            # legitimate failed check. ``schema_version: 1.0`` of
            # gate.json allows additional properties so this is
            # backward-compatible.
            stages_payload.append(
                {
                    "id": stage.stage_id,
                    "name": stage.name,
                    "result": "failed",
                    "verification_type": stage.verification_type,
                    "exit_code": None,
                    "contract_ref": stage.contract_ref,
                    "log_ref": f"stages/{stage.stage_id}.log",
                    "synthetic": True,
                    "synthetic_reason": "missing_result_for_adopted_stage",
                }
            )
            continue
        stages_payload.append(
            {
                "id": r.stage_id,
                "name": r.name,
                "result": r.result,
                "verification_type": r.verification_type,
                "exit_code": r.exit_code,
                "contract_ref": r.contract_ref,
                "log_ref": f"stages/{r.stage_id}.log",
            }
        )

    return {
        "schema_version": "1.0",
        "req_id": req_id,
        "timestamp_utc": timestamps.compact,
        "timestamp_rfc3339": timestamps.rfc3339,
        "run_id": run_id,
        "phase": phase,
        "status": decision.status,
        "failed_stage": decision.failed_stage,
        "decision": {
            "result": decision.status,
            "meaning": decision.meaning,
            # Codex RA2: ``scope`` keeps ``meaning`` strictly verbatim
            # per F-016 by hoisting the project-local (P11) note out of
            # the meaning string. Exact-match consumers of ``meaning``
            # are unaffected; auditors reading ``decision.scope`` see
            # the P11 framing.
            "scope": decision.scope,
        },
        "runner": {"name": "qgb", "version": __version__},
        "paths": {
            "run_dir": run_dir_rel,
            "curated_latest_dir": curated_latest_rel,
        },
        "stages": stages_payload,
        "basis": basis,
    }


def build_summary_md(gate: dict[str, Any]) -> str:
    """Render the human-readable summary.md.

    Identical content in both curated and volatile copies. The wording is
    deliberately conservative (P5, P11): ALLOW is "defined checks passed",
    not "this project is good".
    """
    lines: list[str] = []
    req_id = gate["req_id"]
    status = gate["status"]
    meaning = gate["decision"]["meaning"]

    lines.append(f"# {req_id} 採用判定サマリ")
    lines.append("")
    lines.append("## 判定結果")
    lines.append("")
    lines.append(f"**{status}**")
    lines.append("")
    lines.append(f"> {meaning}")
    lines.append("")
    lines.append("## 実行情報")
    lines.append("")
    lines.append("| 項目 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| REQ ID | {req_id} |")
    lines.append(f"| Phase | {gate['phase']} |")
    lines.append(f"| 実行日時 (UTC) | {gate['timestamp_utc']} |")
    lines.append(f"| 実行日時 (RFC3339) | {gate['timestamp_rfc3339']} |")
    lines.append(f"| run_id | `{gate['run_id']}` |")
    lines.append(
        f"| Runner | {gate['runner']['name']} {gate['runner']['version']} |"
    )
    lines.append(f"| run_dir | `{gate['paths']['run_dir']}` |")
    lines.append(f"| curated_latest_dir | `{gate['paths']['curated_latest_dir']}` |")
    if status == "DENY":
        lines.append(f"| failed_stage | `{gate['failed_stage']}` |")
    lines.append("")
    lines.append("## 段階別結果")
    lines.append("")
    lines.append("| 段階 | 名前 | 結果 | verification_type |")
    lines.append("|---|---|---|---|")
    for stage in gate["stages"]:
        row = (
            f"| {stage['id']} | {stage['name']} | {stage['result']} | "
            f"{stage['verification_type']} |"
        )
        lines.append(row)
    lines.append("")
    if status == "ALLOW":
        lines.append("すべての必須段階が通過したため、status=ALLOW。")
    elif gate["failed_stage"]:
        lines.append(
            f"必須段階 `{gate['failed_stage']}` が failed のため、status=DENY。"
        )
    else:
        # Step 6+7 統合レビュー (Codex A9): all-waived DENY. No stage
        # actually failed — the REQ simply has no judgement material
        # because every adopted stage was waived. Avoid the misleading
        # "stage `` が failed" wording.
        lines.append(
            "すべての必須段階が waived のため判定対象が存在せず、status=DENY。"
        )
    lines.append("")
    lines.append("## 採用根拠 (basis)")
    lines.append("")
    for b in gate["basis"]:
        lines.append(f"- {b}")
    lines.append("")
    lines.append("## 注意 (思想 P5, P11)")
    lines.append("")
    lines.append(
        "- 本判定は「定義済み検査に通過した」ことのみを意味する。"
        "完全な正しさ・業務妥当性・将来の保証は意味しない"
    )
    lines.append(
        "- 本判定は当該プロジェクト内の policy と contract に対する局所判定であり、"
        "他プロジェクトとの品質水準比較には使えない"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------


def write_evidence(
    *,
    project_root: Path,
    req_id: str,
    phase: str,
    timestamps: Timestamps,
    decision: Decision,
    adopted: list[AdoptedStage],
    results: list[StageResult],
    policy: dict[str, Any] | None,
    keep_runs: int | None = None,
) -> EvidenceWriteResult:
    """Write gate.json / summary.md / stage logs to both trees.

    The volatile copy is written first; the curated copy mirrors it. After
    writing, old volatile run-dirs are pruned per ``QGB_KEEP_RUNS`` (or the
    explicit ``keep_runs`` argument when provided).
    """
    qs = project_root / ".quality-system"
    artifacts = qs / "artifacts" / req_id / "runs"
    # _reserve_run_dir creates run_dir atomically and returns the run_id
    # that actually won the race (timestamps stay as wall-clock truth).
    run_dir, run_id = _reserve_run_dir(artifacts, timestamps)
    (run_dir / "stages").mkdir(parents=False, exist_ok=False)

    curated_root = qs / "evidence" / req_id
    curated_root.mkdir(parents=True, exist_ok=True)
    curated_dir = curated_root / "latest"

    # Paths recorded *inside* gate.json are project-relative POSIX strings.
    run_dir_rel = (
        f".quality-system/artifacts/{req_id}/runs/{timestamps.compact}-{run_id}"
    )
    curated_latest_rel = f".quality-system/evidence/{req_id}/latest"

    basis = build_basis(req_id, policy, adopted)
    gate = build_gate_document(
        req_id=req_id,
        phase=phase,
        timestamps=timestamps,
        run_id=run_id,
        decision=decision,
        adopted=adopted,
        results=results,
        basis=basis,
        run_dir_rel=run_dir_rel,
        curated_latest_rel=curated_latest_rel,
    )

    gate_text = json.dumps(gate, ensure_ascii=False, indent=2) + "\n"
    summary_text = build_summary_md(gate)

    # Volatile copy. Run dir is exclusively owned (reserved by run_id), so
    # direct writes are safe.
    (run_dir / "gate.json").write_text(gate_text, encoding="utf-8")
    (run_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    for r in results:
        (run_dir / "stages" / f"{r.stage_id}.log").write_text(
            r.log_text, encoding="utf-8"
        )

    # Curated copy: atomic swap (Step 6b 項目 2 / Codex Step 5 M4/M5).
    # Stage the full payload into a sibling tmp dir, then swap it into
    # place. This guarantees the curated/latest/ tree is observed only in
    # a consistent state (or absent), never half-written, and that a
    # mid-write failure leaves the previous latest/ intact rather than
    # destroyed (no "stages empty + old gate.json" window, no broken
    # curated/ on Ctrl+C / power loss).
    _atomic_swap_curated(
        curated_root=curated_root,
        run_id=run_id,
        gate_text=gate_text,
        summary_text=summary_text,
        stage_logs=[(r.stage_id, r.log_text) for r in results],
    )

    # Step 7 D: record one ``waiver`` entry per waived stage into
    # knowledge.jsonl. The append is idempotent (an existing entry with
    # the same ``id`` is not duplicated) so repeated runs of the same
    # REQ do not balloon the knowledge file.
    _record_waiver_knowledge(
        qs=qs,
        req_id=req_id,
        adopted=adopted,
        timestamps=timestamps,
    )

    _prune_runs(artifacts, _resolve_keep_runs(keep_runs))

    return EvidenceWriteResult(
        run_dir=run_dir,
        curated_dir=curated_dir,
        gate_path_curated=curated_dir / "gate.json",
        gate_path_volatile=run_dir / "gate.json",
    )


# ---------------------------------------------------------------------------


def _record_waiver_knowledge(
    *,
    qs: Path,
    req_id: str,
    adopted: list[AdoptedStage],
    timestamps: Timestamps,
) -> None:
    """Append one ``waiver`` row per waived stage to ``knowledge.jsonl``.

    Idempotent: an entry whose ``id`` already exists in the file is not
    rewritten. This means re-running the same REQ does not duplicate
    waivers, and a user-edited ``reason`` (Phase 1: hand-editing is the
    only way to update an existing waiver) is preserved.

    The schema is the one ``qgb/schemas/knowledge.schema.json`` defines
    for ``kind: waiver``: ``id``, ``kind``, ``title``, ``source_type``,
    ``created_at``, plus the waiver-specific ``stage_id`` / ``reason`` /
    ``decided_by`` / ``applies_to`` block.

    **Phase 1 audit semantics** (Step 6+7 統合レビュー Codex A4, A8):

    * The ``KNOWLEDGE-WAIVER-<REQ>-<stage>`` row that ``build_basis``
      adds to ``gate.json#basis`` is a **snapshot reference** to this
      file at run time. It is not a live link. If a user hand-edits
      ``knowledge.jsonl`` to remove a waiver entry after the gate was
      written, the historical ``gate.json`` is **not** updated and
      the basis row will reference an id that no longer exists.
      Phase 1 treats ``gate.json`` as the immutable audit record and
      ``knowledge.jsonl`` as the live state; the user is responsible
      for not destroying audit history by removing waivers.
    * Waived stages are **not** re-evaluated if their underlying
      contract / target file changes (Step 6+7 統合レビュー A8). This
      is in alignment with requirements §F-007 ("waived 段階は判定対象
      から除外される") and the philosophy of explicit human-recorded
      decisions. Phase 2 may add waiver expiry, contract hash
      checksums, or revalidation policies; Phase 1 does not.
    * Updating a waiver's reason or removing a waiver in Phase 1 is a
      manual operation: edit ``knowledge.jsonl`` (and the matching
      ``REQ.meta.json`` if removing the waiver entirely), then re-run
      ``qgb run`` so a new ``gate.json`` is written that reflects the
      new state.
    """
    waived_stages = [s for s in adopted if s.waived]
    if not waived_stages:
        return

    knowledge_dir = qs / "knowledge"
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    kjsonl = knowledge_dir / "knowledge.jsonl"

    existing_ids: set[str] = set()
    if kjsonl.is_file():
        for line in kjsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                # Pre-existing malformed line: leave it alone, surface
                # nothing here (validate would flag it on a later run).
                continue
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                existing_ids.add(entry["id"])

    to_append: list[dict[str, Any]] = []
    for stage in waived_stages:
        wid = waiver_knowledge_id(req_id, stage.stage_id)
        if wid in existing_ids:
            continue
        to_append.append(
            {
                "id": wid,
                "kind": "waiver",
                "title": f"Waiver for {req_id} / {stage.stage_id}",
                "applies_to": req_id,
                "stage_id": stage.stage_id,
                "reason": stage.waiver_reason,
                "decided_by": "user",
                "source_type": "user",
                "created_at": timestamps.rfc3339,
            }
        )

    if not to_append:
        return

    # Step 7 補修 (Codex 4): if the existing file ends with a partial
    # line (no trailing newline), naively appending would concatenate
    # our new JSON onto the broken tail, corrupting the new entry too.
    # Prefix a newline in that case so the new entries land on their
    # own lines and remain parseable by the next reader.
    needs_leading_newline = False
    if kjsonl.is_file() and kjsonl.stat().st_size > 0:
        with kjsonl.open("rb") as fh:
            fh.seek(-1, 2)
            needs_leading_newline = fh.read(1) != b"\n"

    # Append-only write. Each entry is one JSON object per line per the
    # ``knowledge.jsonl`` convention.
    with kjsonl.open("a", encoding="utf-8") as fh:
        if needs_leading_newline:
            fh.write("\n")
        for entry in to_append:
            fh.write(json.dumps(entry, ensure_ascii=False))
            fh.write("\n")


# ---------------------------------------------------------------------------


_DEFAULT_KEEP_RUNS = 10


def _resolve_keep_runs(explicit: int | None) -> int:
    """Step 6b 項目 3 (Codex Step 5 L4): warn on invalid QGB_KEEP_RUNS.

    Resolution order:

    * ``explicit`` (test escape hatch) — trust the caller, no validation.
    * ``QGB_KEEP_RUNS`` env var — parse as int. Reject ``< 1``, non-int,
      and whitespace-only strings with a stderr warning and fall back to
      ``_DEFAULT_KEEP_RUNS``.
    * Unset / empty string — silent fall-back to the default.

    Why warn instead of silent: previous behaviour clamped negatives to 1
    and ignored garbage outright, so a typo like ``QGB_KEEP_RUNS=20a`` or
    ``QGB_KEEP_RUNS=-5`` would prune more aggressively than the user
    expected with no signal that the setting was malformed.
    """
    if explicit is not None:
        return max(1, explicit)
    raw = os.environ.get("QGB_KEEP_RUNS")
    if raw is None or raw == "":
        return _DEFAULT_KEEP_RUNS
    stripped = raw.strip()
    if stripped == "":
        _warn_invalid_keep_runs(raw, "empty after stripping whitespace")
        return _DEFAULT_KEEP_RUNS
    try:
        value = int(stripped)
    except ValueError:
        _warn_invalid_keep_runs(raw, "not an integer")
        return _DEFAULT_KEEP_RUNS
    if value < 1:
        _warn_invalid_keep_runs(raw, "must be >= 1")
        return _DEFAULT_KEEP_RUNS
    return value


def _warn_invalid_keep_runs(raw: str, reason: str) -> None:
    print(
        f"qgb: warning: QGB_KEEP_RUNS={raw!r} is invalid ({reason}); "
        f"falling back to default ({_DEFAULT_KEEP_RUNS}).",
        file=sys.stderr,
    )


def _prune_runs(runs_dir: Path, keep: int) -> None:
    """Keep only the ``keep`` most recent run directories under ``runs_dir``.

    Directory names follow ``<compact_timestamp>-<run_id>`` where the
    timestamp leads and ``run_id`` is a zero-padded hex counter, so
    lexical sort = chronological even within the same second.
    """
    if not runs_dir.is_dir():
        return
    children = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    overflow = len(children) - keep
    if overflow <= 0:
        return
    for victim in children[:overflow]:
        shutil.rmtree(victim, ignore_errors=True)


def _recover_orphan_latest(curated_root: Path) -> None:
    """Codex 補修 (Medium 2): startup-time recovery for crash-mid-swap.

    If a previous run was killed between step 2 (``latest`` → ``latest.old-X``)
    and step 3 (``latest.tmp-Y`` → ``latest``), the on-disk state is:

    * ``latest/`` absent
    * one or more ``latest.old-*`` directories present (the last known good)

    Without recovery, the next ``qgb run`` would still produce a fresh
    ``latest/``, but any failure during *its* staging would leave the
    user without curated evidence — even though a recoverable copy
    exists on disk. Promote the most recent ``latest.old-*`` back to
    ``latest/`` before staging so we always have a fallback.

    If multiple ``latest.old-*`` exist, the lexically largest is taken
    as "most recent" — ``run_id`` is a per-second hex counter, so within
    a tight time window this is monotonic enough for the rare crash case.
    Older orphans are deleted.
    """
    final_dir = curated_root / "latest"
    if final_dir.exists():
        return
    orphans = sorted(
        p for p in curated_root.iterdir()
        if p.is_dir() and p.name.startswith("latest.old-")
    )
    if not orphans:
        return
    winner = orphans[-1]
    os.replace(winner, final_dir)
    for victim in orphans[:-1]:
        shutil.rmtree(victim, ignore_errors=True)


def _atomic_swap_curated(
    *,
    curated_root: Path,
    run_id: str,
    gate_text: str,
    summary_text: str,
    stage_logs: list[tuple[str, str]],
) -> None:
    """Atomically replace ``curated_root/latest/`` with a freshly-written tree.

    The sequence is:

    0. Recover from a previous mid-swap crash: if ``latest/`` is absent
       but ``latest.old-*`` is present, restore the most recent old as
       ``latest/`` first.
    1. Write the full payload (``gate.json`` + ``summary.md`` +
       ``stages/<id>.log``) into ``curated_root/latest.tmp-<run_id>/``.
    2. If ``curated_root/latest/`` already exists, rename it to
       ``curated_root/latest.old-<run_id>/``.
    3. Rename ``latest.tmp-<run_id>/`` to ``latest/``.
    4. Best-effort delete ``latest.old-<run_id>/``.

    The only window where ``latest/`` is absent is between step 2 and 3,
    and during that window the content that *will* appear in ``latest/``
    is already fully written on disk. Readers therefore observe either
    "absent" or "fully consistent", never "partial".

    On any failure in step 1, ``latest/`` is untouched and the half-written
    tmp tree is left for inspection (Codex Step 5 M4/M5 rationale: silent
    cleanup hides bugs; explicit residue lets a follow-up ``qgb run``
    overwrite it with the next run_id).

    **Out of scope for Phase 1:** durability across power loss (no
    ``fsync()`` on files / parent dir) and multi-writer concurrency (no
    interprocess lock). Phase 1's contract is single-writer crash
    consistency at the rename layer; readers see either old or new but
    never a partially-built tree. See Codex review note for Phase 2
    durability hardening.

    **Windows note (NF-004):** if an external process (PowerShell host,
    editor, indexer, AV scanner) holds an open handle to a file under
    ``latest/``, step 2 may raise ``PermissionError``. The previous
    ``latest/`` is preserved in that case because the swap aborts before
    moving anything; the staged ``latest.tmp-<run_id>/`` is left on disk
    for the next run or for manual inspection.
    """
    tmp_dir = curated_root / f"latest.tmp-{run_id}"
    old_dir = curated_root / f"latest.old-{run_id}"
    final_dir = curated_root / "latest"

    # 0. Recover from a previous mid-swap crash before staging anything new.
    _recover_orphan_latest(curated_root)

    # If a previous interrupted run left a stale tmp at the same run_id,
    # blow it away first; the new run owns this run_id now.
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 1. Stage the full payload into the tmp dir.
    (tmp_dir / "stages").mkdir(parents=True, exist_ok=False)
    (tmp_dir / "gate.json").write_text(gate_text, encoding="utf-8")
    (tmp_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    for stage_id, log_text in stage_logs:
        (tmp_dir / "stages" / f"{stage_id}.log").write_text(
            log_text, encoding="utf-8"
        )

    # 2. Move the existing latest aside (no-op if it does not exist).
    if final_dir.exists():
        # If an old.<run_id> already exists from a botched prior swap,
        # remove it first so the rename can succeed.
        if old_dir.exists():
            shutil.rmtree(old_dir, ignore_errors=True)
        os.replace(final_dir, old_dir)

    # 3. Swap the staged tmp into place.
    try:
        os.replace(tmp_dir, final_dir)
    except OSError:
        # The swap failed after we already moved the previous latest
        # aside. Restore the previous latest so we never leave the user
        # without curated evidence.
        if old_dir.exists() and not final_dir.exists():
            os.replace(old_dir, final_dir)
        raise

    # 4. Best-effort cleanup of the now-orphaned previous tree.
    if old_dir.exists():
        shutil.rmtree(old_dir, ignore_errors=True)
