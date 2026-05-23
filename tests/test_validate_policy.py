"""Step 6a Commit 3: acceptance tests for `qgb validate-policy`.

These tests cover the CLI entry point end-to-end (in-process via
qgb.cli.main) and the fixture-based regression suite that pins the
expected (kind, severity) for each design-quality failure mode. The
three fixtures (missing_required / dangling_ref / misplaced_contract)
are the "spec固定装置" the Codex Step 6 plan review called for: when
validate-policy's diagnostics change, these fixtures fail loudly and
force a deliberate doc update.

CLI exit code contract:

* blockers present       -> EXIT_NOT_READY (2)
* warnings only          -> EXIT_OK (0); stderr lists warnings
* clean                  -> EXIT_OK (0); stdout says "OK"

The runner-side qgb run preflight still treats the same situations as
blockers in the run-mode path; that distinction is checked in
tests/test_preflight_checks.py via check_runtime_support mode switch.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from qgb.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"
FIXTURE_ROOT = REPO_ROOT / "tests" / "fixtures" / "validate_policy"


def _copy_generic_minimal(dest: Path) -> Path:
    project = dest / "project"
    shutil.copytree(
        GENERIC_MINIMAL,
        project,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    return project


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _capture(argv: list[str]) -> tuple[int, str, str]:
    """Run qgb.cli.main and capture (exit_code, stdout, stderr)."""
    out = StringIO()
    err = StringIO()
    with patch("sys.stdout", out), patch("sys.stderr", err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


# ---- happy path / generic-minimal ---------------------------------------


def test_validate_policy_generic_minimal_warns_only(tmp_path: Path) -> None:
    """generic-minimal has only the stage_count warning (no blockers)."""
    project = _copy_generic_minimal(tmp_path)
    code, stdout, stderr = _capture(["validate-policy", "--path", str(project)])
    assert code == EXIT_OK
    # OK is silent on stdout when warnings are present (they go to stderr).
    assert "stage_count_out_of_range" in stderr
    assert "OK" not in stdout


def test_validate_policy_with_req_warns_only_for_minimal(tmp_path: Path) -> None:
    """Same: passing a REQ id resolves the REQ but still warns only."""
    project = _copy_generic_minimal(tmp_path)
    code, _, stderr = _capture(
        ["validate-policy", "REQ-APP-001", "--path", str(project)]
    )
    assert code == EXIT_OK
    assert "stage_count_out_of_range" in stderr


def test_validate_policy_json_output(tmp_path: Path) -> None:
    """--json emits machine-readable payload with separated blockers / warnings."""
    project = _copy_generic_minimal(tmp_path)
    code, stdout, _ = _capture(
        ["validate-policy", "--path", str(project), "--json"]
    )
    assert code == EXIT_OK
    payload = json.loads(stdout)
    assert payload["ok"] is True
    assert payload["req_id"] is None
    assert payload["status"] == "OK"
    assert payload["blockers"] == []
    assert any(
        w["kind"] == "stage_count_out_of_range" for w in payload["warnings"]
    )
    assert payload["summary"] == {"blockers": 0, "warnings": 1}


def test_validate_policy_clean_project_returns_ok(tmp_path: Path) -> None:
    """A policy in the 3..7 recommended band emits OK on stdout."""
    project = _copy_generic_minimal(tmp_path)
    # Extend to 3 stages so the stage_count warning disappears.
    policy_path = project / ".quality-system" / "policy.json"
    policy = _read_json(policy_path)
    extra = dict(policy["stages"][0])
    extra["id"] = "S3"
    extra["depends_on"] = []
    policy["stages"].append(extra)
    _write_json(policy_path, policy)

    code, stdout, stderr = _capture(["validate-policy", "--path", str(project)])
    assert code == EXIT_OK
    assert "OK" in stdout
    assert stderr == ""


# ---- usage errors --------------------------------------------------------


def test_validate_policy_nonexistent_path_is_usage_error(tmp_path: Path) -> None:
    code, _, stderr = _capture(
        ["validate-policy", "--path", str(tmp_path / "does-not-exist")]
    )
    assert code == EXIT_USAGE
    assert "path does not exist" in stderr


def test_validate_policy_file_path_is_usage_error(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    code, _, stderr = _capture(["validate-policy", "--path", str(f)])
    assert code == EXIT_USAGE
    assert "project directory" in stderr


# ---- fixtures: missing_required -----------------------------------------


def _load_fixture(name: str, dest: Path) -> Path:
    """Copy a fixture project into ``dest/<name>``."""
    src = FIXTURE_ROOT / name
    project = dest / name
    shutil.copytree(src, project)
    return project


def test_fixture_missing_required_is_blocker(tmp_path: Path) -> None:
    """Fixture: .quality-system/ is missing policy.json (or config.json).

    validate-policy must surface this as a blocker (NOT_READY exit 2),
    not as a warning, and certainly not as a clean pass. This is the
    primary "validate-policy 仕様固定装置" the Codex plan review asked
    for.
    """
    project = _load_fixture("missing_required", tmp_path)
    code, stdout, stderr = _capture(
        ["validate-policy", "--path", str(project), "--json"]
    )
    assert code == EXIT_NOT_READY
    payload = json.loads(stdout)
    assert payload["ok"] is False
    assert payload["status"] == "NOT_READY"
    kinds = {b["kind"] for b in payload["blockers"]}
    assert "missing_required_file" in kinds, kinds


def test_fixture_dangling_ref_is_blocker(tmp_path: Path) -> None:
    """Fixture: REQ meta cites stage_id missing from policy.json."""
    project = _load_fixture("dangling_ref", tmp_path)
    code, stdout, _ = _capture(
        [
            "validate-policy",
            "REQ-APP-001",
            "--path",
            str(project),
            "--json",
        ]
    )
    assert code == EXIT_NOT_READY
    payload = json.loads(stdout)
    kinds = {b["kind"] for b in payload["blockers"]}
    assert "unknown_stage_id" in kinds, kinds


def test_fixture_misplaced_contract_is_blocker(tmp_path: Path) -> None:
    """Fixture: contract_ref is outside the canonical layout."""
    project = _load_fixture("misplaced_contract", tmp_path)
    code, stdout, _ = _capture(
        [
            "validate-policy",
            "REQ-APP-001",
            "--path",
            str(project),
            "--json",
        ]
    )
    assert code == EXIT_NOT_READY
    payload = json.loads(stdout)
    kinds = {b["kind"] for b in payload["blockers"]}
    assert "misplaced_contract" in kinds, kinds


# ---- subprocess smoke ---------------------------------------------------


def _run_qgb_subprocess(*args: str) -> subprocess.CompletedProcess[str]:
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


def test_validate_policy_subprocess(tmp_path: Path) -> None:
    """Real entry-point smoke: python -m qgb validate-policy ... is wired."""
    project = _copy_generic_minimal(tmp_path)
    proc = _run_qgb_subprocess(
        "validate-policy", "--path", str(project), "--json"
    )
    assert proc.returncode == EXIT_OK
    payload = json.loads(proc.stdout)
    assert payload["status"] == "OK"


def test_validate_policy_help_shows_real_description() -> None:
    """--help no longer says 'not yet implemented'."""
    proc = _run_qgb_subprocess("validate-policy", "--help")
    assert proc.returncode == EXIT_OK
    assert "not yet implemented" not in proc.stdout
    assert "stage design quality" in proc.stdout
