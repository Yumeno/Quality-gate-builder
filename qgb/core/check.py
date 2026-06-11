"""Daily verification channel: the core of ``qgb check`` (Phase 2 Step 2.4).

``qgb check REQ-ID`` is an **official run rehearsal**: it shares
``run_preflight`` → ``run_stages`` → ``decide`` with ``qgb run`` (DRY, P9)
but never calls :func:`qgb.core.evidence.write_evidence`. Instead a check
writer emits gate.json / summary.md / stage logs to a volatile check dir
only:

    .quality-system/artifacts/<REQ>/checks/<timestamp_utc>-<run_id>/

(設計境界 3、Step 2.4 着手前確定 2026-06-11: check 出力は run の揮発出力と
同種なので既予約の揮発木 ``artifacts/`` に同居させる。)

What check deliberately does NOT do — the boundary that makes it a
rehearsal rather than a gate:

* no curated ``evidence/<REQ>/latest/`` swap,
* no ``knowledge.jsonl`` waiver append,
* no pruning of the official ``runs/`` tree (only its own ``checks/``
  tree is pruned, reusing ``QGB_KEEP_RUNS``),
* no F-008 confirmation prompt (F-008 protects the curated evidence
  mutation; check mutates nothing curated).

Check is **not read-only**: ``verification_type=command`` stages execute
their declared subprocess exactly like ``qgb run`` would — that fidelity
is the rehearsal's value (NF-010: we say "does not update curated
evidence", never "safe" / "read-only").

Knowledge orphan findings are collected as **advisory only** for the
per-REQ path: an orphaned waiver for an unrelated REQ must not block a
daily ``qgb check REQ-B`` (Step 2.3 申し送りの解; P9 — project-wide
orphan enforcement belongs to ``qgb validate-policy`` and to the
REQ-less ``qgb check`` path, both of which use
``validate_policy_preflight``).

Known boundary consequences (段 1 レビューで明文化, Step 2.4):

* **basis fidelity over basis resolvability**: a check gate's ``basis``
  mirrors what an official run *would* record, including
  ``KNOWLEDGE-WAIVER-*`` rows for waived stages. Because check never
  appends to knowledge.jsonl, such a row may reference an id that does
  not exist yet (it will exist after the first official run, which
  appends it). Rehearsal fidelity is the chosen semantics; auditors
  must resolve basis ids against the *official* evidence chain only.
* **prune under Windows file locks**: ``_prune_runs`` uses
  ``shutil.rmtree(ignore_errors=True)``; a check dir held open by a
  scanner/editor/sync engine (this matters under OneDrive) survives one
  prune round and is retried oldest-first on later checks. Transiently
  the checks/ tree may hold more than QGB_KEEP_RUNS entries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from qgb.core.decision import Decision, decide
from qgb.core.evidence import (
    Timestamps,
    _prune_runs,
    _reserve_run_dir,
    _resolve_keep_runs,
    build_basis,
    build_gate_document,
    build_summary_md,
    make_timestamps,
)
from qgb.core.knowledge import OrphanFinding, check_knowledge_orphans
from qgb.core.preflight import AdoptedStage, PreflightReport, run_preflight
from qgb.core.runner import StageResult, run_stages

__all__ = ["CheckOutcome", "run_check", "CHECK_MEANING_NOTE"]


# Appended (space-separated) to the official decision.meaning so a check
# gate can never be mistaken for an official one by a meaning-reading
# consumer. The official meaning strings themselves stay verbatim (F-016)
# for official gates; only check gates carry this suffix.
CHECK_MEANING_NOTE = (
    "[check rehearsal: not an official gate; curated evidence was not "
    "updated]"
)


@dataclass(frozen=True)
class CheckOutcome:
    """Result of the per-REQ ``qgb check`` path.

    ``decision`` / ``gate`` / ``check_dir`` are ``None`` when preflight
    rejected the REQ (NOT_READY) — nothing was executed and nothing was
    written, mirroring ``qgb run``'s behaviour of writing no gate.json
    on a failed preflight.

    ``orphan_findings`` is advisory context (see module docstring); it
    never influences the ALLOW/DENY outcome or whether the check ran.
    """

    preflight: PreflightReport
    orphan_findings: list[OrphanFinding]
    decision: Decision | None
    gate: dict[str, Any] | None
    check_dir: Path | None


def run_check(
    project_root: Path,
    req_id: str,
    *,
    phase: str = "verify",
    keep_runs: int | None = None,
) -> CheckOutcome:
    """Rehearse ``qgb run <req_id>`` without touching curated state.

    Shares the exact preflight function (:func:`run_preflight`), stage
    executor (:func:`run_stages`) and judgement (:func:`decide`) with the
    official runner, so a check verdict predicts the official one for
    the same world state. The only divergences are the writer (volatile
    ``checks/`` dir only) and the decision meaning (suffixed with
    :data:`CHECK_MEANING_NOTE`).
    """
    preflight = run_preflight(project_root, req_id)
    orphan_findings = check_knowledge_orphans(project_root)

    if not preflight.ready_for_run():
        return CheckOutcome(
            preflight=preflight,
            orphan_findings=orphan_findings,
            decision=None,
            gate=None,
            check_dir=None,
        )

    timestamps = make_timestamps()
    results = run_stages(project_root, preflight.adopted_stages)
    official = decide(preflight.adopted_stages, results, phase)
    decision = replace(
        official, meaning=f"{official.meaning} {CHECK_MEANING_NOTE}"
    )

    gate, check_dir = _write_check_artifacts(
        project_root=project_root,
        req_id=req_id,
        phase=phase,
        timestamps=timestamps,
        decision=decision,
        adopted=preflight.adopted_stages,
        results=results,
        policy=preflight.policy,
        keep_runs=keep_runs,
    )
    return CheckOutcome(
        preflight=preflight,
        orphan_findings=orphan_findings,
        decision=decision,
        gate=gate,
        check_dir=check_dir,
    )


def _write_check_artifacts(
    *,
    project_root: Path,
    req_id: str,
    phase: str,
    timestamps: Timestamps,
    decision: Decision,
    adopted: list[AdoptedStage],
    results: list[StageResult],
    policy: dict[str, Any] | None,
    keep_runs: int | None,
) -> tuple[dict[str, Any], Path]:
    """Write gate.json / summary.md / stage logs to the checks tree only.

    Mirrors the volatile half of :func:`qgb.core.evidence.write_evidence`
    (same ``_reserve_run_dir`` collision handling, same file layout, same
    prune policy via ``QGB_KEEP_RUNS``) and deliberately omits the other
    three quarters: curated swap, waiver knowledge append, ``runs/``
    prune. The private evidence helpers are reused on purpose — the
    reservation/prune semantics must stay identical to the official
    writer's, and duplicating them here would let the two drift (P9).
    """
    qs = project_root / ".quality-system"
    checks_root = qs / "artifacts" / req_id / "checks"
    check_dir, run_id = _reserve_run_dir(checks_root, timestamps)
    (check_dir / "stages").mkdir(parents=False, exist_ok=False)

    check_dir_rel = (
        f".quality-system/artifacts/{req_id}/checks/"
        f"{timestamps.compact}-{run_id}"
    )

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
        run_dir_rel=check_dir_rel,
        curated_latest_rel=None,
        mode="check",
    )

    gate_text = json.dumps(gate, ensure_ascii=False, indent=2) + "\n"
    (check_dir / "gate.json").write_text(gate_text, encoding="utf-8")
    (check_dir / "summary.md").write_text(
        build_summary_md(gate), encoding="utf-8"
    )
    for r in results:
        (check_dir / "stages" / f"{r.stage_id}.log").write_text(
            r.log_text, encoding="utf-8"
        )

    _prune_runs(checks_root, _resolve_keep_runs(keep_runs))
    return gate, check_dir
