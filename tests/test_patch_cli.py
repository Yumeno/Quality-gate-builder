"""Tests for `qgb patch` CLI (Phase 2 Step 2.2 prejournal §6.5).

CLI 経路の exit code / `--json` / `--dry-run` / 警告ハンドリングを spec lock。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from qgb.cli import EXIT_DENY, EXIT_NOT_READY, EXIT_OK, main

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


def _copy_generic_minimal(dest: Path) -> Path:
    target = dest / "project"
    shutil.copytree(
        GENERIC_MINIMAL,
        target,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
    return target


def _write_patch(path: Path, ops: list[dict]) -> None:
    path.write_text(json.dumps(ops, ensure_ascii=False, indent=2), encoding="utf-8")


# ---- happy path ----------------------------------------------------------


def test_patch_applies_and_returns_exit_ok(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(
        patch,
        [{"op": "add", "path": "/description", "value": "added by CLI"}],
    )
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
        ]
    )
    assert exit_code == EXIT_OK


def test_patch_json_output(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(
        patch,
        [{"op": "add", "path": "/description", "value": "added by JSON test"}],
    )
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["ok"] is True
    assert payload["target_kind"] == "policy"
    assert payload["written"] is True
    assert payload["would_write"] is True
    assert payload["dry_run"] is False


def test_patch_dry_run_does_not_write_and_returns_ok(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(
        patch,
        [{"op": "add", "path": "/description", "value": "phantom"}],
    )
    policy_before = (project / ".quality-system" / "policy.json").read_text(
        encoding="utf-8"
    )
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
            "--dry-run",
            "--json",
        ]
    )
    assert exit_code == EXIT_OK
    policy_after = (project / ".quality-system" / "policy.json").read_text(
        encoding="utf-8"
    )
    assert policy_before == policy_after
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert payload["would_write"] is True
    assert payload["written"] is False
    assert payload["dry_run"] is True


# ---- failure paths -------------------------------------------------------


def test_patch_schema_violation_returns_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """``move`` op is reserved for Phase 3 → patch schema rejects it."""
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(patch, [{"op": "move", "path": "/a", "from": "/b"}])
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["reason"] == "patch_schema_violation"


def test_patch_target_schema_violation_returns_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(patch, [{"op": "remove", "path": "/schema_version"}])
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "target_schema_violation"


def test_patch_absolute_target_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(patch, [{"op": "add", "path": "/foo", "value": 1}])
    abs_target = str((project / ".quality-system" / "policy.json").resolve())
    exit_code = main(
        [
            "patch",
            abs_target,
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "target_path_invalid"


def test_patch_outside_quality_system_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    project = _copy_generic_minimal(tmp_path)
    patch = tmp_path / "p.json"
    _write_patch(patch, [{"op": "add", "path": "/foo", "value": 1}])
    exit_code = main(
        [
            "patch",
            "README.md",
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "target_path_invalid"


def test_patch_file_missing_returns_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    project = _copy_generic_minimal(tmp_path)
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(tmp_path / "missing.json"),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "patch_not_found"


def test_patch_validate_policy_blocker_returns_deny(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When the patched view passes target schema but fails validate-policy
    (e.g. duplicate stage_id), the exit code is EXIT_DENY (1), not
    EXIT_NOT_READY (2). Codex 計画レビュー指摘 11 採用。"""
    project = _copy_generic_minimal(tmp_path)
    # Inject a duplicate stage id via patch: clone S1 into a second entry.
    patch = tmp_path / "p.json"
    # The generic-minimal policy.json has stages: [S1, S2]. Add a 3rd entry
    # with id="S1" (duplicate) — policy.schema may permit it (it doesn't
    # enforce uniqueness), but validate-policy reports duplicate_stage_id.
    stage_copy = {
        "id": "S1",
        "name": "duplicate of S1",
        "responsibility": "duplicate",
        "depends_on": [],
        "verification_type": "file_exists",
        "required_contract_fields": ["target"],
    }
    _write_patch(
        patch,
        [{"op": "add", "path": "/stages/-", "value": stage_copy}],
    )
    exit_code = main(
        [
            "patch",
            ".quality-system/policy.json",
            str(patch),
            "--path",
            str(project),
            "--json",
        ]
    )
    assert exit_code == EXIT_DENY
    payload = json.loads(capsys.readouterr().out)
    assert payload["reason"] == "validate_policy_blocker"
    # Original file is unchanged.
    policy = json.loads(
        (project / ".quality-system" / "policy.json").read_text(encoding="utf-8")
    )
    # The duplicate was NOT applied.
    assert sum(1 for s in policy["stages"] if s["id"] == "S1") == 1
