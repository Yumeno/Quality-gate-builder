"""Tests that the bundled examples stay consistent with the schemas and themselves.

Phase 1 currently ships one hand-written example (Step 4):
``examples/generic-minimal/``. This module enforces three layers of guard:

1. Schema validity: ``qgb validate`` of the example must succeed.
2. Strict curated gate.json conformance.
3. Cross-file integrity (policy <-> REQ meta <-> contract <-> gate.json).

(3) is the contract that Step 5's ``qgb run`` implementation must keep
honouring; if a future change drifts one of these files, CI fails here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from qgb.core.schema import validate as schema_validate
from qgb.core.validate import run_validate

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"
GENERIC_MINIMAL = EXAMPLES / "generic-minimal"
QS = GENERIC_MINIMAL / ".quality-system"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _policy() -> dict:
    return _read_json(QS / "policy.json")


def _req_meta() -> dict:
    return _read_json(QS / "req" / "REQ-APP-001.meta.json")


def _contracts() -> dict[str, dict]:
    base = QS / "contracts" / "REQ-APP-001"
    return {p.stem: _read_json(p) for p in sorted(base.glob("*.json"))}


def _gate() -> dict:
    return _read_json(
        QS / "evidence" / "REQ-APP-001" / "latest" / "gate.json"
    )


# ---- Layer 1: schema validity --------------------------------------------


def test_generic_minimal_validates_under_qgb_validate() -> None:
    """Step 5 precondition: the hand-written example must pass qgb validate."""
    report = run_validate(GENERIC_MINIMAL)
    assert not report.has_problems(), report
    # config / policy / 1 REQ meta / 2 contracts = 5 spec files.
    assert len(report.files_checked) == 5
    schema_names = sorted(name for _, name in report.files_checked)
    assert schema_names == ["config", "contract", "contract", "policy", "req-meta"]


# ---- Layer 2: curated gate.json conformance ------------------------------


def test_generic_minimal_curated_gate_conforms_to_strict_schema() -> None:
    """The hand-written gate.json acts as the Step 5 reference output."""
    issues = schema_validate(_gate(), "gate")
    assert not issues, [f"{i.path}: {i.message}" for i in issues]


# ---- Layer 3: cross-file integrity (Codex review item 3) -----------------


def test_req_meta_stage_ids_match_policy_stage_ids() -> None:
    policy_ids = {s["id"] for s in _policy()["stages"]}
    meta_ids = {s["stage_id"] for s in _req_meta()["stages"]}
    assert meta_ids.issubset(policy_ids), (
        f"REQ meta references stage ids not present in policy: "
        f"{meta_ids - policy_ids}"
    )


def test_req_meta_contract_refs_resolve_to_real_files() -> None:
    for stage in _req_meta()["stages"]:
        contract_path = GENERIC_MINIMAL / stage["contract_ref"]
        assert contract_path.is_file(), (
            f"contract_ref does not resolve: {stage['contract_ref']}"
        )


def test_contracts_match_policy_stage_definitions() -> None:
    policy_by_id = {s["id"]: s for s in _policy()["stages"]}
    contracts = _contracts()
    for stage_id, contract in contracts.items():
        assert contract["req_id"] == "REQ-APP-001"
        assert contract["stage_id"] == stage_id
        policy_entry = policy_by_id[stage_id]
        assert contract["verification_type"] == policy_entry["verification_type"]
        # All required_contract_fields declared by policy must appear in contract.
        for fld in policy_entry.get("required_contract_fields", []):
            assert fld in contract, (
                f"contract {stage_id} missing required field {fld!r}"
            )


def test_gate_stages_align_with_policy_and_meta() -> None:
    policy_ids = [s["id"] for s in _policy()["stages"]]
    meta_ids = [s["stage_id"] for s in _req_meta()["stages"]]
    gate_ids = [s["id"] for s in _gate()["stages"]]
    # gate stages must reflect the REQ meta selection in order.
    assert gate_ids == meta_ids
    # And the meta selection is a subset of the policy definition.
    assert set(meta_ids).issubset(set(policy_ids))


def test_gate_stage_verification_types_match_policy() -> None:
    policy_by_id = {s["id"]: s for s in _policy()["stages"]}
    for stage in _gate()["stages"]:
        assert stage["verification_type"] == policy_by_id[stage["id"]]["verification_type"]


def test_gate_stage_contract_refs_match_meta_contract_refs() -> None:
    meta_by_id = {s["stage_id"]: s for s in _req_meta()["stages"]}
    for stage in _gate()["stages"]:
        assert stage["contract_ref"] == meta_by_id[stage["id"]]["contract_ref"]


def test_gate_decision_semantics_are_consistent() -> None:
    """ALLOW implies failed_stage='' and every gate stage passed; symmetric for DENY."""
    gate = _gate()
    assert gate["status"] == gate["decision"]["result"]
    if gate["status"] == "ALLOW":
        assert gate["failed_stage"] == ""
        assert all(s["result"] == "passed" for s in gate["stages"])
    else:  # DENY
        assert gate["failed_stage"] != ""
        assert any(s["result"] == "failed" for s in gate["stages"])


def test_gate_basis_contains_expected_ids() -> None:
    """basis[] must reference REQ, policy and every adopted contract."""
    gate = _gate()
    basis = set(gate["basis"])
    assert "REQ-APP-001" in basis
    # Policy id surfaces as POLICY-<policy_id>.
    assert any(b.startswith("POLICY-") for b in basis), basis
    # Each adopted stage must surface as CONTRACT-REQ-APP-001-<stage_id>.
    for stage in _req_meta()["stages"]:
        marker = f"CONTRACT-REQ-APP-001-{stage['stage_id']}"
        assert marker in basis, f"basis missing {marker!r}; got {basis}"


def test_gate_timestamps_are_mutually_consistent() -> None:
    """timestamp_utc (compact), timestamp_rfc3339, and paths.run_dir must agree."""
    gate = _gate()
    utc = gate["timestamp_utc"]            # YYYY-MM-DDTHHMMSSZ
    rfc = gate["timestamp_rfc3339"]        # YYYY-MM-DDTHH:MM:SSZ
    run_dir = gate["paths"]["run_dir"]

    # The compact form must end the run_dir path.
    assert run_dir.endswith(utc), (run_dir, utc)
    # Both timestamps must describe the same wall-clock instant.
    m = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})Z", utc
    )
    assert m, f"timestamp_utc shape unexpected: {utc!r}"
    expected_rfc = (
        f"{m.group(1)}-{m.group(2)}-{m.group(3)}T"
        f"{m.group(4)}:{m.group(5)}:{m.group(6)}Z"
    )
    assert rfc == expected_rfc, (utc, rfc)


def test_gate_paths_curated_dir_matches_actual_layout() -> None:
    gate = _gate()
    curated = gate["paths"]["curated_latest_dir"]
    expected = ".quality-system/evidence/REQ-APP-001/latest"
    assert curated == expected, (curated, expected)


def test_gate_stage_log_refs_resolve_to_files() -> None:
    """Codex review item 1: log_ref must point at a real file under latest/."""
    latest_dir = QS / "evidence" / "REQ-APP-001" / "latest"
    for stage in _gate()["stages"]:
        log_path = latest_dir / stage["log_ref"]
        assert log_path.is_file(), (
            f"log_ref does not resolve to an actual file: "
            f"{stage['log_ref']} (looked under {latest_dir})"
        )


# ---- Layer 4: contract claims hold on the actual target ------------------


def test_substring_match_keywords_actually_present_in_target() -> None:
    """If S2 claims target contains 'hello', target had better contain it."""
    contracts = _contracts()
    s2 = contracts["S2"]
    target_text = (GENERIC_MINIMAL / s2["target"]).read_text(encoding="utf-8")
    for keyword in s2["must_contain"]:
        assert keyword in target_text, (
            f"contract S2 claims target contains {keyword!r}, but it doesn't"
        )


def test_file_exists_target_actually_exists() -> None:
    contracts = _contracts()
    s1 = contracts["S1"]
    target_path = GENERIC_MINIMAL / s1["target"]
    assert target_path.is_file()


# ---- design-notes.md required content ------------------------------------


def test_design_notes_documents_stage_count_choice() -> None:
    """design-notes.md must explain the deviation from the recommended 3-7 range."""
    notes = (GENERIC_MINIMAL / "design-notes.md").read_text("utf-8")
    assert "推奨" in notes
    assert "意図的" in notes or "2 段階" in notes


def test_design_notes_lists_rejected_stages() -> None:
    """design-notes.md must include the "stages we did NOT adopt" section.

    This is the most valuable part of the example pack (Issue #12 discussion):
    teaching the decision pattern, not just the winning choice.
    """
    notes = (GENERIC_MINIMAL / "design-notes.md").read_text("utf-8")
    assert "採用しなかった段階" in notes


def test_design_notes_has_required_top_level_sections() -> None:
    """Codex review item 3: enforce the design-notes spec at section level."""
    notes = (GENERIC_MINIMAL / "design-notes.md").read_text("utf-8")
    required_sections = [
        "## 対象系の特徴",
        "## 段階数の決定根拠",
        "## 採用した段階と理由",
        "## 採用しなかった段階と理由",
        "## 思想憲章のどの項目が特に効くか",
        "## 段階間の依存関係",
        "## 既知の限界",
    ]
    for header in required_sections:
        assert header in notes, f"design-notes.md missing section: {header}"
