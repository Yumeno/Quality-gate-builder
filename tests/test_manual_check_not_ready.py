"""Step 7 項目 C: manual_check を含む REQ → NOT_READY.

受け入れ条件 §12-15: manual_check を含む REQ の run は NOT_READY となる.

philosophy P6: LLM レビュー単独で ALLOW を出さない方針の機械化。manual_check
は人間判断であり、自動 ALLOW の根拠にはできない。

Step 6a で preflight に mode="run" / "validate_policy" の分岐は入っている
が、Step 7 で受け入れ条件 15 として独立にロックする。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


def _copy_generic_minimal(dest: Path) -> Path:
    target = dest / "generic-minimal"
    shutil.copytree(
        GENERIC_MINIMAL,
        target,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
    return target


def _inject_manual_check_stage(project: Path) -> None:
    """generic-minimal policy.json に S3=manual_check stage を追加."""
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    policy["stages"].append(
        {
            "id": "S3",
            "name": "human review",
            "responsibility": "human reviewer approves",
            "depends_on": ["S2"],
            "verification_type": "manual_check",
            "required_contract_fields": ["description"],
        }
    )
    pp.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # REQ meta に S3 を採用させる。
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"].append(
        {
            "stage_id": "S3",
            "contract_ref": ".quality-system/contracts/REQ-APP-001/S3.json",
            "required": True,
        }
    )
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # contract も足す (schema-valid)。
    contracts_dir = project / ".quality-system" / "contracts" / "REQ-APP-001"
    (contracts_dir / "S3.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "req_id": "REQ-APP-001",
                "stage_id": "S3",
                "verification_type": "manual_check",
                "description": "human reviewer must inspect target/sample.txt",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---- run: manual_check を含む REQ は NOT_READY -----------------------


def test_run_with_manual_check_stage_is_not_ready(tmp_path: Path) -> None:
    """受け入れ条件 15 そのまま. manual_check を 1 つでも含めば run は NOT_READY."""
    project = _copy_generic_minimal(tmp_path)
    _inject_manual_check_stage(project)

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


def test_run_with_manual_check_does_not_write_curated_gate(tmp_path: Path) -> None:
    """NOT_READY なので curated/latest/ の gate.json は生成されない."""
    project = _copy_generic_minimal(tmp_path)
    _inject_manual_check_stage(project)

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    curated = (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "gate.json"
    )
    assert not curated.exists()


def test_run_with_manual_check_json_reports_blocker(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _inject_manual_check_stage(project)

    import io
    import sys

    captured = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = captured
    try:
        exit_code = main(
            ["run", "REQ-APP-001", "--yes", "--json", "--path", str(project)]
        )
    finally:
        sys.stdout = real_stdout

    assert exit_code == EXIT_NOT_READY
    parsed = json.loads(captured.getvalue())
    assert parsed["status"] == "NOT_READY"
    kinds = {issue["kind"] for issue in parsed["issues"]}
    assert "manual_check_required" in kinds, kinds


# ---- validate-policy: manual_check は warning (Step 6a 挙動を維持) ----


def test_validate_policy_keeps_manual_check_as_warning(tmp_path: Path) -> None:
    """validate-policy では manual_check は blocker でなく warning.

    Step 6a で確立した「runtime と validate-policy で severity を変える」
    挙動。Step 7 でこれを壊さないことをロックする。
    """
    project = _copy_generic_minimal(tmp_path)
    _inject_manual_check_stage(project)

    exit_code = main(
        ["validate-policy", "REQ-APP-001", "--path", str(project)]
    )
    # warning は blocker でないので exit 0。
    assert exit_code == EXIT_OK


# ---- 全 stage が manual_check の REQ も NOT_READY (philosophy P6) ----


def test_manual_check_only_req_is_not_ready(tmp_path: Path) -> None:
    """全 stage manual_check の REQ は ALLOW を出せない (P6)."""
    project = _copy_generic_minimal(tmp_path)
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    # S1/S2 を manual_check に書き換える (極端ケース)。
    for stage in policy["stages"]:
        stage["verification_type"] = "manual_check"
        stage["required_contract_fields"] = ["description"]
    pp.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # contract も manual_check 用に書き換える。
    contracts_dir = project / ".quality-system" / "contracts" / "REQ-APP-001"
    for stage_id in ("S1", "S2"):
        cp = contracts_dir / f"{stage_id}.json"
        c = json.loads(cp.read_text(encoding="utf-8"))
        c["verification_type"] = "manual_check"
        c["description"] = f"manual check for {stage_id}"
        # 他 field は schema が許容するので残ってもいい。
        cp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY
