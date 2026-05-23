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

from collections.abc import Iterable, Iterator
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
    "depends_on_order_violation",
    "unsupported_verification_type",
    "manual_check_required",
    "no_required_stages",
    "verification_type_mismatch",
]


PreflightSeverity = Literal["blocker", "warning"]


@dataclass(frozen=True)
class PreflightIssue:
    """A single preflight finding.

    ``severity`` distinguishes a hard blocker (``qgb run`` must return
    NOT_READY) from an advisory warning (Step 6 ``qgb validate-policy``
    surfaces it but the run could still proceed). Step 5 三次補修
    introduces the field as a future-compatible default of ``"blocker"``;
    no Phase 1 caller emits ``"warning"`` yet, and the runner treats any
    non-empty issue list as NOT_READY regardless of severity.
    """

    kind: PreflightIssueKind
    where: str
    message: str
    severity: PreflightSeverity = "blocker"


@dataclass
class PreflightReport:
    """Aggregated preflight result.

    ``adopted_stages`` is populated only when the report is ready; it lists
    the ``(policy_stage, req_meta_stage, contract)`` triples the runner will
    execute, in the order REQ meta declares them.

    Step 6a (validate-policy への共通土台) で診断 API を整理:

    * 主 API は :meth:`iter_issues` (severity フィルタ可)。
    * :meth:`blocking_issues` / :meth:`warnings` / :meth:`has_blockers` は
      便利メソッド。
    * :meth:`ready_for_run` は ``qgb run`` 専用の意味 ("blocker が一つも
      なければ run を続行できる") を持つ。``qgb validate-policy`` は
      blocker と warning を区別して報告するので
      :meth:`has_blockers` を使う (P9: 失敗モードを混ぜない)。
    * :meth:`ready` は Step 5 までの後方互換。新規コードでは使わない。
    """

    issues: list[PreflightIssue] = field(default_factory=list)
    adopted_stages: list[AdoptedStage] = field(default_factory=list)
    policy: dict[str, Any] | None = None
    req_meta: dict[str, Any] | None = None

    def iter_issues(
        self, severity: PreflightSeverity | None = None
    ) -> Iterator[PreflightIssue]:
        """Iterate over issues, optionally filtered by severity.

        ``severity=None`` yields every issue. Pass ``"blocker"`` or
        ``"warning"`` to filter. Iteration preserves the order issues
        were appended, which matters because :func:`run_preflight`
        records them in the order it discovers them (schema first, then
        graph, then resolution, then runtime support).
        """
        if severity is None:
            yield from self.issues
            return
        for issue in self.issues:
            if issue.severity == severity:
                yield issue

    def blocking_issues(self) -> list[PreflightIssue]:
        """Return the subset of issues with ``severity="blocker"``."""
        return list(self.iter_issues("blocker"))

    def warnings(self) -> list[PreflightIssue]:
        """Return the subset of issues with ``severity="warning"``."""
        return list(self.iter_issues("warning"))

    def has_blockers(self) -> bool:
        """True iff at least one blocker is present.

        Used by ``qgb validate-policy``: a report with only warnings is
        still considered a successful design check (exit 0) while
        blockers must surface as exit 2 (NOT_READY).
        """
        return any(i.severity == "blocker" for i in self.issues)

    def ready_for_run(self) -> bool:
        """True iff ``qgb run`` may proceed.

        Phase 1 semantics: ``run`` treats every blocker as fatal and
        ignores warnings (there are no warnings yet, but the contract
        survives Step 6b's introduction of them). This is the *only*
        place where the runner consults the report: callers that map
        the result to NOT_READY/exit 2 should call this method.
        """
        return not self.has_blockers()

    def ready(self) -> bool:
        """Deprecated alias kept for Step 5 callers.

        Equivalent to :meth:`ready_for_run` while Phase 1 has no
        warnings. New code should call :meth:`ready_for_run` (run path)
        or :meth:`has_blockers` (validate-policy path) directly so the
        intent is explicit at the call site.
        """
        return self.ready_for_run()


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
# Step 5 三次補修 (B partial): preflight is decomposed into five
# functions so that ``qgb validate-policy`` (Step 6) can reuse the same
# building blocks under a different orchestration. ``run_preflight``
# becomes a thin orchestrator that wires them in the order
# ``qgb run`` needs. The function boundaries are *provisional* in
# Phase 1; Step 6 may adjust them as validate-policy's needs come into
# focus. Each helper appends to a passed-in :class:`PreflightReport`
# rather than returning issues, so callers can layer multiple stages
# into the same report without losing earlier findings.
# ---------------------------------------------------------------------------


def validate_schema_sources(
    project_root: Path, report: PreflightReport
) -> None:
    """Schema-validate every spec file under ``.quality-system/``.

    Maps :class:`qgb.core.validate.ValidateReport` problems onto
    preflight issue kinds so the caller sees a single homogeneous list.
    """
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


def inspect_policy_graph(
    policy: dict[str, Any], report: PreflightReport
) -> dict[str, dict[str, Any]]:
    """Check the policy's depends_on graph for dangling refs and cycles.

    Returns a ``stage_id -> stage_dict`` map so the caller can keep
    using policy stages without re-walking the list. The report
    accumulates ``depends_on_unknown`` and ``depends_on_cycle`` issues.
    """
    policy_stages = {
        s["id"]: s for s in policy.get("stages", []) if isinstance(s, dict)
    }
    for sid, stage in policy_stages.items():
        for dep in stage.get("depends_on", []) or []:
            if dep not in policy_stages:
                report.issues.append(
                    PreflightIssue(
                        kind="depends_on_unknown",
                        where=f"policy.stages[{sid}].depends_on",
                        message=(
                            f"stage {sid!r} depends on unknown stage id {dep!r}"
                        ),
                    )
                )

    cycle = _detect_cycle(policy_stages)
    if cycle is not None:
        report.issues.append(
            PreflightIssue(
                kind="depends_on_cycle",
                where="policy.stages",
                message=(
                    f"depends_on graph contains a cycle: {' -> '.join(cycle)}"
                ),
            )
        )

    return policy_stages


def resolve_adopted_stages(
    project_root: Path,
    req_id: str,
    policy_stages: dict[str, dict[str, Any]],
    req_meta: dict[str, Any],
    report: PreflightReport,
) -> list[AdoptedStage]:
    """Resolve REQ meta entries to (policy, contract) triples.

    Records ``unknown_stage_id`` / ``missing_contract`` /
    ``verification_type_mismatch`` issues per entry and skips bad ones.
    Also checks REQ meta order against ``depends_on`` (Step 5 三次補修
    M1) and emits ``depends_on_order_violation`` when a stage appears
    before one of its adopted predecessors.
    """
    meta_path = req_meta_path(project_root, req_id)
    adopted_raw = req_meta.get("stages", []) or []
    if not isinstance(adopted_raw, list) or not adopted_raw:
        report.issues.append(
            PreflightIssue(
                kind="no_required_stages",
                where=str(meta_path),
                message="REQ meta declares no stages; nothing to judge",
            )
        )
        return []

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
                        f"REQ meta references stage id {stage_id!r} which is "
                        f"not defined in policy.json"
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

        if contract.get("verification_type") != vtype:
            report.issues.append(
                PreflightIssue(
                    kind="verification_type_mismatch",
                    where=contract_ref,
                    message=(
                        f"contract verification_type "
                        f"{contract.get('verification_type')!r} does not match "
                        f"policy stage {stage_id!r} ({vtype!r})"
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

    # M1: REQ meta order must satisfy depends_on among adopted stages.
    adopted_ids = {a.stage_id for a in adopted}
    seen: set[str] = set()
    for adopted_stage in adopted:
        for dep in adopted_stage.depends_on:
            if dep not in policy_stages:
                continue
            if dep not in adopted_ids:
                continue
            if dep not in seen:
                report.issues.append(
                    PreflightIssue(
                        kind="depends_on_order_violation",
                        where=(
                            f"{meta_path}::stage_id={adopted_stage.stage_id}"
                        ),
                        message=(
                            f"stage {adopted_stage.stage_id!r} appears before "
                            f"its adopted dependency {dep!r} in REQ meta; "
                            f"reorder stages[] so dependencies come first"
                        ),
                    )
                )
        seen.add(adopted_stage.stage_id)

    return adopted


def check_runtime_support(
    adopted: list[AdoptedStage], report: PreflightReport
) -> list[AdoptedStage]:
    """Drop stages ``qgb run`` cannot execute in Phase 1.

    This is the boundary where ``qgb run`` and ``qgb validate-policy``
    diverge: for ``qgb run`` an unsupported verification_type is a
    blocker (we can't actually run it); for ``qgb validate-policy``
    (Step 6) the same finding will be a warning ("Phase 1 runtime won't
    execute this, but the policy itself isn't malformed"). Step 5 leaves
    both as ``severity="blocker"``; Step 6 will introduce the warning
    variant.
    """
    runnable: list[AdoptedStage] = []
    for stage in adopted:
        vtype = stage.verification_type
        if vtype == "manual_check" and stage.required:
            report.issues.append(
                PreflightIssue(
                    kind="manual_check_required",
                    where=f"policy.stages[{stage.stage_id}]",
                    message=(
                        "stage uses verification_type=manual_check; Phase 1 "
                        "forbids manual_check from being a required ALLOW "
                        "basis (P6)"
                    ),
                )
            )
            continue
        if vtype not in _SUPPORTED_RUNTIME_TYPES:
            report.issues.append(
                PreflightIssue(
                    kind="unsupported_verification_type",
                    where=f"policy.stages[{stage.stage_id}]",
                    message=(
                        f"verification_type {vtype!r} is not runnable in "
                        f"Phase 1; only "
                        f"{sorted(_SUPPORTED_RUNTIME_TYPES)} are supported"
                    ),
                )
            )
            continue
        runnable.append(stage)
    return runnable


def run_preflight(project_root: Path, req_id: str) -> PreflightReport:
    """Decide whether ``qgb run <req_id>`` may proceed.

    Thin orchestrator over :func:`validate_schema_sources`,
    :func:`inspect_policy_graph`, :func:`resolve_adopted_stages`, and
    :func:`check_runtime_support`. Step 6 ``qgb validate-policy`` will
    reuse the same helpers with different short-circuit rules.

    The report's ``issues`` list is empty exactly when execution is
    safe. Callers that want NOT_READY semantics should map
    ``ready() is False`` to exit code 2 without writing any gate.json.
    """
    report = PreflightReport()

    validate_schema_sources(project_root, report)

    # If anything fundamental is broken, do not try to interpret the
    # policy. Reporting more issues on top of a broken base file is noise.
    if any(
        i.kind in ("missing_required_file", "invalid_json", "schema_violation")
        for i in report.issues
    ):
        return report

    try:
        policy = load_policy(project_root)
        report.policy = policy
    except LoaderError as exc:
        report.issues.append(
            PreflightIssue(
                kind=(
                    "invalid_json" if exc.kind == "invalid_json"
                    else "missing_required_file"
                ),
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
                kind=(
                    "missing_required_file" if exc.kind == "missing_file"
                    else "invalid_json"
                ),
                where=str(meta_path),
                message=exc.message,
            )
        )
        return report

    policy_stages = inspect_policy_graph(policy, report)
    adopted = resolve_adopted_stages(
        project_root, req_id, policy_stages, req_meta, report
    )
    adopted = check_runtime_support(adopted, report)

    # Phase 1 treats every adopted stage as judgement material (see
    # decision.py for the rationale). An REQ with zero adopted stages
    # after preflight has nothing to judge and must be NOT_READY.
    if not adopted and not report.issues:
        report.issues.append(
            PreflightIssue(
                kind="no_required_stages",
                where=str(meta_path),
                message="no adopted stages remain after preflight",
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
