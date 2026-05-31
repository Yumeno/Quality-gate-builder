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
    "wrong_type",
    "unknown_stage_id",
    "missing_contract",
    "misplaced_contract",
    "missing_contract_field",
    "duplicate_stage_id",
    "depends_on_unknown",
    "depends_on_cycle",
    "depends_on_order_violation",
    "unsupported_verification_type",
    "manual_check_required",
    "no_required_stages",
    "verification_type_mismatch",
    "stage_count_out_of_range",
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
    """An adopted REQ stage with its resolved policy entry and contract.

    Step 7 added ``waived`` / ``waiver_reason``: when the REQ meta sets
    ``waived: true`` (with a non-empty ``waiver_reason`` per the schema),
    the stage is still adopted — its contract is still validated and its
    presence is still recorded — but the runner skips execution, the
    decision treats the stage as judgement-excluded, and a
    ``KNOWLEDGE-WAIVER-<REQ>-<stage>`` entry is added to
    ``gate.json#basis`` plus a ``waiver`` row is appended to
    ``knowledge.jsonl``.
    """

    stage_id: str
    name: str
    verification_type: str
    depends_on: tuple[str, ...]
    contract_ref: str
    contract: dict[str, Any]
    required: bool
    waived: bool = False
    waiver_reason: str = ""


# Phase 1 understands these verification types at runtime. Step 7 added
# ``command``; Step 8 added ``json_schema``. ``manual_check`` is
# run-rejected by design (P6). Preflight rejects unsupported types so
# silent ALLOW never happens.
_SUPPORTED_RUNTIME_TYPES: frozenset[str] = frozenset(
    {"file_exists", "substring_match", "command", "json_schema"}
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
    """Check the policy's stage structure: duplicates, refs, DAG, count range.

    Returns a ``stage_id -> stage_dict`` map so the caller can keep
    using policy stages without re-walking the list. The report
    accumulates:

    * ``duplicate_stage_id`` — same ``id`` repeated (blocker, P9)
    * ``depends_on_unknown`` — depends_on cites a non-existent id (blocker)
    * ``depends_on_cycle`` — depends_on contains a cycle (blocker)
    * ``stage_count_out_of_range`` — outside the recommended 3..7 range
      (warning, P9: a hint that single-responsibility is breaking down,
      not an error per ``stage-design.md`` §9)

    When duplicate ids are present the returned map keeps the first
    occurrence (later occurrences are dropped) so the caller can still
    walk a well-formed map; the duplicate is recorded as a blocker so
    the overall report is rejected before judgement.
    """
    raw_stages = policy.get("stages", []) or []
    policy_stages: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for stage in raw_stages:
        if not isinstance(stage, dict):
            continue
        sid = stage.get("id")
        if not isinstance(sid, str):
            continue
        if sid in seen_ids:
            report.issues.append(
                PreflightIssue(
                    kind="duplicate_stage_id",
                    where=f"policy.stages[{sid}]",
                    message=(
                        f"stage id {sid!r} is declared more than once in "
                        f"policy.json; ids must be unique"
                    ),
                )
            )
            continue
        seen_ids.add(sid)
        policy_stages[sid] = stage

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

    # P9 advisory: outside 3..7 is a warning per stage-design.md §9.
    # Empty policy.stages is a separate matter for validate-policy
    # (Step 6a Commit 3) — the absence of stages is checked by the JSON
    # schema's minItems and by REQ meta's no_required_stages; here we
    # only flag *configured* policies that drift outside the band.
    stage_count = len(policy_stages)
    if stage_count > 0 and (stage_count < 3 or stage_count > 7):
        report.issues.append(
            PreflightIssue(
                kind="stage_count_out_of_range",
                where="policy.stages",
                message=(
                    f"policy declares {stage_count} stage(s); recommended "
                    f"range is 3..7 (stage-design.md section 9). Outside "
                    f"this band is often a single-responsibility smell, "
                    f"not a hard error"
                ),
                severity="warning",
            )
        )

    return policy_stages


def _expected_contract_ref(req_id: str, stage_id: str) -> str:
    """Canonical path of a stage contract relative to project root.

    The canonical layout (``stage-design.md`` §11) is
    ``.quality-system/contracts/<REQ>/<stage>.json``. Anything else (deeper
    nesting, ``.yaml``, files outside ``contracts/<REQ>/``) is rejected
    as ``misplaced_contract`` so validate-policy can flag layout drift
    before runtime confusion sets in.
    """
    return f".quality-system/contracts/{req_id}/{stage_id}.json"


def resolve_adopted_stages(
    project_root: Path,
    req_id: str,
    policy_stages: dict[str, dict[str, Any]],
    req_meta: dict[str, Any],
    report: PreflightReport,
) -> list[AdoptedStage]:
    """Resolve REQ meta entries to (policy, contract) triples.

    Records ``unknown_stage_id`` / ``missing_contract`` /
    ``misplaced_contract`` / ``missing_contract_field`` /
    ``wrong_type`` / ``verification_type_mismatch`` issues per entry and
    skips bad ones. Also checks REQ meta order against ``depends_on``
    (Step 5 三次補修 M1) and emits ``depends_on_order_violation`` when a
    stage appears before one of its adopted predecessors.

    Step 6a Commit 2 added:

    * canonical layout check (``.quality-system/contracts/<REQ>/<stage>.json``)
    * ``required_contract_fields`` (policy) ⊆ contract.json fields
    * ``LoaderError.wrong_type`` (e.g. root escape via symlink) is now
      reported as ``wrong_type`` rather than collapsed into
      ``missing_contract`` so callers can distinguish a missing artefact
      from a malformed reference

    Step 6a 補修 1 次 (Codex M1) — diagnostic priority is *spec*:

    The canonical-layout check runs **before** any filesystem resolution.
    This means any ``contract_ref`` that fails the string match — including
    absolute paths, ``..``-relative paths, ``.yaml`` files, deeper
    subdirectory placements — is recorded as ``misplaced_contract`` and
    NEVER reaches ``load_contract``. As a result:

    * For the REQ-meta ``contract_ref`` path, ``wrong_type`` is only
      reachable when the ``contract_ref`` string is canonical-looking
      AND a filesystem-level escape happens at resolve time (e.g.
      ``S1.json`` is a symlink pointing outside the project root).
      A plain absolute path string is caught by ``misplaced_contract``
      first.
    * ``wrong_type`` remains the kind for policy/REQ meta loader errors
      where the JSON itself is not an object (see
      ``_loader_kind_for_policy`` / ``_loader_kind_for_meta``).

    Why canonical-layout check goes first — *limited to this case*: the
    layout violation is decided by a stable textual comparison, with no
    I/O and no dependence on filesystem state; the same input always
    gives the same diagnostic, and the designer sees the cheapest fix
    (rename / move the contract). Both findings indicate a contract
    that ``qgb run`` will refuse, but the textual one points at the
    smallest change (P9: each error should point at the smallest change
    that resolves it).

    This is **not** a general "cheaper diagnostic first" principle for
    all preflight checks. When safety, ambiguity, or downstream
    diagnostic pollution is at stake, the order must favour
    "uncontaminated diagnostics first" instead — see ``run_preflight``'s
    graph-integrity short-circuit (Codex M2) for the opposite trade-off,
    where blockers like ``duplicate_stage_id`` suppress *more* findings
    on purpose. The canonical-layout case earns its ordering specifically
    because the textual violation is decisive on its own and does not
    affect any later finding's validity.
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
        waived = bool(entry.get("waived", False))
        waiver_reason = entry.get("waiver_reason", "") or ""

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

        # Canonical layout: contract_ref must be exactly the
        # .quality-system/contracts/<REQ>/<stage>.json shape. Step 6a
        # surfaces drift (e.g. nested subdirectory, .yaml, different
        # REQ folder) as misplaced_contract. This is a blocker for both
        # qgb run (the runner has no policy for non-canonical layouts)
        # and validate-policy (P7: structure must be predictable).
        expected_ref = _expected_contract_ref(req_id, stage_id)
        ref_norm = contract_ref.replace("\\", "/")
        if ref_norm != expected_ref:
            report.issues.append(
                PreflightIssue(
                    kind="misplaced_contract",
                    where=f"{meta_path}::stage_id={stage_id}",
                    message=(
                        f"contract_ref {contract_ref!r} is not the canonical "
                        f"layout {expected_ref!r} "
                        f"(stage-design.md section 11)"
                    ),
                )
            )
            continue

        try:
            contract = load_contract(project_root, contract_ref)
        except LoaderError as exc:
            # L3: distinguish "the spec is malformed" (wrong_type:
            # absolute path, root escape) from "the artefact is
            # missing" (missing_file). Both block ``qgb run`` but the
            # remediation differs, and validate-policy needs the
            # distinction for accurate diagnostics.
            kind: PreflightIssueKind = (
                "wrong_type" if exc.kind == "wrong_type" else "missing_contract"
            )
            report.issues.append(
                PreflightIssue(
                    kind=kind,
                    where=str(exc.path),
                    message=exc.message,
                )
            )
            continue

        # Step 6a Commit 2: policy.stages[].required_contract_fields ⊆
        # contract.json keys. The schema validator (qgb validate) only
        # knows per-verification-type required fields (F-005); the
        # policy-declared "fields this REQ must populate" check is the
        # *cross-file* integrity that belongs to validate-policy /
        # preflight, not to the per-file schema.
        required_fields = policy_entry.get("required_contract_fields", []) or []
        if isinstance(required_fields, list):
            missing = [
                fname for fname in required_fields
                if isinstance(fname, str) and fname not in contract
            ]
            if missing:
                report.issues.append(
                    PreflightIssue(
                        kind="missing_contract_field",
                        where=contract_ref,
                        message=(
                            f"contract is missing fields declared in "
                            f"policy.stages[{stage_id}].required_contract_fields: "
                            f"{missing}"
                        ),
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
                waived=waived,
                waiver_reason=waiver_reason,
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


PreflightMode = Literal["run", "validate_policy"]


def check_runtime_support(
    adopted: list[AdoptedStage],
    report: PreflightReport,
    *,
    mode: PreflightMode = "run",
) -> list[AdoptedStage]:
    """Drop stages ``qgb run`` cannot execute in Phase 1.

    This is the boundary where ``qgb run`` and ``qgb validate-policy``
    diverge:

    * ``mode="run"`` (default, used by :func:`run_preflight`) treats
      ``manual_check_required`` and ``unsupported_verification_type``
      as **blocker** — the runner cannot execute these stages.
    * ``mode="validate_policy"`` treats both as **warning** — the
      policy itself is not malformed; Phase 1 runtime simply does not
      execute those types yet (Step 7+). validate-policy reports them
      so the designer knows ``qgb run`` will reject the REQ, but the
      design check itself does not fail.

    Either way, the affected stage is dropped from the returned
    runnable list so callers that only consume the list (the runner)
    do not need to filter again.

    The ``mode`` boundary keeps P9 (single-responsibility): the same
    finding can mean different things to different commands, but the
    finding itself is recorded once with the right severity, not
    duplicated under two issue kinds.
    """
    severity: PreflightSeverity = (
        "warning" if mode == "validate_policy" else "blocker"
    )
    runnable: list[AdoptedStage] = []
    for stage in adopted:
        # Step 7: a waived stage is never executed, so its
        # verification_type is irrelevant for runtime support. The
        # runner will short-circuit it to result=waived, and the
        # decision excludes it from judgement. Keep it in the returned
        # list so the runner / evidence layer can still emit a
        # "waived" stage entry in gate.json and add the
        # KNOWLEDGE-WAIVER-* basis. Without this, a waived
        # manual_check would still be flagged as
        # ``manual_check_required`` and block ``qgb run`` even though
        # the user explicitly waived it (P6 is preserved because the
        # waiver is recorded in knowledge.jsonl with a reason and
        # decided_by).
        if stage.waived:
            runnable.append(stage)
            continue
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
                    severity=severity,
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
                    severity=severity,
                )
            )
            continue
        runnable.append(stage)
    return runnable


def run_preflight(project_root: Path, req_id: str) -> PreflightReport:
    """Decide whether ``qgb run <req_id>`` may proceed.

    Thin orchestrator over :func:`validate_schema_sources`,
    :func:`inspect_policy_graph`, :func:`resolve_adopted_stages`, and
    :func:`check_runtime_support` (mode="run"). Step 6a
    :func:`validate_policy_preflight` reuses the same helpers with
    different short-circuit rules and mode="validate_policy".

    Callers that want NOT_READY semantics should map
    ``ready_for_run() is False`` to exit code 2 without writing any
    gate.json. Warnings alone do not stop the runner.
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
                kind=_loader_kind_for_policy(exc.kind),
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
                kind=_loader_kind_for_meta(exc.kind),
                where=str(meta_path),
                message=exc.message,
            )
        )
        return report

    policy_stages = inspect_policy_graph(policy, report)
    # Step 6a 補修 1 次 (Codex M2): if the policy graph itself is
    # corrupt (duplicate ids, dependency cycles), adopted resolution
    # would silently pick the first stage definition for any duplicated
    # id and walk a graph that may not be a DAG. Both produce ambiguous
    # secondary diagnostics that obscure the primary fix. Stop here so
    # the report contains only first-order findings. The runner is
    # NOT_READY regardless because graph errors are blockers.
    if _has_graph_integrity_blockers(report):
        return report

    adopted = resolve_adopted_stages(
        project_root, req_id, policy_stages, req_meta, report
    )
    adopted = check_runtime_support(adopted, report, mode="run")

    # Phase 1 treats every adopted stage as judgement material (see
    # decision.py for the rationale). An REQ with zero adopted stages
    # after preflight has nothing to judge and must be NOT_READY.
    #
    # Step 6a Commit 2: the gate is "no blockers were recorded", not
    # "no issues at all" — a warning-only report still represents a
    # real failure to extract any runnable stage and must surface as
    # NOT_READY (e.g. stage_count_out_of_range alone shouldn't
    # synthesize this issue, but a manual_check-only REQ would, even
    # though manual_check is recorded as a blocker; the condition is
    # captured by has_blockers()).
    if not adopted and not report.has_blockers():
        report.issues.append(
            PreflightIssue(
                kind="no_required_stages",
                where=str(meta_path),
                message="no adopted stages remain after preflight",
            )
        )

    report.adopted_stages = adopted
    return report


def validate_policy_preflight(
    project_root: Path, req_id: str | None = None
) -> PreflightReport:
    """Run the design-quality preflight for ``qgb validate-policy``.

    Differences from :func:`run_preflight`:

    * No specific REQ is required. When ``req_id`` is None, only the
      policy graph and schema integrity are checked (project-wide
      design quality). When ``req_id`` is provided, the same REQ-level
      checks as ``run`` are performed, but ``check_runtime_support``
      is invoked with ``mode="validate_policy"`` so unsupported
      verification_type / manual_check become warnings.
    * Schema / policy load failures stop further checks (same as run),
      because they make downstream interpretation meaningless.

    Returns a :class:`PreflightReport`. Callers should use
    :meth:`PreflightReport.has_blockers` (not ``ready_for_run``) to
    decide exit status: blockers → exit 2 (NOT_READY), warnings only
    → exit 0 + stderr advisory.
    """
    report = PreflightReport()

    validate_schema_sources(project_root, report)
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
                kind=_loader_kind_for_policy(exc.kind),
                where=str(exc.path),
                message=exc.message,
            )
        )
        return report

    policy_stages = inspect_policy_graph(policy, report)

    if req_id is None:
        # Project-wide check: policy graph quality only.
        return report

    # Same short-circuit as run_preflight (Codex M2): graph integrity
    # blockers make REQ-level resolution ambiguous; stop before adopted
    # resolution so the report keeps first-order diagnostics.
    if _has_graph_integrity_blockers(report):
        return report

    meta_path = req_meta_path(project_root, req_id)
    try:
        req_meta = load_req_meta(project_root, req_id)
        report.req_meta = req_meta
    except LoaderError as exc:
        report.issues.append(
            PreflightIssue(
                kind=_loader_kind_for_meta(exc.kind),
                where=str(meta_path),
                message=exc.message,
            )
        )
        return report

    adopted = resolve_adopted_stages(
        project_root, req_id, policy_stages, req_meta, report
    )
    adopted = check_runtime_support(adopted, report, mode="validate_policy")
    report.adopted_stages = adopted
    return report


def _loader_kind_for_policy(loader_kind: str) -> PreflightIssueKind:
    """Map LoaderError.kind onto preflight kinds for policy/config reads."""
    if loader_kind == "invalid_json":
        return "invalid_json"
    if loader_kind == "wrong_type":
        return "wrong_type"
    return "missing_required_file"


def _loader_kind_for_meta(loader_kind: str) -> PreflightIssueKind:
    """Map LoaderError.kind onto preflight kinds for REQ meta reads."""
    if loader_kind == "invalid_json":
        return "invalid_json"
    if loader_kind == "wrong_type":
        return "wrong_type"
    return "missing_required_file"


# Step 6a 補修 1 次 (Codex M2): graph-integrity blockers that make
# downstream REQ-level resolution unsafe to attempt. duplicate_stage_id
# means the policy_stages map silently picked the first occurrence
# (any required_contract_fields / contract_ref check would be against
# whichever stage definition won the tie); depends_on_cycle means the
# graph is not a DAG so depends_on_order_violation diagnostics become
# ill-defined. depends_on_unknown is intentionally NOT in this set —
# adopted resolution is still meaningful when only some references are
# dangling, so we let the per-stage diagnostics surface alongside.
#
# Why the short-circuit also applies to ``validate_policy_preflight``
# (Codex 二次レビュー反映): ``qgb validate-policy`` does try to report
# *all* design quality findings, which would normally argue against
# suppressing diagnostics. But "all findings" only helps when each
# finding is correct in isolation. With ``duplicate_stage_id``,
# downstream per-stage diagnostics cite a stage_id whose definition is
# ambiguous; with ``depends_on_cycle``, ordering-aware diagnostics
# become meaningless. Reporting wrong / unstable findings on top of a
# correct primary finding *degrades* design quality feedback rather
# than enriching it. The trade-off is intentional: fix the integrity
# blocker first, then re-run validate-policy to surface the next layer.
_GRAPH_INTEGRITY_BLOCKER_KINDS: frozenset[PreflightIssueKind] = frozenset(
    {"duplicate_stage_id", "depends_on_cycle"}
)


def _has_graph_integrity_blockers(report: PreflightReport) -> bool:
    return any(
        i.kind in _GRAPH_INTEGRITY_BLOCKER_KINDS
        for i in report.iter_issues("blocker")
    )


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
