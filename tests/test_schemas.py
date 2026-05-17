"""Tests for the bundled JSON Schemas (Step 1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from qgb.core.schema import (
    SCHEMA_FILES,
    is_valid,
    load_schema,
    schemas_root,
    validate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


def _load_fixture(name: str) -> dict:
    with (FIXTURES / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


# --- Schema self-checks ---


@pytest.mark.parametrize("schema_name", sorted(SCHEMA_FILES))
def test_each_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = load_schema(schema_name)
    # Will raise jsonschema.SchemaError on a malformed schema.
    Draft202012Validator.check_schema(schema)


def test_schemas_root_resolves() -> None:
    root = schemas_root()
    assert root.is_dir()
    for filename in SCHEMA_FILES.values():
        assert (root / filename).is_file(), f"missing bundled schema: {filename}"


# --- config ---


def test_config_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("config.success.json"), "config")


def test_config_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("config.failure.json"), "config")
    assert issues, "config.failure.json must produce at least one issue"


# --- policy ---


def test_policy_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("policy.success.json"), "policy")


def test_policy_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("policy.failure.json"), "policy")
    # Expect empty id, empty responsibility, and unknown verification_type to all fail.
    messages = [i.message for i in issues]
    assert issues, "policy.failure.json must fail"
    # The unknown verification_type ("shell_script") must be rejected.
    assert any("shell_script" in m for m in messages), messages
    # Empty id and empty responsibility must trigger minLength errors.
    assert any("should be non-empty" in m or "minLength" in m for m in messages), messages


# --- REQ meta ---


def test_req_meta_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("req-meta.success.json"), "req-meta")


def test_req_meta_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("req-meta.failure.json"), "req-meta")
    assert issues, "req-meta.failure.json must fail (bad req_id and empty stages)"


def test_req_meta_waived_with_reason_validates() -> None:
    assert is_valid(_load_fixture("req-meta.waived.success.json"), "req-meta")


def test_req_meta_waived_without_reason_rejected() -> None:
    issues = validate(_load_fixture("req-meta.waived.failure.json"), "req-meta")
    assert issues, "waived: true without waiver_reason must fail"


# --- contract ---


@pytest.mark.parametrize(
    "fixture_name",
    [
        "contract.command.success.json",
        "contract.file_exists.success.json",
        "contract.substring_match.success.json",
        "contract.json_schema.success.json",
        "contract.manual_check.success.json",
    ],
)
def test_contract_success_fixtures_validate(fixture_name: str) -> None:
    assert is_valid(_load_fixture(fixture_name), "contract"), (
        f"{fixture_name} must validate against contract.schema.json"
    )


def test_contract_command_missing_command_rejected() -> None:
    issues = validate(_load_fixture("contract.command.failure.json"), "contract")
    assert issues, "command verification_type without `command` field must fail"


# --- gate (strict, curated) ---


def test_gate_allow_fixture_validates() -> None:
    assert is_valid(_load_fixture("gate.allow.success.json"), "gate")


def test_gate_deny_fixture_validates() -> None:
    assert is_valid(_load_fixture("gate.deny.success.json"), "gate")


def test_gate_allow_with_non_empty_failed_stage_rejected() -> None:
    issues = validate(_load_fixture("gate.allow_with_failed_stage.failure.json"), "gate")
    assert issues, "status=ALLOW with non-empty failed_stage must fail"


def test_gate_deny_with_empty_failed_stage_rejected() -> None:
    issues = validate(_load_fixture("gate.deny_with_empty_failed_stage.failure.json"), "gate")
    assert issues, "status=DENY with empty failed_stage must fail"


def test_gate_strict_rejects_additional_properties() -> None:
    issues = validate(_load_fixture("gate.extra_field.failure.json"), "gate")
    assert issues, "curated gate.json must reject additional top-level fields"


# --- gate.runtime (permissive) ---


def test_gate_runtime_allows_additional_properties() -> None:
    # Same payload that fails the strict schema; runtime schema must accept it.
    assert is_valid(
        _load_fixture("gate.extra_field.failure.json"), "gate-runtime"
    )


def test_gate_runtime_extra_field_fixture_validates() -> None:
    assert is_valid(_load_fixture("gate-runtime.extra_field.success.json"), "gate-runtime")


# --- knowledge ---


def test_knowledge_user_fixture_validates() -> None:
    assert is_valid(_load_fixture("knowledge.user.success.json"), "knowledge")


def test_knowledge_waiver_fixture_validates() -> None:
    assert is_valid(_load_fixture("knowledge.waiver.success.json"), "knowledge")


def test_knowledge_waiver_missing_fields_rejected() -> None:
    issues = validate(_load_fixture("knowledge.waiver.failure.json"), "knowledge")
    assert issues, "kind=waiver without stage_id/reason/decided_by/applies_to must fail"


def test_knowledge_external_with_review_flag_validates() -> None:
    assert is_valid(_load_fixture("knowledge.external.success.json"), "knowledge")
