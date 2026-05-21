"""READY/NOT_READY judgement for `qgb run` (and the integrity half of validate-policy).

Phase 1 scope (matches requirements doc §6.3.2 and §F-009):

* Run :func:`qgb.core.validate.run_validate` so any schema violation in the
  spec files surfaces here as NOT_READY rather than as an exception inside
  the runner.
* Verify cross-file integrity:
    - the REQ meta file exists and parses,
    - every ``stages[].stage_id`` it cites exists in policy.json,
    - every ``stages[].contract_ref`` resolves to a real file,
    - ``depends_on`` references inside policy.json form a DAG (no cycles,
      no dangling references),
    - the contract's declared verification_type is one Phase 1 understands
      (only ``file_exists`` and ``substring_match`` are runnable; the rest
      are explicitly NOT_READY so we never silently accept the unsupported).
* Reject REQs whose adopted stages are all ``manual_check`` (philosophy P6:
  LLM-only / human-only ALLOW must not happen). Phase 1 treats *any*
  ``manual_check`` in a required adopted stage as NOT_READY.

Out of scope (Step 6 / Step 7):
* Stage-count warning (3-7 recommended range) - validate-policy will emit
  warnings; preflight only fails on errors.
* TDD phase=red expected-failure semantics - Step 7 wiring.

The single :func:`run_preflight` entry point returns a :class:`PreflightReport`
so callers (the runner, ``qgb validate-policy`` later) can format the same
data differently.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from qgb.core.loader import (
    LoaderError,
    load_contract,
    load_policy,
    load_req_meta,
    quality_system_root,
    req_meta_path,
)
from qgb.core.validate import run_validate

PreflightIssueKind = Literal[
    "schema_violation",
    "missing_required_file",
    "invalid_json",
    "unknown_stage_id",
    "missing_contract",
    "depends_on_unknown",
    "depends_on_cycle",
    "unsupported_verification_type",
    "manual_check_required",
    "no_required_stages",
    "verification_type_mismatch",
]


@dataclass(frozen=True)
class PreflightIssue:
    """A single READY/NOT_READY blocker."""

    kind: PreflightIssueKind
    where: str
    message: str


@dataclass
class PreflightReport:
    """Aggregated preflight result.

    ``adopted_stages`` is populated only when the report is ready; it lists
    the ``(policy_stage, req_meta_stage, contract)`` triples the runner will
    execute, in the order REQ meta declares them.
    """

    issues: list[PreflightIssue] = field(default_factory=list)
    adopted_stages: list[AdoptedStage] = field(default_factory=list)
    policy: dict[str, Any] | None = None
    req_meta: dict[str, Any] | None = None

    def ready(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class AdoptedStage:
    """An adopted REQ stage with its resolved policy entry and contract."""

    stage_id: str
    name: str
    verification_type: str
    depends_on: tuple[str, ...]
    contract_ref: str
    contract: dict[str, Any]
    required: bool


# Phase 1 understands these verification types at runtime. Others (command,
# json_schema, manual_check) are scaffolded by the schemas but not runnable
# yet; preflight rejects them so silent ALLOW never happens.
_SUPPORTED_RUNTIME_TYPES: frozenset[str] = frozenset(
    {"file_exists", "substring_match"}
)


# ---------------------------------------------------------------------------


def run_preflight(project_root: Path, req_id: str) -> PreflightReport:
    """Decide whether ``qgb run <req_id>`` may proceed.

    The report's ``issues`` list is empty exactly when execution is safe.
    Callers that want NOT_READY semantics should map ``ready() is False``
    to exit code 2 without writing any gate.json.
    """
    report = PreflightReport()

    # 1) Schema validation of all existing spec files. We run this first so
    #    structural problems do not hide behind integrity issues.
    validate_report = run_validate(project_root)
    for fi in validate_report.schema_issues:
        report.issues.append(
            PreflightIssue(
                kind="schema_violation",
                where=str(fi.file),
                message=(
                    f"{fi.schema_name} {fi.issue.path or '/'}: {fi.issue.message}"
                ),
            )
        )
    for re in validate_report.read_errors:
        report.issues.append(
            PreflightIssue(
                kind="invalid_json",
                where=str(re.file),
                message=re.message,
            )
        )
    for fm in validate_report.field_mismatches:
        report.issues.append(
            PreflightIssue(
                kind="schema_violation",
                where=str(fm.file),
                message=fm.as_message(),
            )
        )

    # 2) Required top-level files. validate is permissive about absence (it
    #    walks "files that exist"), so the missing-file check belongs here.
    qs = quality_system_root(project_root)
    if not (qs / "config.json").is_file():
        report.issues.append(
            PreflightIssue(
                kind="missing_required_file",
                where=str(qs / "config.json"),
                message="config.json is required for qgb run",
            )
        )
    if not (qs / "policy.json").is_file():
        report.issues.append(
            PreflightIssue(
                kind="missing_required_file",
                where=str(qs / "policy.json"),
                message="policy.json is required for qgb run",
            )
        )

    # If anything fundamental is broken, do not try to interpret the policy.
    # Reporting more issues on top of a broken base file is noise.
    if any(
        i.kind in ("missing_required_file", "invalid_json", "schema_violation")
        for i in report.issues
    ):
        return report

    # 3) Load policy + REQ meta. Loader errors surface as preflight issues.
    try:
        policy = load_policy(project_root)
        report.policy = policy
    except LoaderError as exc:
        report.issues.append(
            PreflightIssue(
                kind="invalid_json" if exc.kind == "invalid_json" else "missing_required_file",
                where=str(exc.path),
                message=exc.message,
            )
        )
        return report

    meta_path = req_meta_path(project_root, req_id)
    try:
        req_meta = load_req_meta(project_root, req_id)
        report.req_meta = req_meta
    except LoaderError as exc:
        report.issues.append(
            PreflightIssue(
                kind="missing_required_file" if exc.kind == "missing_file" else "invalid_json",
                where=str(meta_path),
                message=exc.message,
            )
        )
        return report

    # 4) Policy DAG: dangling depends_on or cycles inside policy.json.
    policy_stages = {s["id"]: s for s in policy.get("stages", []) if isinstance(s, dict)}
    for sid, stage in policy_stages.items():
        for dep in stage.get("depends_on", []) or []:
            if dep not in policy_stages:
                report.issues.append(
                    PreflightIssue(
                        kind="depends_on_unknown",
                        where=f"policy.stages[{sid}].depends_on",
                        message=f"stage {sid!r} depends on unknown stage id {dep!r}",
                    )
                )

    cycle = _detect_cycle(policy_stages)
    if cycle is not None:
        report.issues.append(
            PreflightIssue(
                kind="depends_on_cycle",
                where="policy.stages",
                message=f"depends_on graph contains a cycle: {' -> '.join(cycle)}",
            )
        )

    # 5) Walk REQ meta stages and build the adopted-stage list.
    adopted_raw = req_meta.get("stages", []) or []
    if not isinstance(adopted_raw, list) or not adopted_raw:
        report.issues.append(
            PreflightIssue(
                kind="no_required_stages",
                where=str(meta_path),
                message="REQ meta declares no stages; nothing to judge",
            )
        )
        return report

    adopted: list[AdoptedStage] = []
    for entry in adopted_raw:
        if not isinstance(entry, dict):
            continue
        stage_id = entry.get("stage_id")
        contract_ref = entry.get("contract_ref")
        required = bool(entry.get("required", True))

        if not isinstance(stage_id, str) or stage_id not in policy_stages:
            report.issues.append(
                PreflightIssue(
                    kind="unknown_stage_id",
                    where=f"{meta_path}::stage_id={stage_id!r}",
                    message=(
                        f"REQ meta references stage id {stage_id!r} which is not "
                        f"defined in policy.json"
                    ),
                )
            )
            continue

        policy_entry = policy_stages[stage_id]
        vtype = policy_entry.get("verification_type")

        if not isinstance(contract_ref, str):
            report.issues.append(
                PreflightIssue(
                    kind="missing_contract",
                    where=f"{meta_path}::stage_id={stage_id}",
                    message="contract_ref is missing or not a string",
                )
            )
            continue

        try:
            contract = load_contract(project_root, contract_ref)
        except LoaderError as exc:
            report.issues.append(
                PreflightIssue(
                    kind="missing_contract",
                    where=str(exc.path),
                    message=exc.message,
                )
            )
            continue

        # Contract's verification_type must agree with policy's.
        if contract.get("verification_type") != vtype:
            report.issues.append(
                PreflightIssue(
                    kind="verification_type_mismatch",
                    where=contract_ref,
                    message=(
                        f"contract verification_type {contract.get('verification_type')!r} "
                        f"does not match policy stage {stage_id!r} "
                        f"({vtype!r})"
                    ),
                )
            )
            continue

        # manual_check in any required adopted stage means NOT_READY (P6).
        if vtype == "manual_check" and required:
            report.issues.append(
                PreflightIssue(
                    kind="manual_check_required",
                    where=f"policy.stages[{stage_id}]",
                    message=(
                        "stage uses verification_type=manual_check; Phase 1 forbids "
                        "manual_check from being a required ALLOW basis (P6)"
                    ),
                )
            )
            continue

        if vtype not in _SUPPORTED_RUNTIME_TYPES:
            report.issues.append(
                PreflightIssue(
                    kind="unsupported_verification_type",
                    where=f"policy.stages[{stage_id}]",
                    message=(
                        f"verification_type {vtype!r} is not runnable in Phase 1; "
                        f"only {sorted(_SUPPORTED_RUNTIME_TYPES)} are supported"
                    ),
                )
            )
            continue

        adopted.append(
            AdoptedStage(
                stage_id=stage_id,
                name=policy_entry.get("name", stage_id),
                verification_type=vtype,
                depends_on=tuple(policy_entry.get("depends_on", []) or []),
                contract_ref=contract_ref,
                contract=contract,
                required=required,
            )
        )

    if not any(a.required for a in adopted) and not report.issues:
        report.issues.append(
            PreflightIssue(
                kind="no_required_stages",
                where=str(meta_path),
                message="no required stages remain after preflight",
            )
        )

    report.adopted_stages = adopted
    return report


# ---------------------------------------------------------------------------


def _detect_cycle(stages: dict[str, dict[str, Any]]) -> list[str] | None:
    """Return one cycle as ``[a, b, ..., a]`` or ``None``.

    Plain iterative DFS so the call stack never explodes on deep graphs.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {sid: WHITE for sid in stages}

    for root in stages:
        if color[root] != WHITE:
            continue
        # stack entries: (node, iterator over its outgoing edges, path so far)
        stack: list[tuple[str, Iterable[str], list[str]]] = [
            (root, iter(stages[root].get("depends_on", []) or []), [root])
        ]
        color[root] = GRAY
        while stack:
            node, edges, path = stack[-1]
            try:
                nxt = next(edges)
            except StopIteration:
                color[node] = BLACK
                stack.pop()
                continue
            if nxt not in stages:
                # Dangling reference; reported separately as depends_on_unknown.
                continue
            if color[nxt] == GRAY:
                idx = path.index(nxt) if nxt in path else 0
                return path[idx:] + [nxt]
            if color[nxt] == WHITE:
                color[nxt] = GRAY
                stack.append(
                    (
                        nxt,
                        iter(stages[nxt].get("depends_on", []) or []),
                        path + [nxt],
                    )
                )
    return None
