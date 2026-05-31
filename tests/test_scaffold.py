"""Step 6d 項目 3: qgb scaffold (REQ + contract + L1/L5 雛形).

Codex 計画レビュー方針:
- REQ id を `^REQ-[A-Z0-9]+-[0-9]{3,}$` で入口バリデート
- 生成物は **schema-valid な placeholder** で出す (qgb validate が即落ちない)
- L1 / L5 のみ最小ディレクトリ生成 (Phase 1 focus)
- 既存 REQ がある場合 --force なしで refuse (exit 2)
- --force は対象 REQ 範囲のみ (policy.json や他 REQ に触らない)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main

# ---- helpers -------------------------------------------------------------


def _init_project_with_stages(root: Path) -> None:
    """scaffold が動く最小環境: policy.json に generic-minimal stages を入れる."""
    qs = root / ".quality-system"
    qs.mkdir()
    (qs / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": [
                    {
                        "id": "S1",
                        "name": "Existence",
                        "responsibility": "target file exists",
                        "depends_on": [],
                        "verification_type": "file_exists",
                        "required_contract_fields": ["target"],
                    },
                    {
                        "id": "S2",
                        "name": "Content",
                        "responsibility": "target contains keywords",
                        "depends_on": ["S1"],
                        "verification_type": "substring_match",
                        "required_contract_fields": ["target", "must_contain"],
                    },
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (qs / "config.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project": {"name": "test-project"},
                "qgb": {"core_language": "python", "version": "0.1.0"},
                "commands": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---- happy path ---------------------------------------------------------


def test_scaffold_generates_req_meta(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    meta = tmp_path / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    assert meta.is_file()
    payload = json.loads(meta.read_text(encoding="utf-8"))
    assert payload["req_id"] == "REQ-APP-001"
    assert len(payload["stages"]) == 2
    for s in payload["stages"]:
        assert s["required"] is True


def test_scaffold_generates_contracts_per_stage(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    contracts_dir = tmp_path / ".quality-system" / "contracts" / "REQ-APP-001"
    assert contracts_dir.is_dir()
    assert (contracts_dir / "S1.json").is_file()
    assert (contracts_dir / "S2.json").is_file()


def test_scaffold_contracts_are_schema_valid(tmp_path: Path) -> None:
    """Codex 補修方針: 生成物は schema-valid な placeholder.

    qgb validate を直接呼ぶことで「scaffold 直後に validate が通る」
    ことを担保する。
    """
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    assert main(["validate", "--path", str(tmp_path)]) == EXIT_OK


def test_scaffold_creates_l1_l5_test_dirs(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    tests_root = tmp_path / "tests" / "quality"
    assert (tests_root / "L1_behavior").is_dir()
    assert (tests_root / "L5_contract").is_dir()


def test_scaffold_does_not_create_l2_l3_l4_l6(tmp_path: Path) -> None:
    """Phase 1 focus は L1/L5 のみ。他は Phase 2 送りなので scaffold しない."""
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    tests_root = tmp_path / "tests" / "quality"
    for unwanted in ("L2_state", "L3_boundary", "L4_flow", "L6_experience"):
        assert not (tests_root / unwanted).exists(), unwanted


def test_scaffold_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_project_with_stages(tmp_path)
    exit_code = main(
        ["scaffold", "REQ-APP-001", "--json", "--path", str(tmp_path)]
    )
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert parsed["req_id"] == "REQ-APP-001"
    assert "created" in parsed


# ---- REQ id validation -------------------------------------------------


def test_scaffold_rejects_invalid_req_id(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    for bad in ["REQ-app-001", "REQ-X-12", "INVALID", "REQ-APP-1", ""]:
        exit_code = main(["scaffold", bad, "--path", str(tmp_path)])
        assert exit_code == EXIT_USAGE, bad


def test_scaffold_accepts_valid_req_ids(tmp_path: Path) -> None:
    """REQ-XXX-NNN 形式の id を受け入れる (XXX は大文字英数字、NNN は 3 桁以上)."""
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    # 別 REQ も別 path で OK。
    other = tmp_path.parent / "scaffold_alt"
    other.mkdir()
    _init_project_with_stages(other)
    assert main(["scaffold", "REQ-WEB-1234", "--path", str(other)]) == EXIT_OK


# ---- policy 必須 ---------------------------------------------------------


def test_scaffold_refuses_when_no_policy(tmp_path: Path) -> None:
    """policy.json が無い (= qgb init / design-stages --commit 未) 場合 refuse."""
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY


def test_scaffold_refuses_when_policy_has_no_stages(tmp_path: Path) -> None:
    """policy.json はあるが stages 空 (design-stages --commit 未) なら refuse."""
    qs = tmp_path / ".quality-system"
    qs.mkdir()
    (qs / "policy.json").write_text(
        json.dumps(
            {"schema_version": "1.0", "policy_id": "default", "stages": []},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (qs / "config.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project": {"name": "x"},
                "qgb": {"core_language": "python", "version": "0.1.0"},
                "commands": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY


# ---- idempotency --------------------------------------------------------


def test_scaffold_refuses_existing_req_without_force(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    # 2 回目は --force なしで refuse。
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY


def test_scaffold_force_overwrites_existing(tmp_path: Path) -> None:
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK

    # ユーザー編集を模した contract 改変を仕込む。
    s1 = (
        tmp_path / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    )
    edited = json.loads(s1.read_text(encoding="utf-8"))
    edited["target"] = "edited/by/user.txt"
    s1.write_text(
        json.dumps(edited, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --force で再生成。ユーザー編集は上書きされる。
    assert (
        main(["scaffold", "REQ-APP-001", "--force", "--path", str(tmp_path)])
        == EXIT_OK
    )
    after = json.loads(s1.read_text(encoding="utf-8"))
    assert after["target"] != "edited/by/user.txt"


def test_scaffold_force_does_not_touch_policy(tmp_path: Path) -> None:
    """--force は scaffold 対象 REQ のみ。policy.json は触らない."""
    _init_project_with_stages(tmp_path)
    pp = tmp_path / ".quality-system" / "policy.json"
    before = pp.read_text(encoding="utf-8")
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    assert (
        main(["scaffold", "REQ-APP-001", "--force", "--path", str(tmp_path)])
        == EXIT_OK
    )
    after = pp.read_text(encoding="utf-8")
    assert before == after


def test_scaffold_force_does_not_touch_other_reqs(tmp_path: Path) -> None:
    """--force は同 REQ のみ。他 REQ の meta/contracts は無傷."""
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK
    assert main(["scaffold", "REQ-WEB-002", "--path", str(tmp_path)]) == EXIT_OK

    other_meta = (
        tmp_path / ".quality-system" / "req" / "REQ-WEB-002.meta.json"
    )
    before = other_meta.read_text(encoding="utf-8")

    assert (
        main(["scaffold", "REQ-APP-001", "--force", "--path", str(tmp_path)])
        == EXIT_OK
    )
    after = other_meta.read_text(encoding="utf-8")
    assert before == after


# ---- usage error --------------------------------------------------------


def test_scaffold_missing_path_returns_usage(tmp_path: Path) -> None:
    missing = tmp_path / "no-such"
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(missing)])
    assert exit_code == EXIT_USAGE


def test_scaffold_path_to_file_returns_usage(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(f)])
    assert exit_code == EXIT_USAGE


# ---- end-to-end with run -----------------------------------------------


def test_scaffold_then_run_yields_deny_on_placeholders(tmp_path: Path) -> None:
    """scaffold 直後に run は DENY (placeholder なので実際は fail).

    Codex 計画レビュー: 「scaffold は schema-valid だが run で誤って
    PASS しない placeholder」が望ましい。schema 通過 + run で fail を
    両立することを担保する。
    """
    _init_project_with_stages(tmp_path)
    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK

    # qgb validate は通る (placeholder は schema-valid)。
    assert main(["validate", "--path", str(tmp_path)]) == EXIT_OK
    # qgb validate-policy は通る (contract 解決 + canonical layout 成立)。
    assert (
        main(["validate-policy", "REQ-APP-001", "--path", str(tmp_path)])
        == EXIT_OK
    )

    # qgb run は placeholder なので DENY (target が実在しない)。
    from qgb.cli import EXIT_DENY

    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--path", str(tmp_path)]
    )
    assert exit_code == EXIT_DENY
