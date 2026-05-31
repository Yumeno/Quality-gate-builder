"""Step 6d 項目 2: qgb design-stages --commit (atomic).

Codex 計画レビュー方針:
- tmp project に copy → tmp の policy.json を差し替え → validate-policy(tmp)
- pass なら本物の policy.json を os.replace で atomic に入れ替え
- 失敗時は既存 policy.json を一切触らない
- 既存 stages[] が非空なら refuse、--force で上書き
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main

# ---- helpers -------------------------------------------------------------


def _init_minimal_project(root: Path, *, stages: list[dict] | None = None) -> None:
    """qgb init 相当の最小プロジェクトを手で組む.

    policy.json は generic-minimal と互換の形 (validate-policy が通る)。
    config.json も必要 (validate-policy が見る)。
    """
    qs = root / ".quality-system"
    qs.mkdir()
    (qs / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": stages or [],
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


def _policy(root: Path) -> dict:
    return json.loads(
        (root / ".quality-system" / "policy.json").read_text(encoding="utf-8")
    )


# ---- happy path ---------------------------------------------------------


def test_commit_writes_stages_to_policy(tmp_path: Path) -> None:
    """--commit で stages が policy.json に書かれる."""
    _init_minimal_project(tmp_path)
    exit_code = main(["design-stages", "--commit", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    policy = _policy(tmp_path)
    assert len(policy["stages"]) >= 2
    # generic-minimal の S1/S2 が入っている。
    ids = [s["id"] for s in policy["stages"]]
    assert ids == ["S1", "S2"]


def test_commit_preserves_non_stage_fields(tmp_path: Path) -> None:
    """policy_id など stages 以外の field は維持される."""
    _init_minimal_project(tmp_path)
    # policy_id を独自値に書き換える。
    pp = tmp_path / ".quality-system" / "policy.json"
    p = json.loads(pp.read_text(encoding="utf-8"))
    p["policy_id"] = "custom-policy"
    pp.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")

    assert main(["design-stages", "--commit", "--path", str(tmp_path)]) == EXIT_OK
    after = _policy(tmp_path)
    assert after["policy_id"] == "custom-policy"


def test_commit_json_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_minimal_project(tmp_path)
    exit_code = main(
        ["design-stages", "--commit", "--json", "--path", str(tmp_path)]
    )
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert parsed["committed"] is True


# ---- idempotency / refuse -----------------------------------------------


def test_commit_refuses_existing_stages_without_force(tmp_path: Path) -> None:
    """既に stages が入っている policy は --force なしで refuse."""
    existing = [
        {
            "id": "old",
            "name": "Existing",
            "responsibility": "previously adopted",
            "depends_on": [],
            "verification_type": "file_exists",
            "required_contract_fields": ["target"],
        }
    ]
    _init_minimal_project(tmp_path, stages=existing)
    exit_code = main(["design-stages", "--commit", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY
    # 既存 stages は無傷。
    after = _policy(tmp_path)
    assert after["stages"] == existing


def test_commit_force_overwrites_existing_stages(tmp_path: Path) -> None:
    existing = [
        {
            "id": "old",
            "name": "Existing",
            "responsibility": "previously adopted",
            "depends_on": [],
            "verification_type": "file_exists",
            "required_contract_fields": ["target"],
        }
    ]
    _init_minimal_project(tmp_path, stages=existing)
    exit_code = main(
        ["design-stages", "--commit", "--force", "--path", str(tmp_path)]
    )
    assert exit_code == EXIT_OK
    after = _policy(tmp_path)
    assert [s["id"] for s in after["stages"]] == ["S1", "S2"]


# ---- no quality-system ---------------------------------------------------


def test_commit_refuses_when_no_quality_system(tmp_path: Path) -> None:
    """qgb init が走っていない (policy.json なし) 場合 refuse."""
    exit_code = main(["design-stages", "--commit", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY


# ---- atomic: failure preserves original ----------------------------------


def test_commit_failure_leaves_original_policy_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """commit_design の途中で例外が起きても元の policy.json は無傷.

    os.replace を monkeypatch で raise させる。
    """
    _init_minimal_project(tmp_path)
    original_text = (tmp_path / ".quality-system" / "policy.json").read_text(
        encoding="utf-8"
    )

    import os
    real_replace = os.replace

    def fail_on_policy_replace(src: object, dst: object) -> None:
        dst_str = str(dst)
        if dst_str.endswith("policy.json"):
            raise OSError("simulated failure on final swap")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", fail_on_policy_replace)

    with pytest.raises(OSError, match="simulated failure on final swap"):
        main(["design-stages", "--commit", "--path", str(tmp_path)])

    # 元の policy.json は無傷。
    after = (tmp_path / ".quality-system" / "policy.json").read_text(
        encoding="utf-8"
    )
    assert after == original_text


def test_commit_staging_dir_is_cleaned_up(tmp_path: Path) -> None:
    """commit 成功後に <project>.qgb-stage/ は残らない."""
    _init_minimal_project(tmp_path)
    assert main(["design-stages", "--commit", "--path", str(tmp_path)]) == EXIT_OK

    parent = tmp_path.parent
    leftovers = [
        p for p in parent.iterdir()
        if p.is_dir() and p.name.endswith(".qgb-stage")
    ]
    assert not leftovers, leftovers


# ---- validate-policy gates commit ---------------------------------------


def test_commit_aborts_on_validate_policy_blocker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """validate-policy が blocker を出す状況 (config.json 欠落) なら refuse."""
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
    # config.json を作らない → validate-policy で blocker.

    exit_code = main(["design-stages", "--commit", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY
    # 元 policy は stages 空のまま。
    after = _policy(tmp_path)
    assert after["stages"] == []
