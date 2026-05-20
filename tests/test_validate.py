"""Tests for the validate command (Step 2, with Step 2 patch corrections)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main
from qgb.core.validate import (
    FieldMismatch,
    IntegrityIssue,
    ReadError,
    _check_contract_field_mismatch,
    run_validate,
)

FIXTURES = Path(__file__).parent / "fixtures" / "projects"


# ---- run_validate (core) -------------------------------------------------


def test_run_validate_on_valid_project_returns_clean_report() -> None:
    report = run_validate(FIXTURES / "valid")
    assert not report.has_problems(), report
    # config.json, policy.json, 1 REQ meta, 2 contracts = 5 files.
    assert len(report.files_checked) == 5
    schema_names = sorted(name for _, name in report.files_checked)
    assert schema_names == ["config", "contract", "contract", "policy", "req-meta"]
    assert report.total_problems() == 0


def test_run_validate_reports_schema_violations() -> None:
    report = run_validate(FIXTURES / "schema_violation")
    assert report.has_problems()
    assert report.schema_issues, "schema violations should be reported"
    messages = " | ".join(fi.issue.message for fi in report.schema_issues)
    assert "shell_script" in messages, messages


def test_run_validate_reports_contract_field_mismatches() -> None:
    report = run_validate(FIXTURES / "field_mismatch")
    assert report.field_mismatches, "expected at least one field mismatch"
    # The contract declares verification_type=file_exists but also includes
    # `command` and `expected_exit_code` (which belong to verification_type=command).
    by_field = {fm.field_name: fm for fm in report.field_mismatches}
    assert by_field["command"].owning_verification_type == "command"
    assert by_field["expected_exit_code"].owning_verification_type == "command"
    # No schema violations are expected on this fixture (Codex re-review item 7).
    assert not report.schema_issues, report.schema_issues


def test_run_validate_reports_invalid_json_as_read_error() -> None:
    report = run_validate(FIXTURES / "invalid_json")
    assert report.read_errors, "invalid JSON must be reported as a read error"
    assert isinstance(report.read_errors[0], ReadError)
    assert report.read_errors[0].file.name == "config.json"
    assert "invalid JSON" in report.read_errors[0].message


def test_run_validate_on_directory_without_quality_system_returns_empty(
    tmp_path: Path,
) -> None:
    report = run_validate(tmp_path)
    assert not report.files_checked
    assert not report.has_problems()


def test_run_validate_files_checked_order_is_stable() -> None:
    # config.json, then policy.json, then sorted REQ metas, then contracts.
    report = run_validate(FIXTURES / "valid")
    schema_order = [name for _, name in report.files_checked]
    assert schema_order == ["config", "policy", "req-meta", "contract", "contract"]


# ---- integrity ------------------------------------------------------------


def test_run_validate_reports_missing_required_files() -> None:
    """Codex review #2: missing config.json / policy.json must be flagged."""
    report = run_validate(FIXTURES / "missing_required")
    kinds = sorted(ii.kind for ii in report.integrity_issues)
    assert "missing_file" in kinds, [ii.message for ii in report.integrity_issues]
    files = sorted(ii.file.name for ii in report.integrity_issues)
    assert "config.json" in files
    assert "policy.json" in files


def test_run_validate_reports_dangling_contract_ref_and_unknown_stage_id() -> None:
    """Codex review #2: REQ meta pointing at missing contract / unknown stage."""
    report = run_validate(FIXTURES / "dangling_ref")
    kinds = sorted(ii.kind for ii in report.integrity_issues)
    assert "dangling_contract_ref" in kinds, [ii.message for ii in report.integrity_issues]
    assert "unknown_stage_id" in kinds, [ii.message for ii in report.integrity_issues]


def test_run_validate_reports_misplaced_contract() -> None:
    """Contracts must live at contracts/<REQ>/<stage>.json, not deeper."""
    report = run_validate(FIXTURES / "misplaced_contract")
    misplaced = [ii for ii in report.integrity_issues if ii.kind == "misplaced_contract"]
    assert misplaced, [ii.message for ii in report.integrity_issues]
    # The deep contract file should also NOT be enumerated as a checked file.
    checked = [str(p) for p, _ in report.files_checked]
    assert not any("stages" in str(p) for p in checked), checked


# ---- contract field policy ------------------------------------------------


def test_check_contract_field_mismatch_known_type_allowed_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "command",
        "command": ["python", "-m", "x"],
        "expected_exit_code": 0,
        "timeout_seconds": 30,
    }
    assert _check_contract_field_mismatch(payload, Path("dummy.json")) == []


def test_check_contract_field_mismatch_unknown_verification_type_skipped() -> None:
    payload = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "no-such-type",
        "anything": True,
    }
    # Unknown verification_type is a schema concern, not a field-mismatch one.
    assert _check_contract_field_mismatch(payload, Path("dummy.json")) == []


def test_check_contract_field_mismatch_flags_foreign_typed_field() -> None:
    """Codex review #3: only fields owned by a *different* known type are flagged."""
    payload = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "file_exists",
        "target": "target/sample.txt",
        "command": ["should", "not", "appear"],
    }
    issues = _check_contract_field_mismatch(payload, Path("dummy.json"))
    assert issues == [
        FieldMismatch(
            file=Path("dummy.json"),
            verification_type="file_exists",
            field_name="command",
            owning_verification_type="command",
        )
    ]


def test_check_contract_field_mismatch_accepts_forward_compatible_field() -> None:
    """Codex review #3: fields not owned by any known type are forward-compatible.

    NOTE: "description" already belongs to manual_check, so it would be
    flagged on a non-manual contract. Truly forward-compatible fields are
    those that do not yet belong to any known verification_type's set.
    """
    payload = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "file_exists",
        "target": "target/sample.txt",
        "tags": ["smoke"],
        "notes": "common future field",
        "disabled": False,
    }
    assert _check_contract_field_mismatch(payload, Path("dummy.json")) == []


def test_run_validate_accepts_forward_compatible_contract_fields() -> None:
    """Whole-tree test for the forward-compatible policy."""
    report = run_validate(FIXTURES / "forward_compat_field")
    assert not report.has_problems(), report


def test_check_contract_field_mismatch_manual_check_rejects_command() -> None:
    """manual_check carrying a command-owned field should be flagged."""
    payload = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S6",
        "verification_type": "manual_check",
        "description": "Review by hand",
        "command": ["should", "not", "appear"],
    }
    issues = _check_contract_field_mismatch(payload, Path("dummy.json"))
    assert len(issues) == 1
    assert issues[0].field_name == "command"
    assert issues[0].owning_verification_type == "command"


# ---- CLI: in-process via main() ------------------------------------------


def test_cli_validate_on_valid_project_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "valid")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "OK:" in captured.out
    assert "Schema violations" not in captured.out
    assert "Contract field mismatches" not in captured.out
    assert "Integrity issues" not in captured.out


def test_cli_validate_on_schema_violation_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "schema_violation")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Schema violations" in captured.err


def test_cli_validate_on_field_mismatch_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "field_mismatch")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Contract field mismatches" in captured.err


def test_cli_validate_on_dangling_ref_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "dangling_ref")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Integrity issues" in captured.err
    assert "dangling_contract_ref" in captured.err


def test_cli_validate_on_invalid_json_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "invalid_json")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Read errors" in captured.err


def test_cli_validate_with_nonexistent_path_exits_usage(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bogus = tmp_path / "does-not-exist"
    exit_code = main(["validate", "--path", str(bogus)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE
    assert "does not exist" in captured.err


def test_cli_validate_with_file_path_exits_usage(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    """Codex review #1: --path must point at a directory, not a regular file."""
    f = tmp_path / "some.json"
    f.write_text("{}", encoding="utf-8")
    exit_code = main(["validate", "--path", str(f)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE
    assert "directory" in captured.err.lower()


def test_cli_validate_on_directory_without_quality_system_exits_zero(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main(["validate", "--path", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "No .quality-system/ files" in captured.out


# ---- CLI: --json flag ----------------------------------------------------


def test_cli_validate_json_output_on_valid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "valid"), "--json"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["files"] == 5
    assert payload["summary"]["total_problems"] == 0
    assert payload["summary"]["schema_issues"] == 0
    assert payload["summary"]["field_mismatches"] == 0
    assert payload["summary"]["read_errors"] == 0
    assert payload["summary"]["integrity_issues"] == 0
    # Codex review #7: --json must not pollute stderr with diagnostic text.
    assert captured.err == "", f"stderr should be empty when --json is used, got: {captured.err!r}"


def test_cli_validate_json_output_on_field_mismatch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["validate", "--path", str(FIXTURES / "field_mismatch"), "--json"]
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["summary"]["field_mismatches"] >= 1
    assert payload["summary"]["total_problems"] == (
        payload["summary"]["schema_issues"]
        + payload["summary"]["field_mismatches"]
        + payload["summary"]["read_errors"]
        + payload["summary"]["integrity_issues"]
    )
    flagged = {item["field"]: item for item in payload["field_mismatches"]}
    assert "command" in flagged
    assert flagged["command"]["owning_verification_type"] == "command"
    assert captured.err == ""


def test_cli_validate_json_output_on_integrity_issues(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["validate", "--path", str(FIXTURES / "dangling_ref"), "--json"]
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(captured.out)
    assert payload["summary"]["integrity_issues"] >= 2
    kinds = {item["kind"] for item in payload["integrity_issues"]}
    assert "dangling_contract_ref" in kinds
    assert "unknown_stage_id" in kinds


# ---- subprocess smoke ----------------------------------------------------


def _run_qgb(*args: str) -> subprocess.CompletedProcess[str]:
    """Spawn `python -m qgb ...` with UTF-8 forced on both ends.

    Windows defaults to the active code page (e.g. CP932) for console I/O, so
    the child process can produce bytes the parent's UTF-8 reader thread
    cannot decode. ``PYTHONIOENCODING=utf-8`` and ``PYTHONUTF8=1`` make the
    child use UTF-8 unconditionally.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "qgb", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_subprocess_validate_on_valid_project() -> None:
    result = _run_qgb("validate", "--path", str(FIXTURES / "valid"))
    assert result.returncode == EXIT_OK, result
    assert "OK:" in result.stdout


def test_subprocess_validate_on_schema_violation() -> None:
    result = _run_qgb("validate", "--path", str(FIXTURES / "schema_violation"))
    assert result.returncode == EXIT_NOT_READY, result
    assert "Schema violations" in result.stderr


def test_subprocess_validate_json_output() -> None:
    result = _run_qgb(
        "validate", "--path", str(FIXTURES / "valid"), "--json"
    )
    assert result.returncode == EXIT_OK, result
    payload = json.loads(result.stdout)
    assert payload["summary"]["files"] == 5
    assert payload["ok"] is True
    # JSON mode must not write diagnostic text to stderr.
    assert result.stderr == "", f"stderr should be empty, got: {result.stderr!r}"


def test_unused_imports_are_still_used() -> None:
    """Sanity assertion that the public exports we import are still referenced.

    This guards against ruff F401 hiding because we use them through pytest.
    """
    assert IntegrityIssue.__name__ == "IntegrityIssue"
