"""Step 8 項目 1: json_schema verification_type 実装.

Codex 計画レビュー方針:
- target / schema 両方 resolve_project_relative (R1 ガード)
- target / schema が JSON parse 失敗 → failed
- schema 自身が JSON Schema として malformed → failed
- $ref present → failed (Phase 1 では $ref unsupported)
- validate エラー (型違反 / required 欠落 / enum 違反) → failed
- format は Phase 1 では検査しない (docstring 明記)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from qgb.cli import EXIT_DENY, EXIT_OK, main

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


def _replace_with_json_schema_contract(
    project: Path,
    *,
    target: str,
    schema: str,
) -> None:
    """policy / req meta / contract を single json_schema stage に書き換える."""
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    policy["stages"] = [
        {
            "id": "S1",
            "name": "schema check",
            "responsibility": "target validates against schema",
            "depends_on": [],
            "verification_type": "json_schema",
            "required_contract_fields": ["target", "schema"],
        }
    ]
    pp.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")

    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = [meta["stages"][0]]
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    contracts_dir = project / ".quality-system" / "contracts" / "REQ-APP-001"
    contract = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "json_schema",
        "target": target,
        "schema": schema,
    }
    (contracts_dir / "S1.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _gate(project: Path) -> dict:
    return json.loads(
        (
            project
            / ".quality-system"
            / "evidence"
            / "REQ-APP-001"
            / "latest"
            / "gate.json"
        ).read_text(encoding="utf-8")
    )


def _stage_log(project: Path, stage_id: str) -> str:
    return (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / f"{stage_id}.log"
    ).read_text(encoding="utf-8")


# ---- happy path ---------------------------------------------------------


def test_valid_target_and_schema_passes(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo", "version": 1}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    gate = _gate(project)
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "passed"


# ---- validation error -------------------------------------------------


def test_target_violates_schema_fails(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo"}), encoding="utf-8"  # version 欠落
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    # 違反箇所 (path / message) が log に出る
    assert "required" in log.lower() or "version" in log.lower()


def test_type_violation_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo", "version": "not-an-int"}),
        encoding="utf-8",
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


# ---- target missing / unreadable -------------------------------------


def test_target_missing_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="does-not-exist.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "target" in log.lower()


def test_schema_missing_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="does-not-exist.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "schema" in log.lower()


# ---- malformed JSON / schema -----------------------------------------


def test_target_not_json_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text("not valid json {", encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


def test_schema_not_json_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text("not valid", encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


def test_schema_not_valid_json_schema_is_failed(tmp_path: Path) -> None:
    """schema 自身が JSON Schema として malformed (e.g. type が文字列でない) → failed."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": 123}), encoding="utf-8"  # type は string であるべき
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


# ---- R1: path escape -------------------------------------------------


def test_target_escape_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    # project の外に target を置く
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="../outside.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "outside the project root" in log


def test_schema_escape_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    outside = tmp_path / "outside.schema.json"
    outside.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="../outside.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "outside the project root" in log


# ---- $ref unsupported ----------------------------------------------


def test_schema_with_dollar_ref_is_failed(tmp_path: Path) -> None:
    """Codex 計画レビュー方針: Phase 1 では $ref unsupported。

    内部/外部問わず $ref が存在したら failed として扱う。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "$defs": {"X": {"type": "string"}},
                "properties": {"y": {"$ref": "#/$defs/X"}},
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "$ref" in log or "ref" in log.lower()


# ---- preflight support -----------------------------------------------


def test_json_schema_no_longer_unsupported_in_run(tmp_path: Path) -> None:
    """Step 8 で json_schema が runtime supported に加わる."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    from qgb.cli import EXIT_NOT_READY
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # NOT_READY ではなく実行される (passed)
    assert exit_code != EXIT_NOT_READY
