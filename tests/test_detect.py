"""Step 6c 項目 4: core/detect.py と qgb detect CLI.

* core.detect: 全 adapter を順に呼び、最高 confidence の profile を
  selected に。他に当たった adapter は candidates に。generic は
  他 adapter が無い時のみ candidates に含む。
* CLI: text 出力 (緩くテスト) / JSON 出力 (構造を固定テスト)

Codex 計画レビューの指針:
- text 出力は将来の wording 変更に弱くしない (固定パターンを最小限)
- JSON は `{selected: {...}, candidates: [...]}` 形を固定
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qgb.cli import EXIT_OK, EXIT_USAGE, main
from qgb.core.detect import run_detect

# ---- core.detect: adapter コンポジション --------------------------------


def test_run_detect_on_python_project_selects_python(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi"]\n', encoding="utf-8"
    )
    result = run_detect(tmp_path)
    assert result.selected.language == "python"
    assert result.selected.adapter_name == "python"
    assert result.selected.framework == "fastapi"


def test_run_detect_on_empty_dir_falls_back_to_generic(tmp_path: Path) -> None:
    result = run_detect(tmp_path)
    assert result.selected.language == "generic"
    assert result.selected.adapter_name == "generic"
    # generic を含む候補リスト (他に当たる adapter が無いので generic が
    # candidates にも入る)。
    assert any(p.adapter_name == "generic" for p in result.candidates)


def test_run_detect_excludes_generic_when_specific_adapter_matches(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    result = run_detect(tmp_path)
    assert result.selected.adapter_name == "python"
    # candidates に generic は含まれない (他 adapter が当たったため)。
    assert not any(p.adapter_name == "generic" for p in result.candidates)


def test_run_detect_includes_python_in_candidates(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    result = run_detect(tmp_path)
    adapter_names = {p.adapter_name for p in result.candidates}
    assert "python" in adapter_names


# ---- CLI: text 出力 (緩い検査) ------------------------------------------


def test_qgb_detect_exits_ok_on_python(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi"]\n', encoding="utf-8"
    )
    exit_code = main(["detect", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    # 主要 token がどこかに出ること (固定 wording は避ける)。
    assert "python" in out


def test_qgb_detect_exits_ok_on_empty_dir(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """空ディレクトリでも generic が返るので exit 0."""
    exit_code = main(["detect", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    assert "generic" in out


def test_qgb_detect_exits_usage_for_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    exit_code = main(["detect", "--path", str(missing)])
    assert exit_code == EXIT_USAGE


# ---- CLI: JSON 出力 (構造を固定) ----------------------------------------


def test_qgb_detect_json_has_selected_and_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi"]\n', encoding="utf-8"
    )
    exit_code = main(["detect", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)

    assert parsed["ok"] is True
    assert "selected" in parsed
    assert "candidates" in parsed

    sel = parsed["selected"]
    # 必須フィールド (Phase 1 安定 schema)。
    expected_sel_keys = {
        "language",
        "framework",
        "test_runner",
        "confidence",
        "evidence",
        "adapter_name",
    }
    assert expected_sel_keys.issubset(set(sel.keys()))
    assert sel["language"] == "python"
    assert sel["framework"] == "fastapi"
    assert isinstance(sel["evidence"], list)
    for ev in sel["evidence"]:
        assert set(ev.keys()) >= {"kind", "where", "note"}
        assert not Path(ev["where"]).is_absolute()


def test_qgb_detect_json_empty_dir_has_generic_selected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(["detect", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["selected"]["language"] == "generic"
    assert parsed["selected"]["adapter_name"] == "generic"
    # generic は他に当たる adapter が無いので candidates にも入る。
    cand_names = [c["adapter_name"] for c in parsed["candidates"]]
    assert "generic" in cand_names


def test_qgb_detect_json_python_excludes_generic_from_candidates(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    exit_code = main(["detect", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    cand_names = [c["adapter_name"] for c in parsed["candidates"]]
    assert "generic" not in cand_names
    assert "python" in cand_names


# ---- CLI: --path 既定 (cwd) ---------------------------------------------


def test_qgb_detect_uses_cwd_when_path_not_given(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    exit_code = main(["detect"])
    assert exit_code == EXIT_OK
    out = capsys.readouterr().out
    assert "python" in out


# ---- Codex 補修分 -------------------------------------------------------


def test_qgb_detect_json_has_schema_version(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex 補修 7: JSON 出力に schema_version を含める.

    Step 6d 以降で detect の出力を消費するとき、互換性判定の入口となる。
    """
    exit_code = main(["detect", "--json", "--path", str(tmp_path)])
    assert exit_code == EXIT_OK
    parsed = json.loads(capsys.readouterr().out)
    assert parsed.get("schema_version") == 1


def test_run_detect_empty_adapters_list_raises_or_returns_generic(
    tmp_path: Path,
) -> None:
    """Codex 補修 4: ``adapters=[]`` は ``or`` で default に化けない.

    明示的に空リストを渡したら default は使われず、generic も含めて何も
    試行されないので fallback generic が返る (core 内の defensive branch)。
    """
    result = run_detect(tmp_path, adapters=[])
    # 「全 adapter (空) が profile 返さなかった」ので core の defensive
    # generic fallback ブランチが走り、generic profile が返る。
    assert result.selected.adapter_name == "generic"
    assert result.selected.language == "generic"


def test_qgb_detect_text_on_missing_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Codex 補修 1: 存在しないパスは依然 EXIT_USAGE (typo 検知)."""
    missing = tmp_path / "no-such-dir"
    exit_code = main(["detect", "--path", str(missing)])
    assert exit_code == EXIT_USAGE


def test_python_adapter_oserror_in_scan_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 補修 2: PythonAdapter._scan() が OSError を投げたら None を返す.

    これにより run_detect は generic フォールバック branch に降りられる。
    Windows での権限剥奪の代わりに _scan を直接差し替えてシミュレート。
    """
    from qgb.adapters.python import PythonAdapter

    (tmp_path / "marker.txt").write_text("x\n", encoding="utf-8")

    adapter = PythonAdapter()

    def boom(_root: Path) -> None:
        raise PermissionError("simulated")

    monkeypatch.setattr(adapter, "_scan", boom)
    assert adapter.detect(tmp_path) is None


def test_run_detect_falls_back_to_generic_when_specific_adapter_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 補修 2 統合: PythonAdapter が落ちても generic に到達する."""
    from qgb.adapters.generic import GenericAdapter
    from qgb.adapters.python import PythonAdapter

    (tmp_path / "marker.txt").write_text("x\n", encoding="utf-8")

    python_adapter = PythonAdapter()
    monkeypatch.setattr(
        python_adapter, "_scan",
        lambda _r: (_ for _ in ()).throw(PermissionError("simulated"))
    )

    result = run_detect(
        tmp_path, adapters=[python_adapter, GenericAdapter()]
    )
    assert result.selected.adapter_name == "generic"


def test_generic_distinguishes_unreadable_from_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Codex 補修 3: 読めないディレクトリは dir_unreadable evidence にする."""
    from qgb.adapters.generic import GenericAdapter

    adapter = GenericAdapter()
    # _top_level_visible が「読めない」を返す状態をシミュレート。
    monkeypatch.setattr(
        GenericAdapter, "_top_level_visible",
        staticmethod(lambda _root: ([], False))
    )
    result = adapter.detect(tmp_path)
    assert result is not None
    kinds = {ev.kind for ev in result.evidence}
    assert "dir_unreadable" in kinds
    assert "dir_empty" not in kinds


def test_qgb_detect_same_confidence_breaks_tie_by_registration_order(
    tmp_path: Path,
) -> None:
    """Codex 補修 5: 同 confidence は登録順 (max は最初に当たった方を返す)."""
    from qgb.adapters.base import (
        BaseAdapter,
        DetectedProjectProfile,
    )

    class AlphaAdapter(BaseAdapter):
        name = "alpha"

        def detect(self, project_root: Path) -> DetectedProjectProfile | None:
            return DetectedProjectProfile(
                language="alpha", framework=None, test_runner=None,
                confidence=0.5, evidence=[], adapter_name=self.name,
            )

    class BravoAdapter(BaseAdapter):
        name = "bravo"

        def detect(self, project_root: Path) -> DetectedProjectProfile | None:
            return DetectedProjectProfile(
                language="bravo", framework=None, test_runner=None,
                confidence=0.5, evidence=[], adapter_name=self.name,
            )

    # alpha 先に登録 → 同 confidence なら alpha が selected。
    result = run_detect(tmp_path, adapters=[AlphaAdapter(), BravoAdapter()])
    assert result.selected.language == "alpha"
    # 両方 candidates に入る。
    names = {p.adapter_name for p in result.candidates}
    assert names == {"alpha", "bravo"}


def test_qgb_detect_path_to_file_returns_usage(
    tmp_path: Path,
) -> None:
    """Codex 補修 1 補足: --path がファイルは依然 EXIT_USAGE."""
    file_path = tmp_path / "f.txt"
    file_path.write_text("x", encoding="utf-8")
    exit_code = main(["detect", "--path", str(file_path)])
    assert exit_code == EXIT_USAGE
