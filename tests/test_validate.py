"""Tests for the validate command (Step 2)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main
from qgb.core.validate import (
    FieldMismatch,
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


def test_run_validate_reports_schema_violations() -> None:
    report = run_validate(FIXTURES / "schema_violation")
    assert report.has_problems()
    assert report.schema_issues, "schema violations should be reported"
    # The policy fixture has an empty stage id, empty responsibility, and an
    # unknown verification_type. All three should surface.
    messages = " | ".join(fi.issue.message for fi in report.schema_issues)
    assert "shell_script" in messages, messages


def test_run_validate_reports_contract_field_mismatches() -> None:
    report = run_validate(FIXTURES / "field_mismatch")
    assert report.field_mismatches, "expected at least one field mismatch"
    # The contract declares verification_type=file_exists but also includes
    # `command` and `expected_exit_code` (which belong to verification_type=command).
    fields = sorted(fm.field_name for fm in report.field_mismatches)
    assert "command" in fields
    assert "expected_exit_code" in fields
    # No schema violations are expected on this fixture.
    assert not report.schema_issues, report.schema_issues


def test_run_validate_reports_invalid_json_as_read_error() -> None:
    report = run_validate(FIXTURES / "invalid_json")
    assert report.read_errors, "invalid JSON must be reported as a read error"
    path, message = report.read_errors[0]
    assert path.name == "config.json"
    assert "invalid JSON" in message


def test_run_validate_on_directory_without_quality_system_returns_empty(
    tmp_path: Path,
) -> None:
    report = run_validate(tmp_path)
    assert not report.files_checked
    assert not report.has_problems()


# ---- _check_contract_field_mismatch (unit) -------------------------------


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


def test_check_contract_field_mismatch_flags_foreign_fields() -> None:
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
        )
    ]


# ---- CLI: in-process via main() ------------------------------------------


def test_cli_validate_on_valid_project_exits_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "valid")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "OK:" in captured.out
    # No schema-violation or field-mismatch sections should appear.
    assert "Schema violations" not in captured.out
    assert "Contract field mismatches" not in captured.out


def test_cli_validate_on_schema_violation_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "schema_violation")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    # Problems are routed to stderr.
    assert "Schema violations" in captured.err


def test_cli_validate_on_field_mismatch_exits_not_ready(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["validate", "--path", str(FIXTURES / "field_mismatch")])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Contract field mismatches" in captured.err


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
    assert payload["summary"]["files"] == 5
    assert payload["summary"]["schema_issues"] == 0
    assert payload["summary"]["field_mismatches"] == 0
    assert payload["summary"]["read_errors"] == 0


def test_cli_validate_json_output_on_field_mismatch(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(
        ["validate", "--path", str(FIXTURES / "field_mismatch"), "--json"]
    )
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(captured.out)
    assert payload["summary"]["field_mismatches"] >= 1
    flagged = {item["field"] for item in payload["field_mismatches"]}
    assert "command" in flagged


# ---- subprocess smoke ----------------------------------------------------


def _run_qgb(*args: str) -> subprocess.CompletedProcess[str]:
    """Spawn `python -m qgb ...` with UTF-8 forced on both ends.

    Windows defaults to the active code page (e.g. CP932) for console I/O, so
    the child process can produce bytes the parent's UTF-8 reader thread
    cannot decode. ``PYTHONIOENCODING=utf-8`` and ``PYTHONUTF8=1`` make the
    child use UTF-8 unconditionally.
    """
    import os

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
