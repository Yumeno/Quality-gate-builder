"""Tests that the bundled examples stay consistent with the schemas.

Phase 1 currently ships one hand-written example (Step 4):
``examples/generic-minimal/``. This module guards two invariants:

1. ``qgb validate`` of the example must succeed (i.e. the .quality-system/
   tree conforms to qgb's machine contract).
2. The hand-written ``evidence/REQ-APP-001/latest/gate.json`` must conform
   to the curated gate schema, including the strict semantic constraints
   (ALLOW + failed_stage="" + every stage passed, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path

from qgb.core.schema import validate as schema_validate
from qgb.core.validate import run_validate

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = REPO_ROOT / "examples"
GENERIC_MINIMAL = EXAMPLES / "generic-minimal"


def test_generic_minimal_validates_under_qgb_validate() -> None:
    """Step 5 precondition: the hand-written example must pass qgb validate."""
    report = run_validate(GENERIC_MINIMAL)
    assert not report.has_problems(), report
    # config / policy / 1 REQ meta / 2 contracts = 5 spec files.
    assert len(report.files_checked) == 5
    schema_names = sorted(name for _, name in report.files_checked)
    assert schema_names == ["config", "contract", "contract", "policy", "req-meta"]


def test_generic_minimal_curated_gate_conforms_to_strict_schema() -> None:
    """The hand-written gate.json acts as the Step 5 reference output.

    It must conform to the strict (additionalProperties: false) curated schema
    so that, when Step 5 implements qgb run, its output can replace this file
    byte-for-byte structurally.
    """
    gate_path = (
        GENERIC_MINIMAL / ".quality-system" / "evidence"
        / "REQ-APP-001" / "latest" / "gate.json"
    )
    payload = json.loads(gate_path.read_text("utf-8"))
    issues = schema_validate(payload, "gate")
    assert not issues, [f"{i.path}: {i.message}" for i in issues]


def test_generic_minimal_target_file_actually_contains_keyword() -> None:
    """The substring_match contract claims target/sample.txt contains 'hello'.

    If we're going to use this example as Step 5's reference, the underlying
    target must actually satisfy the contract.
    """
    target_path = GENERIC_MINIMAL / "target" / "sample.txt"
    assert target_path.is_file()
    text = target_path.read_text("utf-8")
    assert "hello" in text


def test_generic_minimal_design_notes_documents_stage_count() -> None:
    """design-notes.md must explain the deviation from the recommended 3-7 range."""
    notes = (GENERIC_MINIMAL / "design-notes.md").read_text("utf-8")
    # The decision section must mention "推奨段階数" or "推奨レンジ".
    assert "推奨" in notes
    # And explain the deviation (2 stages or "意図的に").
    assert "意図的" in notes or "2 段階" in notes


def test_generic_minimal_design_notes_lists_rejected_stages() -> None:
    """design-notes.md must include the "stages we did NOT adopt" section.

    This is the most valuable part of the example pack (Issue #12 discussion):
    teaching the decision pattern, not just the winning choice.
    """
    notes = (GENERIC_MINIMAL / "design-notes.md").read_text("utf-8")
    assert "採用しなかった段階" in notes
