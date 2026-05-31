"""Step 6a Commit 2 unit tests for the new preflight checks.

These pin the new issue kinds (duplicate_stage_id, misplaced_contract,
missing_contract_field, stage_count_out_of_range, wrong_type) and the
severity behaviour of check_runtime_support's ``mode`` switch.

The composite ``run_preflight`` / ``validate_policy_preflight`` are
exercised in :mod:`tests.test_run_generic_minimal` and (Commit 3) in
``tests.test_validate_policy``. Here we drive the helpers directly to
isolate each check.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qgb.core.loader import load_policy, load_req_meta
from qgb.core.preflight import (
    AdoptedStage,
    PreflightReport,
    check_runtime_support,
    inspect_policy_graph,
    resolve_adopted_stages,
    run_preflight,
    validate_policy_preflight,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


def _copy_generic_minimal(dest: Path) -> Path:
    project = dest / "project"
    shutil.copytree(
        GENERIC_MINIMAL,
        project,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    return project


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ---- duplicate_stage_id --------------------------------------------------


def test_duplicate_stage_id_is_blocker(tmp_path: Path) -> None:
    """Same stage id listed twice in policy.stages is a blocker (P9)."""
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    # Duplicate S1 by re-appending the first stage.
    policy["stages"].append(dict(policy["stages"][0]))
    _write_json(policy_path, policy)

    report = PreflightReport()
    inspect_policy_graph(_read_json(policy_path), report)

    dup = [i for i in report.blocking_issues() if i.kind == "duplicate_stage_id"]
    assert dup, f"expected duplicate_stage_id blocker, got {report.issues}"
    assert "S1" in dup[0].message


# ---- M2 short-circuit: graph integrity blockers stop adopted resolution


def test_duplicate_stage_id_short_circuits_adopted_resolution(
    tmp_path: Path,
) -> None:
    """Step 6a 補修 1 次 (Codex M2): duplicate_stage_id stops downstream resolution.

    With duplicate ids the policy_stages map silently picks the first
    occurrence; any per-stage diagnostic against the duplicated id would
    be ambiguous about which definition was checked. The orchestrator
    short-circuits so the report contains the duplicate blocker but no
    ambiguous secondary findings (e.g. missing_contract_field tied to
    one of the two definitions).
    """
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    policy["stages"].append(dict(policy["stages"][0]))
    _write_json(policy_path, policy)

    report = run_preflight(project, "REQ-APP-001")
    kinds = {i.kind for i in report.blocking_issues()}
    assert "duplicate_stage_id" in kinds
    # No adopted-resolution diagnostics: the resolver was never called.
    assert "missing_contract" not in kinds
    assert "misplaced_contract" not in kinds
    assert "missing_contract_field" not in kinds
    assert "verification_type_mismatch" not in kinds
    assert "depends_on_order_violation" not in kinds
    # No adopted stages were extracted either.
    assert report.adopted_stages == []


def test_depends_on_cycle_short_circuits_adopted_resolution(
    tmp_path: Path,
) -> None:
    """Step 6a 補修 1 次 (Codex M2): cycle in depends_on stops downstream resolution.

    With a cycle the graph is not a DAG; any depends_on_order_violation
    diagnostic becomes ill-defined. Stop after inspect_policy_graph so
    the report keeps only the cycle blocker.
    """
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    # Add a cycle: S1 -> S2 -> S1.
    policy["stages"][0]["depends_on"] = ["S2"]
    _write_json(policy_path, policy)

    report = run_preflight(project, "REQ-APP-001")
    kinds = {i.kind for i in report.blocking_issues()}
    assert "depends_on_cycle" in kinds
    assert "depends_on_order_violation" not in kinds
    assert report.adopted_stages == []


def test_dangling_depends_on_does_not_short_circuit(tmp_path: Path) -> None:
    """Counter-spec to M2: dangling depends_on still permits resolution.

    depends_on_unknown is NOT in the graph-integrity blocker set because
    adopted resolution is still meaningful when only some references are
    dangling — the per-stage diagnostics can complement, not contradict,
    the graph-level finding.
    """
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    policy["stages"][1]["depends_on"] = ["S1", "S999"]  # S999 does not exist
    _write_json(policy_path, policy)

    report = run_preflight(project, "REQ-APP-001")
    kinds = {i.kind for i in report.blocking_issues()}
    assert "depends_on_unknown" in kinds
    # adopted resolution still ran: the REQ has valid contracts so
    # adopted_stages should still be populated.
    assert report.adopted_stages, (
        "dangling depends_on must NOT short-circuit adopted resolution"
    )


# ---- stage_count_out_of_range -------------------------------------------


def test_stage_count_below_three_is_warning(tmp_path: Path) -> None:
    """2-stage policy (generic-minimal) emits a warning, not a blocker."""
    project = _copy_generic_minimal(tmp_path)
    report = PreflightReport()
    policy = load_policy(project)
    inspect_policy_graph(policy, report)

    warnings_ = report.warnings()
    assert any(i.kind == "stage_count_out_of_range" for i in warnings_)
    assert not report.has_blockers()


def test_stage_count_in_range_emits_nothing(tmp_path: Path) -> None:
    """3..7 stages: no advisory."""
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    # Extend to 4 stages by replicating S1 with new ids.
    for i in range(3, 5):
        new = dict(policy["stages"][0])
        new["id"] = f"S{i}"
        new["depends_on"] = []
        policy["stages"].append(new)
    _write_json(policy_path, policy)

    report = PreflightReport()
    inspect_policy_graph(_read_json(policy_path), report)
    assert not any(i.kind == "stage_count_out_of_range" for i in report.issues)


def test_stage_count_above_seven_is_warning(tmp_path: Path) -> None:
    """8+ stages emit the same warning kind as <3."""
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    for i in range(3, 10):  # add S3..S9 → 9 stages total
        new = dict(policy["stages"][0])
        new["id"] = f"S{i}"
        new["depends_on"] = []
        policy["stages"].append(new)
    _write_json(policy_path, policy)

    report = PreflightReport()
    inspect_policy_graph(_read_json(policy_path), report)
    assert any(
        i.kind == "stage_count_out_of_range" and i.severity == "warning"
        for i in report.issues
    )


# ---- misplaced_contract --------------------------------------------------


def test_misplaced_contract_ref_is_blocker(tmp_path: Path) -> None:
    """Non-canonical contract_ref (different directory) is rejected."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    # Move the contract to a non-canonical place.
    orig = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    misplaced = project / ".quality-system" / "contracts" / "REQ-APP-001" / "sub" / "S1.json"
    misplaced.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(orig, misplaced)
    meta["stages"][0]["contract_ref"] = (
        ".quality-system/contracts/REQ-APP-001/sub/S1.json"
    )
    _write_json(meta_path, meta)

    report = run_preflight(project, "REQ-APP-001")
    misplaced_issues = [
        i for i in report.blocking_issues() if i.kind == "misplaced_contract"
    ]
    assert misplaced_issues, f"expected misplaced_contract, got {report.issues}"


def test_misplaced_contract_ref_with_yaml_extension(tmp_path: Path) -> None:
    """Different file extension (.yaml) is also flagged misplaced."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    meta["stages"][0]["contract_ref"] = (
        ".quality-system/contracts/REQ-APP-001/S1.yaml"
    )
    _write_json(meta_path, meta)

    report = run_preflight(project, "REQ-APP-001")
    assert any(
        i.kind == "misplaced_contract" for i in report.blocking_issues()
    ), f"expected misplaced_contract, got {report.issues}"


# ---- missing_contract_field ---------------------------------------------


def test_missing_contract_field_is_blocker(tmp_path: Path) -> None:
    """policy.stages[].required_contract_fields not in contract → blocker."""
    project = _copy_generic_minimal(tmp_path)
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    # Require a field that the existing contract does not have.
    policy["stages"][0]["required_contract_fields"] = [
        "target",
        "nonexistent_field",
    ]
    _write_json(policy_path, policy)

    report = run_preflight(project, "REQ-APP-001")
    missing = [
        i for i in report.blocking_issues() if i.kind == "missing_contract_field"
    ]
    assert missing, f"expected missing_contract_field, got {report.issues}"
    assert "nonexistent_field" in missing[0].message


def test_required_contract_fields_satisfied_emits_no_field_issue(
    tmp_path: Path,
) -> None:
    """Default generic-minimal contracts satisfy declared required_contract_fields."""
    project = _copy_generic_minimal(tmp_path)
    report = run_preflight(project, "REQ-APP-001")
    assert not any(
        i.kind == "missing_contract_field" for i in report.issues
    )


# ---- wrong_type (L3 classification) -------------------------------------


def test_absolute_contract_ref_is_reported_as_misplaced_contract(
    tmp_path: Path,
) -> None:
    """Absolute contract_ref is rejected as misplaced_contract, not wrong_type.

    Step 6a 補修 1 次 (Codex M1) spec lock: the canonical-layout check runs
    BEFORE filesystem resolution, so any contract_ref string that does not
    match the canonical pattern (.quality-system/contracts/<REQ>/<stage>.json)
    is caught as misplaced_contract first and never reaches
    load_contract / resolve_project_relative. This includes:

    * absolute paths (this test)
    * ``..``-relative paths
    * different extensions (``.yaml``)
    * different subdirectory placements

    wrong_type from contract_ref remains reachable only when the
    contract_ref string is itself canonical AND the filesystem entry
    behind it escapes the project root (e.g. canonical S1.json is a
    symlink pointing outside). See
    ``test_root_escape_via_symlink_is_wrong_type``.
    """
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    meta["stages"][0]["contract_ref"] = "/absolute/path/S1.json"
    _write_json(meta_path, meta)

    report = run_preflight(project, "REQ-APP-001")
    blocker_kinds = {i.kind for i in report.blocking_issues()}
    assert "misplaced_contract" in blocker_kinds, blocker_kinds
    # Spec lock: wrong_type must NOT be raised for this case. The
    # canonical-layout check short-circuits before loader sees it.
    assert "wrong_type" not in blocker_kinds, (
        "absolute path must surface as misplaced_contract (cheaper "
        "diagnostic), not wrong_type"
    )


def test_dotdot_contract_ref_is_reported_as_misplaced_contract(
    tmp_path: Path,
) -> None:
    """Same spec as absolute path: ``..``-traversal is misplaced_contract."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    meta["stages"][0]["contract_ref"] = "../escape/S1.json"
    _write_json(meta_path, meta)

    report = run_preflight(project, "REQ-APP-001")
    blocker_kinds = {i.kind for i in report.blocking_issues()}
    assert "misplaced_contract" in blocker_kinds
    assert "wrong_type" not in blocker_kinds


def test_root_escape_via_symlink_is_wrong_type(tmp_path: Path) -> None:
    """Canonical contract_ref + symlinked file escaping the root → wrong_type.

    Step 6a Commit 2 + 補修 1 次 (Codex M1) spec lock: wrong_type from a
    REQ-meta contract_ref is reachable ONLY when the contract_ref string
    itself is canonical AND the filesystem entry behind it escapes the
    project root (e.g. ``S1.json`` is a symlink pointing outside).
    A plain absolute or ``..``-relative path string is caught by the
    earlier canonical-layout pre-check as ``misplaced_contract``; see
    ``test_absolute_contract_ref_is_reported_as_misplaced_contract``.
    """
    project = _copy_generic_minimal(tmp_path)
    meta = load_req_meta(project, "REQ-APP-001")
    policy = load_policy(project)
    policy_stages = inspect_policy_graph(policy, PreflightReport())

    # Forge an entry that passes the canonical-layout pre-check but
    # whose resolution escapes (resolve_project_relative will refuse).
    # The simplest way is to point contract_ref at a canonical-looking
    # path whose actual file is a symlink to outside; the *contract_ref
    # string* still matches canonical layout, so misplaced_contract
    # does not fire. We then let load_contract → resolve_project_relative
    # surface a LoaderError.wrong_type via symlink resolution.
    contract_path = (
        project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    )
    outside = tmp_path / "outside.json"
    outside.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "req_id": "REQ-APP-001",
                "stage_id": "S1",
                "verification_type": "file_exists",
                "target": "sample.txt",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    contract_path.unlink()
    try:
        contract_path.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink not supported on this platform")

    report = PreflightReport()
    resolve_adopted_stages(project, "REQ-APP-001", policy_stages, meta, report)
    wrong = [i for i in report.blocking_issues() if i.kind == "wrong_type"]
    assert wrong, f"expected wrong_type, got {report.issues}"


# ---- check_runtime_support mode switch ----------------------------------


def _make_adopted(
    stage_id: str = "S1",
    verification_type: str = "manual_check",
    required: bool = True,
) -> AdoptedStage:
    return AdoptedStage(
        stage_id=stage_id,
        name=stage_id,
        verification_type=verification_type,
        depends_on=(),
        contract_ref=f".quality-system/contracts/REQ-X/{stage_id}.json",
        contract={},
        required=required,
    )


def test_check_runtime_support_mode_run_emits_blocker_for_manual_check() -> None:
    report = PreflightReport()
    runnable = check_runtime_support(
        [_make_adopted(verification_type="manual_check")], report, mode="run"
    )
    assert runnable == []
    assert report.has_blockers()
    assert any(
        i.kind == "manual_check_required" and i.severity == "blocker"
        for i in report.issues
    )


def test_check_runtime_support_mode_validate_policy_emits_warning() -> None:
    report = PreflightReport()
    runnable = check_runtime_support(
        [_make_adopted(verification_type="manual_check")],
        report,
        mode="validate_policy",
    )
    assert runnable == []
    assert not report.has_blockers()
    assert any(
        i.kind == "manual_check_required" and i.severity == "warning"
        for i in report.issues
    )


def test_check_runtime_support_mode_validate_policy_warns_for_unsupported_type() -> None:
    """Step 7: ``command`` became runtime-supported; ``json_schema``
    remains the canonical unsupported-but-scaffolded type in Phase 1.
    """
    report = PreflightReport()
    runnable = check_runtime_support(
        [_make_adopted(verification_type="json_schema")],
        report,
        mode="validate_policy",
    )
    assert runnable == []
    warnings_ = report.warnings()
    assert any(
        i.kind == "unsupported_verification_type" for i in warnings_
    )
    assert not report.has_blockers()


def test_check_runtime_support_mode_run_blocks_unsupported_type() -> None:
    report = PreflightReport()
    runnable = check_runtime_support(
        [_make_adopted(verification_type="json_schema")],
        report,
        mode="run",
    )
    assert runnable == []
    assert any(
        i.kind == "unsupported_verification_type" and i.severity == "blocker"
        for i in report.issues
    )


# ---- validate_policy_preflight entry point ------------------------------


def test_validate_policy_preflight_without_req(tmp_path: Path) -> None:
    """No req_id: project-wide policy quality only, no REQ-specific checks."""
    project = _copy_generic_minimal(tmp_path)
    report = validate_policy_preflight(project, req_id=None)
    # generic-minimal has only the stage_count_out_of_range advisory.
    assert not report.has_blockers()
    assert any(
        i.kind == "stage_count_out_of_range" for i in report.warnings()
    )
    # REQ meta was not loaded.
    assert report.req_meta is None


def test_validate_policy_preflight_with_req_treats_manual_check_as_warning(
    tmp_path: Path,
) -> None:
    """REQ adopting manual_check stage: warning under validate-policy.

    Driving check_runtime_support directly with synthesized AdoptedStage
    rows isolates the mode switch from the surrounding schema/layout
    checks (manual_check contracts have a different required-field set
    in contract.schema.json, which is not what this test is about).
    The integration path through validate_policy_preflight is covered
    by the schema-aware fixtures added in Step 6a Commit 3.
    """
    report_vp = PreflightReport()
    check_runtime_support(
        [_make_adopted(verification_type="manual_check", required=True)],
        report_vp,
        mode="validate_policy",
    )
    assert any(
        i.kind == "manual_check_required" and i.severity == "warning"
        for i in report_vp.issues
    )
    assert not report_vp.has_blockers()

    report_run = PreflightReport()
    check_runtime_support(
        [_make_adopted(verification_type="manual_check", required=True)],
        report_run,
        mode="run",
    )
    assert any(
        i.kind == "manual_check_required" and i.severity == "blocker"
        for i in report_run.issues
    )
