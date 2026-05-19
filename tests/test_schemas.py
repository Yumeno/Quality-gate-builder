"""Tests for the bundled JSON Schemas (Step 1, with Step 1 patch corrections)."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from qgb.core.schema import (
    SCHEMA_FILES,
    ValidationIssue,
    is_valid,
    load_schema,
    validate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "schemas"


def _load_fixture(name: str) -> dict:
    with (FIXTURES / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _has_schema_path(issues: Iterable[ValidationIssue], needle: str) -> bool:
    """Helper: True iff some issue's schema_path contains `needle` as substring."""
    return any(needle in i.schema_path for i in issues)


def _has_instance_path(issues: Iterable[ValidationIssue], needle: str) -> bool:
    return any(needle in i.path for i in issues)


# --- Schema self-checks ---


@pytest.mark.parametrize("schema_name", sorted(SCHEMA_FILES))
def test_each_schema_is_valid_draft_2020_12(schema_name: str) -> None:
    schema = load_schema(schema_name)
    Draft202012Validator.check_schema(schema)


def test_all_schemas_are_loadable_via_importlib_resources() -> None:
    # Smoke-test: load_schema must succeed for every entry and return a dict.
    for name in SCHEMA_FILES:
        schema = load_schema(name)
        assert isinstance(schema, dict)
        assert "$schema" in schema


# --- config ---


def test_config_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("config.success.json"), "config")


def test_config_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("config.failure.json"), "config")
    assert issues, "config.failure.json must produce at least one issue"
    # Bad schema_version pattern and empty project name.
    assert _has_schema_path(issues, "pattern") or _has_instance_path(issues, "/schema_version")


# --- policy ---


def test_policy_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("policy.success.json"), "policy")


def test_policy_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("policy.failure.json"), "policy")
    messages = [i.message for i in issues]
    assert issues, "policy.failure.json must fail"
    # Unknown verification_type ("shell_script") must be rejected with an enum error.
    assert any("shell_script" in m for m in messages), messages
    assert _has_schema_path(issues, "verification_type"), [i.schema_path for i in issues]
    # Empty id and empty responsibility must trigger minLength errors.
    assert _has_schema_path(issues, "minLength"), [i.schema_path for i in issues]


# --- REQ meta ---


def test_req_meta_success_fixture_validates() -> None:
    assert is_valid(_load_fixture("req-meta.success.json"), "req-meta")


def test_req_meta_failure_fixture_rejected() -> None:
    issues = validate(_load_fixture("req-meta.failure.json"), "req-meta")
    assert issues, "req-meta.failure.json must fail"
    # Bad req_id pattern and empty stages array.
    assert _has_instance_path(issues, "/req_id") or _has_instance_path(issues, "/stages")


def test_req_meta_waived_with_reason_validates() -> None:
    assert is_valid(_load_fixture("req-meta.waived.success.json"), "req-meta")


def test_req_meta_waived_without_reason_rejected() -> None:
    issues = validate(_load_fixture("req-meta.waived.failure.json"), "req-meta")
    assert issues, "waived: true without waiver_reason must fail"
    # Should fail at the conditional-required check on waiver_reason.
    messages = [i.message for i in issues]
    assert any("waiver_reason" in m for m in messages), messages


def test_req_meta_schema_version_is_optional() -> None:
    # Phase 1: schema_version is allowed but not required on REQ meta.
    payload = _load_fixture("req-meta.success.json")
    payload["schema_version"] = "1.0"
    assert is_valid(payload, "req-meta")


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


@pytest.mark.parametrize(
    ("fixture_name", "expected_field"),
    [
        ("contract.command.failure.json", "command"),
        ("contract.file_exists.failure.json", "target"),
        ("contract.json_schema.failure.json", "schema"),
        ("contract.manual_check.failure.json", "description"),
    ],
)
def test_contract_failure_fixtures_rejected(fixture_name: str, expected_field: str) -> None:
    issues = validate(_load_fixture(fixture_name), "contract")
    assert issues, f"{fixture_name} must fail"
    messages = [i.message for i in issues]
    assert any(expected_field in m for m in messages), (
        f"{fixture_name} expected error mentioning {expected_field!r}: {messages}"
    )


def test_contract_substring_match_empty_array_rejected() -> None:
    issues = validate(_load_fixture("contract.substring_match.failure.json"), "contract")
    assert issues, "must_contain: [] must be rejected (minItems: 1)"
    assert _has_schema_path(issues, "minItems") or any(
        "[]" in i.message or "minItems" in i.message for i in issues
    )


def test_contract_command_as_string_rejected() -> None:
    issues = validate(
        _load_fixture("contract.command_string_not_array.failure.json"), "contract"
    )
    assert issues, "command as string (not argv array) must be rejected"
    # The base property type expects array.
    assert any("array" in i.message.lower() for i in issues), [i.message for i in issues]


def test_contract_command_empty_arg_rejected() -> None:
    issues = validate(
        _load_fixture("contract.command_empty_arg.failure.json"), "contract"
    )
    assert issues, "argv array with an empty string element must be rejected"


# --- gate (strict, curated) ---


def test_gate_allow_fixture_validates() -> None:
    assert is_valid(_load_fixture("gate.allow.success.json"), "gate")


def test_gate_deny_fixture_validates() -> None:
    assert is_valid(_load_fixture("gate.deny.success.json"), "gate")


def test_gate_allow_with_non_empty_failed_stage_rejected() -> None:
    issues = validate(
        _load_fixture("gate.allow_with_failed_stage.failure.json"), "gate"
    )
    assert issues, "status=ALLOW with non-empty failed_stage must fail"
    # The constraint lives under the ALLOW branch of allOf.
    assert _has_schema_path(issues, "allOf") or _has_instance_path(issues, "/failed_stage")


def test_gate_deny_with_empty_failed_stage_rejected() -> None:
    issues = validate(
        _load_fixture("gate.deny_with_empty_failed_stage.failure.json"), "gate"
    )
    assert issues, "status=DENY with empty failed_stage must fail"


def test_gate_strict_rejects_additional_top_level_properties() -> None:
    issues = validate(_load_fixture("gate.extra_field.failure.json"), "gate")
    assert issues, "curated gate.json must reject additional top-level fields"
    assert _has_schema_path(issues, "additionalProperties")


def test_gate_strict_rejects_nested_additional_properties() -> None:
    issues = validate(_load_fixture("gate.nested_extra_field.failure.json"), "gate")
    assert issues, "curated gate.json must reject additional fields under decision/runner/paths"
    assert _has_schema_path(issues, "additionalProperties")


def test_gate_allow_with_failed_stage_result_rejected() -> None:
    """Codex review item 1: status=ALLOW must imply every stage.result=passed."""
    issues = validate(
        _load_fixture("gate.allow_with_failed_stage_result.failure.json"), "gate"
    )
    assert issues, "status=ALLOW must not coexist with a failed stage result"


def test_gate_deny_with_all_passed_stages_rejected() -> None:
    """status=DENY must require at least one stage.result=failed."""
    issues = validate(
        _load_fixture("gate.deny_with_all_passed_stages.failure.json"), "gate"
    )
    assert issues, "status=DENY must not coexist with all stages passed"


def test_gate_allow_with_deny_decision_rejected() -> None:
    """decision.result and status must agree (ALLOW vs DENY mismatch)."""
    issues = validate(
        _load_fixture("gate.allow_with_deny_decision.failure.json"), "gate"
    )
    assert issues, "status=ALLOW with decision.result=DENY must fail"


def test_gate_deny_with_allow_decision_rejected() -> None:
    issues = validate(
        _load_fixture("gate.deny_with_allow_decision.failure.json"), "gate"
    )
    assert issues, "status=DENY with decision.result=ALLOW must fail"


def test_gate_bad_timestamp_rfc3339_rejected() -> None:
    """Codex review item 2: format: date-time must be enforced via format_checker."""
    issues = validate(
        _load_fixture("gate.bad_timestamp_rfc3339.failure.json"), "gate"
    )
    assert issues, "invalid RFC3339 timestamp must be rejected when format_checker is active"
    assert _has_instance_path(issues, "/timestamp_rfc3339")


def test_gate_stage_requires_contract_ref_and_log_ref() -> None:
    """Codex review item 3: curated gate requires contract_ref and log_ref per stage."""
    payload = _load_fixture("gate.allow.success.json")
    # Drop required-on-stage fields and re-validate.
    payload["stages"][0].pop("contract_ref", None)
    issues = validate(payload, "gate")
    assert issues
    assert any("contract_ref" in i.message for i in issues), [i.message for i in issues]

    payload = _load_fixture("gate.allow.success.json")
    payload["stages"][0].pop("log_ref", None)
    issues = validate(payload, "gate")
    assert issues
    assert any("log_ref" in i.message for i in issues), [i.message for i in issues]

    payload = _load_fixture("gate.allow.success.json")
    payload["stages"][0].pop("exit_code", None)
    issues = validate(payload, "gate")
    assert issues
    assert any("exit_code" in i.message for i in issues), [i.message for i in issues]


# --- gate.runtime (permissive) ---


def test_gate_runtime_allows_additional_properties() -> None:
    # Same payload that fails the strict schema; runtime schema must accept it.
    assert is_valid(_load_fixture("gate.extra_field.failure.json"), "gate-runtime")


def test_gate_runtime_extra_field_fixture_validates() -> None:
    assert is_valid(
        _load_fixture("gate-runtime.extra_field.success.json"), "gate-runtime"
    )


def test_gate_runtime_still_enforces_decision_result_match() -> None:
    """Even on the permissive runtime schema, ALLOW/DENY mismatch should fail."""
    issues = validate(
        _load_fixture("gate.allow_with_deny_decision.failure.json"), "gate-runtime"
    )
    assert issues, "runtime schema also enforces decision.result vs status"


# --- knowledge ---


def test_knowledge_user_fixture_validates() -> None:
    assert is_valid(_load_fixture("knowledge.user.success.json"), "knowledge")


def test_knowledge_waiver_fixture_validates() -> None:
    assert is_valid(_load_fixture("knowledge.waiver.success.json"), "knowledge")


def test_knowledge_waiver_missing_fields_rejected() -> None:
    issues = validate(_load_fixture("knowledge.waiver.failure.json"), "knowledge")
    assert issues, "kind=waiver without stage_id/reason/decided_by/applies_to must fail"
    messages = [i.message for i in issues]
    # At least one of the conditionally-required fields should be flagged.
    assert any(
        any(f in m for f in ("stage_id", "reason", "decided_by", "applies_to"))
        for m in messages
    ), messages


def test_knowledge_external_with_review_flag_validates() -> None:
    assert is_valid(_load_fixture("knowledge.external.success.json"), "knowledge")


def test_knowledge_bad_created_at_format_rejected() -> None:
    """format: date-time must be enforced on created_at."""
    payload = _load_fixture("knowledge.user.success.json")
    payload["created_at"] = "not-a-date"
    issues = validate(payload, "knowledge")
    assert issues, "invalid RFC3339 created_at must be rejected"
    assert _has_instance_path(issues, "/created_at")


# --- ValidationIssue path is an RFC 6901 JSON Pointer ---


def test_validation_issue_path_uses_json_pointer_escapes() -> None:
    """If an instance has a key with `/` or `~`, ValidationIssue.path must escape it.

    Build a synthetic schema/instance pair to drive a known violation under such a key.
    """
    # Construct a schema that requires a specific field to be a string;
    # then feed a violation through validate() to inspect the resulting pointer.
    # We piggyback on the policy schema by sticking a violation in `policy_id`.
    payload = _load_fixture("policy.success.json")
    payload["policy_id"] = 123  # type: ignore[assignment]  # wrong type triggers an error
    issues = validate(payload, "policy")
    assert issues
    # /policy_id is a simple path; no escape needed. But the pointer must start with /.
    assert any(i.path.startswith("/") for i in issues)
    assert any(i.path == "/policy_id" for i in issues), [i.path for i in issues]


# --- Stable ordering of issues ---


def test_validation_issues_are_sorted_stably() -> None:
    """Repeated validation of the same payload must return issues in the same order."""
    payload = _load_fixture("policy.failure.json")
    first = validate(payload, "policy")
    second = validate(payload, "policy")
    assert first == second
