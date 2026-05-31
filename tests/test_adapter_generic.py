"""Step 6c 項目 2: adapters/generic フォールバック.

generic adapter は **常に** ``DetectedProjectProfile`` を返し、決して
``None`` を返さない。confidence は全 adapter の中で最低。

Codex 計画レビューの指針:
- generic は「他 adapter が当たらなかった」理由を **adapter 内に書かない**
  (= 自分が他 adapter の結果を知っているフリをしない)。
- 単純に「ファイルが何かしらある」「ディレクトリとして読める」程度の物理事実を
  evidence として返す。
- 「fallback として選ばれた理由」は ``core.detect`` 側で付ける。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from qgb.adapters.generic import GenericAdapter


def test_generic_returns_profile_on_empty_dir(tmp_path: Path) -> None:
    """空ディレクトリでも profile を返す (必ず非 None)."""
    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    assert result.language == "generic"
    assert result.adapter_name == "generic"
    assert result.framework is None
    assert result.test_runner is None


def test_generic_confidence_is_lowest(tmp_path: Path) -> None:
    """confidence は他のどの adapter より低い想定 (Phase 1 では <=0.2)."""
    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    assert 0.0 < result.confidence <= 0.2


def test_generic_records_at_least_one_evidence(tmp_path: Path) -> None:
    """evidence が空でない (合格根拠を必ず残す思想 P7).

    fallback の場合でも「ディレクトリが読めた」など最低限の物理事実は記録する。
    """
    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    assert result.evidence, "generic adapter must produce at least one evidence"


def test_generic_evidence_paths_are_relative(tmp_path: Path) -> None:
    """evidence[].where は project-root 相対 (絶対パスを漏らさない)."""
    # ディレクトリ内に何かファイルを置く。
    (tmp_path / "README.md").write_text("hi\n", encoding="utf-8")
    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    for ev in result.evidence:
        assert not Path(ev.where).is_absolute(), (
            f"evidence.where must be relative: {ev.where}"
        )


def test_generic_does_not_claim_framework_or_runner(tmp_path: Path) -> None:
    """ファイルが何かあっても framework / test_runner は決して埋めない."""
    (tmp_path / "main.py").write_text("print('hi')\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}\n", encoding="utf-8")
    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    assert result.framework is None
    assert result.test_runner is None


def test_generic_does_not_inspect_known_excluded_dirs(tmp_path: Path) -> None:
    """venv / node_modules / .git などはそもそも見にいかない.

    探索除外は generic でも守る (絶対パスや膨大なファイル数を evidence に
    含めないため)。テストは「evidence の where に .git や node_modules が
    出ない」ことで担保。
    """
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]\n", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.js").write_text("//\n", encoding="utf-8")
    (tmp_path / "real.txt").write_text("content\n", encoding="utf-8")

    result = GenericAdapter().detect(tmp_path)
    assert result is not None
    bad_paths = {".git", "node_modules"}
    for ev in result.evidence:
        head = Path(ev.where).parts[0] if Path(ev.where).parts else ""
        assert head not in bad_paths, (
            f"generic evidence must skip excluded dir {head}: {ev}"
        )


def test_generic_returns_profile_when_path_is_missing_dir(tmp_path: Path) -> None:
    """ディレクトリが存在しなくても None でなく profile を返す or
    呼び出し側に判断を委ねる。

    Phase 1 では「core.detect が project_root の存在確認を先にやる」
    契約のため、ここでは tmp_path に存在しないサブパスを渡しても落ちない
    ことだけ確認 (例外を投げない)。
    """
    missing = tmp_path / "does-not-exist"
    # 例外を投げないことを担保。
    try:
        result = GenericAdapter().detect(missing)
    except Exception as exc:  # noqa: BLE001 - 明示的に守る
        pytest.fail(f"GenericAdapter raised for missing path: {exc!r}")
    # 結果は None でも profile でも可。Phase 1 は profile 返却に統一。
    assert result is not None
    assert result.language == "generic"
