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
    - Updated by ``qgb run`` only (not by ``qgb verify``).
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
    """Phase 1 ``basis[]`` per detailed-design.md §7.5."""
    policy_id = "default"
    if policy and isinstance(policy.get("policy_id"), str):
        policy_id = policy["policy_id"]
    out = [req_id, f"POLICY-{policy_id}"]
    out.extend(f"CONTRACT-{req_id}-{stage.stage_id}" for stage in adopted)
    return out


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
    """Assemble the dict that becomes gate.json (both copies)."""
    stages_payload: list[dict[str, Any]] = []
    results_by_id = {r.stage_id: r for r in results}
    for stage in adopted:
        r = results_by_id.get(stage.stage_id)
        if r is None:
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
    else:
        lines.append(
            f"必須段階 `{gate['failed_stage']}` が failed のため、status=DENY。"
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

    curated_dir = qs / "evidence" / req_id / "latest"
    curated_dir.mkdir(parents=True, exist_ok=True)
    (curated_dir / "stages").mkdir(parents=True, exist_ok=True)

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

    # Volatile copy.
    (run_dir / "gate.json").write_text(gate_text, encoding="utf-8")
    (run_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    for r in results:
        (run_dir / "stages" / f"{r.stage_id}.log").write_text(
            r.log_text, encoding="utf-8"
        )

    # Curated copy. Clear stage logs first so a leftover log from a removed
    # stage cannot survive into a new run.
    _replace_dir_contents(curated_dir / "stages")
    (curated_dir / "gate.json").write_text(gate_text, encoding="utf-8")
    (curated_dir / "summary.md").write_text(summary_text, encoding="utf-8")
    for r in results:
        (curated_dir / "stages" / f"{r.stage_id}.log").write_text(
            r.log_text, encoding="utf-8"
        )

    _prune_runs(artifacts, _resolve_keep_runs(keep_runs))

    return EvidenceWriteResult(
        run_dir=run_dir,
        curated_dir=curated_dir,
        gate_path_curated=curated_dir / "gate.json",
        gate_path_volatile=run_dir / "gate.json",
    )


# ---------------------------------------------------------------------------


_DEFAULT_KEEP_RUNS = 10


def _resolve_keep_runs(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, explicit)
    raw = os.environ.get("QGB_KEEP_RUNS")
    if raw is None or raw == "":
        return _DEFAULT_KEEP_RUNS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_KEEP_RUNS
    return max(1, value)


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


def _replace_dir_contents(target: Path) -> None:
    if target.exists() and target.is_dir():
        for entry in target.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                try:
                    entry.unlink()
                except OSError:
                    pass
    else:
        target.mkdir(parents=True, exist_ok=True)
