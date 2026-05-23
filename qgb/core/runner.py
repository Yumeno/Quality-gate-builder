"""Execute adopted stages and produce per-stage results.

Phase 1 verification types this module knows how to run:

* ``file_exists``       - the file at ``contract.target`` exists as a regular file.
* ``substring_match``   - the file at ``contract.target`` contains every entry of
                          ``contract.must_contain`` (UTF-8 text).

``command``, ``json_schema`` and ``manual_check`` are deferred to Step 7 / 8;
preflight rejects them before the runner is invoked, so the runner does not
need to handle them.

Dependency handling (Phase 1):

* Stages are executed in the order REQ meta declared them.
* If any of a stage's ``depends_on`` predecessors failed, the stage is
  recorded as ``failed`` with a brief log explaining the skip. This keeps
  the gate schema's "at least one stage failed" invariant trivially true
  while still telling humans which stage was the original cause.

The runner does *not* write files. It only produces in-memory results;
:mod:`qgb.core.evidence` is what serialises them to gate.json / log files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from qgb.core.loader import LoaderError, resolve_project_relative
from qgb.core.preflight import AdoptedStage

StageOutcome = Literal["passed", "failed"]


@dataclass(frozen=True)
class StageResult:
    """In-memory outcome of running a single adopted stage."""

    stage_id: str
    name: str
    verification_type: str
    contract_ref: str
    result: StageOutcome
    exit_code: int | None
    log_text: str


# ---------------------------------------------------------------------------


def run_stages(
    project_root: Path, adopted: list[AdoptedStage]
) -> list[StageResult]:
    """Execute every adopted stage, respecting depends_on for skip-on-failure."""
    results_by_id: dict[str, StageResult] = {}
    out: list[StageResult] = []

    for stage in adopted:
        # If any predecessor failed, mark this stage failed without running.
        failed_dep = next(
            (
                dep
                for dep in stage.depends_on
                if dep in results_by_id and results_by_id[dep].result == "failed"
            ),
            None,
        )
        if failed_dep is not None:
            result = StageResult(
                stage_id=stage.stage_id,
                name=stage.name,
                verification_type=stage.verification_type,
                contract_ref=stage.contract_ref,
                result="failed",
                exit_code=None,
                log_text=(
                    f"stage_id: {stage.stage_id}\n"
                    f"name: {stage.name}\n"
                    f"verification_type: {stage.verification_type}\n"
                    f"contract_ref: {stage.contract_ref}\n\n"
                    f"skipped: predecessor stage {failed_dep!r} failed; "
                    f"this stage is recorded as failed without running.\n"
                    f"result: failed\n"
                ),
            )
        else:
            result = _execute_one(project_root, stage)

        results_by_id[stage.stage_id] = result
        out.append(result)

    return out


# ---------------------------------------------------------------------------


def _execute_one(project_root: Path, stage: AdoptedStage) -> StageResult:
    if stage.verification_type == "file_exists":
        return _run_file_exists(project_root, stage)
    if stage.verification_type == "substring_match":
        return _run_substring_match(project_root, stage)
    # Preflight should have caught unsupported types; this is a defensive guard.
    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result="failed",
        exit_code=None,
        log_text=(
            f"stage_id: {stage.stage_id}\n"
            f"verification_type: {stage.verification_type}\n"
            f"error: this verification_type is not runnable in Phase 1\n"
            f"result: failed\n"
        ),
    )


def _run_file_exists(project_root: Path, stage: AdoptedStage) -> StageResult:
    target = stage.contract.get("target")
    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: file_exists",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        "",
        f"check: {target} exists as a regular file",
    ]

    if not isinstance(target, str) or not target:
        log_lines.append("result: failed (contract.target is missing or empty)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        full = resolve_project_relative(project_root, target, "contract.target")
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    is_regular_file = full.is_file()
    log_lines.append(
        f"resolved: {full}"
    )
    if is_regular_file:
        log_lines.append("result: passed")
        outcome: StageOutcome = "passed"
    else:
        if full.exists():
            log_lines.append(
                "result: failed (path exists but is not a regular file)"
            )
        else:
            log_lines.append("result: failed (file does not exist)")
        outcome = "failed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=None,
        log_text="\n".join(log_lines) + "\n",
    )


def _run_substring_match(project_root: Path, stage: AdoptedStage) -> StageResult:
    target = stage.contract.get("target")
    must_contain = stage.contract.get("must_contain")
    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: substring_match",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        f"must_contain: {must_contain}",
        "",
        "check: every entry of must_contain[] occurs in target file",
    ]

    if (
        not isinstance(target, str)
        or not target
        or not isinstance(must_contain, list)
        or not must_contain
    ):
        log_lines.append(
            "result: failed (contract.target or contract.must_contain is malformed)"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        full = resolve_project_relative(project_root, target, "contract.target")
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    if not full.is_file():
        log_lines.append(f"resolved: {full}")
        log_lines.append("result: failed (target file does not exist)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        text = full.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        log_lines.append(
            f"result: failed (target is not valid UTF-8: {exc})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    missing: list[str] = []
    for keyword in must_contain:
        if not isinstance(keyword, str):
            missing.append(repr(keyword))
            continue
        if keyword in text:
            # Step 6a Commit 3 (Codex L2): the value is a UTF-16 code unit
            # offset in Python (str is a sequence of code points/units, not
            # bytes), so labelling it "byte offset" was misleading. Use
            # "char offset" to match what we actually compute. A real
            # UTF-8 byte offset would require encoding the prefix; that
            # is a Phase 2+ enrichment, not a Step 6 task.
            offset = text.index(keyword)
            log_lines.append(f"- {keyword!r}: found at char offset {offset}")
        else:
            log_lines.append(f"- {keyword!r}: not found")
            missing.append(keyword)

    if missing:
        log_lines.append(f"result: failed (missing keywords: {missing})")
        outcome: StageOutcome = "failed"
    else:
        log_lines.append("result: passed")
        outcome = "passed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=None,
        log_text="\n".join(log_lines) + "\n",
    )
