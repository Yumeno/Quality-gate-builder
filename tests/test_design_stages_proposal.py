"""Step 6d 項目 1: qgb design-stages 提案フェーズ (Phase 3 Step 3.0 で detect 廃止反映).

Phase 1 のルールベース推定 + ユーザー確認の提案部分:

* template (Phase 1 は examples/generic-minimal 1 種のみ) の policy.json を読む
* "提案された stages 案" を text / JSON で表示
* policy.json は **書かない** (提案のみ)

Phase 3 Step 3.0 change:
- detect 関連テスト (banner 検査 / pyproject による python 反映 / JSON detect field) は削除
- 対象プロジェクトの自己定義は project-context.{md,json} に移行 (本テストの守備範囲外)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qgb.cli import EXIT_OK, EXIT_USAGE, main

# ---- text 出力 -----------------------------------------------------------


def test_design_stages_emits_proposal_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """空ディレクトリで stage 提案が text に出る (Phase 3 Step 3.0: detect banner なし)."""
    exit_code = main(["design-stages", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    # Phase 3 Step 3.0: "Detected" banner は廃止 (detect 機能撤去)。
    # template 名と stage 提案セクションだけが必須。
    assert "Recommended template" in out
    assert "Proposed stages" in out or "proposed" in out.lower()
    # generic-minimal template の stage が出ている。
    assert "S1" in out
    assert "S2" in out


def test_design_stages_does_not_write_policy(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """提案フェーズは policy.json を書かない."""
    # qgb init 相当の最小構造を手で作る。
    qs = tmp_path / ".quality-system"
    qs.mkdir()
    initial_policy = {"schema_version": "1.0", "policy_id": "default", "stages": []}
    (qs / "policy.json").write_text(
        json.dumps(initial_policy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["design-stages", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK

    # policy.json は変更されない。
    after = json.loads((qs / "policy.json").read_text(encoding="utf-8"))
    assert after == initial_policy


# Phase 3 Step 3.0 廃止: test_design_stages_reflects_detect_language_in_text
# は detect 機能を前提とするテストだったので削除 (detect 自体が撤去された)。


# ---- JSON 出力 -----------------------------------------------------------


def test_design_stages_json_has_proposal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--json は schema_version + proposed stages を含む (Phase 3 Step 3.0: detect なし)."""
    exit_code = main(["design-stages", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["schema_version"] == 1
    assert parsed["ok"] is True
    assert "committed" in parsed and parsed["committed"] is False

    # Phase 3 Step 3.0: detect フィールドは出力されない。
    assert "detect" not in parsed

    # proposed stages がリストで入る。
    assert "proposed" in parsed
    stages = parsed["proposed"]["stages"]
    assert isinstance(stages, list)
    assert len(stages) >= 2
    for s in stages:
        assert "id" in s
        assert "name" in s
        assert "responsibility" in s
        assert "verification_type" in s


def test_design_stages_json_includes_template_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """どの template を使ったかが JSON に出る (utility for design-notes)."""
    exit_code = main(["design-stages", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert "template" in parsed["proposed"]
    template_name = parsed["proposed"]["template"]
    # Phase 1 は generic-minimal only.
    assert template_name == "generic-minimal"


# ---- usage error ---------------------------------------------------------


def test_design_stages_exit_usage_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    exit_code = main(["design-stages", "--path", str(missing)])
    assert exit_code == EXIT_USAGE


def test_design_stages_exit_usage_for_file_path(tmp_path: Path) -> None:
    f = tmp_path / "f.txt"
    f.write_text("x", encoding="utf-8")
    exit_code = main(["design-stages", "--path", str(f)])
    assert exit_code == EXIT_USAGE


# ---- template の stage 構造 ---------------------------------------------


def test_proposed_stages_are_loaded_from_template(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """generic-minimal template の S1/S2 が提案される (Phase 1 の唯一の template)."""
    exit_code = main(["design-stages", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    stage_ids = [s["id"] for s in parsed["proposed"]["stages"]]
    assert stage_ids == ["S1", "S2"]
