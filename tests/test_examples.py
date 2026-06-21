"""Tests that the bundled examples stay consistent with the schemas and themselves.

Phase 1 currently ships one hand-written example (Step 4):
``examples/generic-minimal/``. This module enforces three layers of guard:

1. Schema validity: ``qgb validate`` of the example must succeed.
2. Strict curated gate.json conformance.
3. Cross-file integrity (policy <-> REQ meta <-> contract <-> gate.json).

(3) is the contract that Step 5's ``qgb run`` implementation must keep
honouring; if a future change drifts one of these files, CI fails here.

Step 5 補修 (R reference): the hand-written reference gate.json /
summary.md / stages logs live under ``evidence-reference/`` (not
``.quality-system/evidence/``). The latter is the destination
``qgb run`` writes to and must stay empty in the repo; the former is
the source of truth a Step 5 run must reproduce.
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
# Step 5 補修: the hand-written reference lives outside .quality-system/ so
# `qgb run --path examples/generic-minimal` cannot overwrite it.
REFERENCE_LATEST = (
    GENERIC_MINIMAL / "evidence-reference" / "REQ-APP-001" / "latest"
)


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
    return _read_json(REFERENCE_LATEST / "gate.json")


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
    """timestamp_utc, timestamp_rfc3339, run_id, and paths.run_dir must agree.

    Step 5 三次補修: paths.run_dir now ends with ``<timestamp_utc>-<run_id>``;
    the timestamp itself is wall-clock truth (no synthetic forwarding),
    and same-second collisions are absorbed by run_id alone.
    """
    gate = _gate()
    utc = gate["timestamp_utc"]            # YYYY-MM-DDTHHMMSSZ
    rfc = gate["timestamp_rfc3339"]        # YYYY-MM-DDTHH:MM:SSZ
    run_id = gate["run_id"]                # r0001..rffff
    run_dir = gate["paths"]["run_dir"]

    # run_dir ends in <timestamp_utc>-<run_id> exactly.
    assert run_dir.endswith(f"{utc}-{run_id}"), (run_dir, utc, run_id)
    # run_id obeys its schema pattern.
    assert re.fullmatch(r"r[0-9a-f]{4}", run_id), run_id
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
    """Codex review item 1: log_ref must point at a real file alongside gate.json.

    log_ref in the curated reference is a path *relative to the directory
    that holds gate.json*, so the test resolves it under the reference
    directory rather than under ``.quality-system/evidence/.../latest/``.
    A Step 5 ``qgb run`` writes the same log files alongside its own
    gate.json (in both the curated and volatile trees).
    """
    for stage in _gate()["stages"]:
        log_path = REFERENCE_LATEST / stage["log_ref"]
        assert log_path.is_file(), (
            f"log_ref does not resolve to an actual file: "
            f"{stage['log_ref']} (looked under {REFERENCE_LATEST})"
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


# =========================================================================
# Step 8 examples: python-cli-pytest and markdown-docs
# =========================================================================
#
# The two new examples share the same hand-written reference contract as
# generic-minimal: each ships .quality-system/ + evidence-reference/ +
# design-notes.md and must validate under qgb at all three layers
# (schema / curated gate / cross-file integrity). The test helpers
# below are parameterised across (example_dir, req_id, expected_files,
# expected_schemas) so future Phase 2 example additions just append a
# parameters tuple.


def _example_qs(example_dir: Path) -> Path:
    return example_dir / ".quality-system"


def _example_reference_latest(example_dir: Path, req_id: str) -> Path:
    return example_dir / "evidence-reference" / req_id / "latest"


def _example_policy(example_dir: Path) -> dict:
    return _read_json(_example_qs(example_dir) / "policy.json")


def _example_req_meta(example_dir: Path, req_id: str) -> dict:
    return _read_json(_example_qs(example_dir) / "req" / f"{req_id}.meta.json")


def _example_contracts(example_dir: Path, req_id: str) -> dict[str, dict]:
    base = _example_qs(example_dir) / "contracts" / req_id
    return {p.stem: _read_json(p) for p in sorted(base.glob("*.json"))}


def _example_gate(example_dir: Path, req_id: str) -> dict:
    return _read_json(_example_reference_latest(example_dir, req_id) / "gate.json")


# Step 8 examples (Codex 計画レビュー方針):
# - python-cli-pytest: command + substring_match (REQ-APP-001, 3 stages)
# - markdown-docs: file_exists + substring_match + json_schema (REQ-DOC-001, 3 stages)
_STEP8_EXAMPLES = [
    {
        "name": "python-cli-pytest",
        "dir": EXAMPLES / "python-cli-pytest",
        "req_id": "REQ-APP-001",
        # 3 contracts + policy + req-meta + config + project-context = 7 spec files
        # (Phase 3 Step 3.0: project-context.json を記入例として追加)
        "expected_files": 7,
        "expected_schema_names": [
            "config", "contract", "contract", "contract", "policy",
            "project-context", "req-meta",
        ],
        "expected_basis_contracts": [
            "CONTRACT-REQ-APP-001-S1",
            "CONTRACT-REQ-APP-001-S2",
            "CONTRACT-REQ-APP-001-S3",
        ],
    },
    {
        "name": "markdown-docs",
        "dir": EXAMPLES / "markdown-docs",
        "req_id": "REQ-DOC-001",
        "expected_files": 6,
        "expected_schema_names": [
            "config", "contract", "contract", "contract", "policy", "req-meta",
        ],
        "expected_basis_contracts": [
            "CONTRACT-REQ-DOC-001-S1",
            "CONTRACT-REQ-DOC-001-S2",
            "CONTRACT-REQ-DOC-001-S3",
        ],
    },
    {
        "name": "python-fastapi-pytest",
        "dir": EXAMPLES / "python-fastapi-pytest",
        "req_id": "REQ-APP-001",
        "expected_files": 6,
        "expected_schema_names": [
            "config", "contract", "contract", "contract", "policy", "req-meta",
        ],
        "expected_basis_contracts": [
            "CONTRACT-REQ-APP-001-S1",
            "CONTRACT-REQ-APP-001-S2",
            "CONTRACT-REQ-APP-001-S3",
        ],
    },
    {
        "name": "go-cli",
        "dir": EXAMPLES / "go-cli",
        "req_id": "REQ-APP-001",
        "expected_files": 6,
        "expected_schema_names": [
            "config", "contract", "contract", "contract", "policy", "req-meta",
        ],
        "expected_basis_contracts": [
            "CONTRACT-REQ-APP-001-S1",
            "CONTRACT-REQ-APP-001-S2",
            "CONTRACT-REQ-APP-001-S3",
        ],
    },
    {
        "name": "node-cli-vitest",
        "dir": EXAMPLES / "node-cli-vitest",
        "req_id": "REQ-APP-001",
        "expected_files": 6,
        "expected_schema_names": [
            "config", "contract", "contract", "contract", "policy", "req-meta",
        ],
        "expected_basis_contracts": [
            "CONTRACT-REQ-APP-001-S1",
            "CONTRACT-REQ-APP-001-S2",
            "CONTRACT-REQ-APP-001-S3",
        ],
    },
]


def test_step8_examples_validate_under_qgb_validate() -> None:
    """Each Step 8 example must pass qgb validate."""
    for ex in _STEP8_EXAMPLES:
        report = run_validate(ex["dir"])
        assert not report.has_problems(), (ex["name"], report)
        assert len(report.files_checked) == ex["expected_files"], ex["name"]
        schema_names = sorted(name for _, name in report.files_checked)
        assert schema_names == ex["expected_schema_names"], ex["name"]


def test_step8_examples_reference_gate_conforms_to_strict_schema() -> None:
    """Each example's frozen evidence-reference/gate.json passes strict schema."""
    for ex in _STEP8_EXAMPLES:
        gate = _example_gate(ex["dir"], ex["req_id"])
        issues = schema_validate(gate, "gate")
        assert not issues, (ex["name"], [(i.path, i.message) for i in issues])


def test_step8_examples_policy_and_req_meta_align() -> None:
    """REQ meta stage_id must exist in policy stages for each example."""
    for ex in _STEP8_EXAMPLES:
        policy = _example_policy(ex["dir"])
        meta = _example_req_meta(ex["dir"], ex["req_id"])
        policy_stage_ids = {s["id"] for s in policy["stages"]}
        meta_stage_ids = [s["stage_id"] for s in meta["stages"]]
        for mid in meta_stage_ids:
            assert mid in policy_stage_ids, (ex["name"], mid)


def test_step8_examples_meta_contract_refs_resolve_to_real_files() -> None:
    for ex in _STEP8_EXAMPLES:
        meta = _example_req_meta(ex["dir"], ex["req_id"])
        for stage_entry in meta["stages"]:
            ref = ex["dir"] / stage_entry["contract_ref"]
            assert ref.is_file(), (
                ex["name"], stage_entry["stage_id"], str(ref)
            )


def test_step8_examples_gate_basis_contains_expected_ids() -> None:
    for ex in _STEP8_EXAMPLES:
        gate = _example_gate(ex["dir"], ex["req_id"])
        basis = set(gate["basis"])
        assert ex["req_id"] in basis
        assert "POLICY-default" in basis
        for contract_id in ex["expected_basis_contracts"]:
            assert contract_id in basis, (ex["name"], contract_id)


def test_step8_examples_gate_decision_semantics_consistent() -> None:
    """Gate status matches decision.result and failed_stage convention."""
    for ex in _STEP8_EXAMPLES:
        gate = _example_gate(ex["dir"], ex["req_id"])
        assert gate["status"] == gate["decision"]["result"], ex["name"]
        if gate["status"] == "ALLOW":
            assert gate["failed_stage"] == "", ex["name"]
        # Step 6+7 統合レビュー RA2: scope is present
        assert "scope" in gate["decision"], ex["name"]


def test_step8_examples_gate_timestamps_mutually_consistent() -> None:
    """compact <-> rfc3339 representations of the same instant."""
    pattern = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})Z$")
    for ex in _STEP8_EXAMPLES:
        gate = _example_gate(ex["dir"], ex["req_id"])
        m = pattern.fullmatch(gate["timestamp_utc"])
        assert m, (ex["name"], gate["timestamp_utc"])
        expected_rfc = (
            f"{m.group(1)}-{m.group(2)}-{m.group(3)}T"
            f"{m.group(4)}:{m.group(5)}:{m.group(6)}Z"
        )
        assert gate["timestamp_rfc3339"] == expected_rfc, ex["name"]


def test_step8_examples_gate_stage_log_refs_resolve_to_files() -> None:
    for ex in _STEP8_EXAMPLES:
        ref_latest = _example_reference_latest(ex["dir"], ex["req_id"])
        for stage in _example_gate(ex["dir"], ex["req_id"])["stages"]:
            assert (ref_latest / stage["log_ref"]).is_file(), (
                ex["name"], stage["log_ref"]
            )


def test_step8_examples_design_notes_have_required_sections() -> None:
    """Same design-notes section template as generic-minimal."""
    required = [
        "## 対象系の特徴",
        "## 段階数の決定根拠",
        "## 採用した段階と理由",
        "## 採用しなかった段階と理由",
        "## 思想憲章のどの項目が特に効くか",
        "## 段階間の依存関係",
        "## 既知の限界",
    ]
    for ex in _STEP8_EXAMPLES:
        notes_path = ex["dir"] / "design-notes.md"
        notes = notes_path.read_text(encoding="utf-8")
        for header in required:
            assert header in notes, (ex["name"], header)


def test_step8_examples_contracts_match_policy_verification_types() -> None:
    """Each contract's verification_type matches its policy stage."""
    for ex in _STEP8_EXAMPLES:
        policy = _example_policy(ex["dir"])
        policy_vt = {s["id"]: s["verification_type"] for s in policy["stages"]}
        contracts = _example_contracts(ex["dir"], ex["req_id"])
        for stage_id, contract in contracts.items():
            assert contract["verification_type"] == policy_vt[stage_id], (
                ex["name"], stage_id
            )


def test_python_cli_pytest_substring_target_actually_contains_keyword() -> None:
    """python-cli-pytest S3 (substring_match) target really has the keyword."""
    ex_dir = EXAMPLES / "python-cli-pytest"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s3 = contracts["S3"]
    target_text = (ex_dir / s3["target"]).read_text(encoding="utf-8")
    for keyword in s3["must_contain"]:
        assert keyword in target_text, (s3["target"], keyword)


def test_markdown_docs_substring_target_actually_contains_keyword() -> None:
    ex_dir = EXAMPLES / "markdown-docs"
    contracts = _example_contracts(ex_dir, "REQ-DOC-001")
    s2 = contracts["S2"]
    target_text = (ex_dir / s2["target"]).read_text(encoding="utf-8")
    for keyword in s2["must_contain"]:
        assert keyword in target_text, (s2["target"], keyword)


def test_fastapi_file_exists_target_actually_exists() -> None:
    """python-fastapi-pytest S2 (file_exists) target resolves."""
    ex_dir = EXAMPLES / "python-fastapi-pytest"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s2 = contracts["S2"]
    assert (ex_dir / s2["target"]).is_file()


def test_fastapi_substring_target_actually_contains_keyword() -> None:
    """python-fastapi-pytest S3 (substring_match) target has the keyword."""
    ex_dir = EXAMPLES / "python-fastapi-pytest"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s3 = contracts["S3"]
    target_text = (ex_dir / s3["target"]).read_text(encoding="utf-8")
    for keyword in s3["must_contain"]:
        assert keyword in target_text, (s3["target"], keyword)


def test_go_cli_substring_target_actually_contains_keyword() -> None:
    ex_dir = EXAMPLES / "go-cli"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s3 = contracts["S3"]
    target_text = (ex_dir / s3["target"]).read_text(encoding="utf-8")
    for keyword in s3["must_contain"]:
        assert keyword in target_text, (s3["target"], keyword)


def test_node_cli_file_exists_target_actually_exists() -> None:
    ex_dir = EXAMPLES / "node-cli-vitest"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s2 = contracts["S2"]
    assert (ex_dir / s2["target"]).is_file()


def test_node_cli_substring_target_actually_contains_keyword() -> None:
    ex_dir = EXAMPLES / "node-cli-vitest"
    contracts = _example_contracts(ex_dir, "REQ-APP-001")
    s3 = contracts["S3"]
    target_text = (ex_dir / s3["target"]).read_text(encoding="utf-8")
    for keyword in s3["must_contain"]:
        assert keyword in target_text, (s3["target"], keyword)


def test_markdown_docs_metadata_validates_against_its_schema() -> None:
    """markdown-docs S3 (json_schema): docs/metadata.json validates the schema."""
    import jsonschema

    ex_dir = EXAMPLES / "markdown-docs"
    metadata = _read_json(ex_dir / "docs" / "metadata.json")
    schema = _read_json(ex_dir / "schemas" / "metadata.schema.json")
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    errors = list(validator.iter_errors(metadata))
    assert not errors, errors
