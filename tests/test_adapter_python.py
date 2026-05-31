"""Step 6c 項目 3: adapters/python 検出.

Phase 1 の Python adapter は静的・浅い・候補生成:

* マーカーファイル: pyproject.toml / setup.py / setup.cfg / requirements*.txt
* ``*.py`` がプロジェクト直下 or src/ 配下に複数
* framework 推定: pyproject.toml の dependencies から fastapi / django / flask
* test_runner 推定: pyproject に pytest / [tool.pytest...] / tests/ + test_*.py 規約
* confidence: pyproject + framework + runner 全部当たる → ~0.9
                   pyproject だけ → ~0.6
                   *.py だけ → ~0.3 (generic より高い)
"""

from __future__ import annotations

import shutil
from pathlib import Path

from qgb.adapters.python import PythonAdapter

# ---- 非該当 (None) ------------------------------------------------------


def test_returns_none_for_empty_dir(tmp_path: Path) -> None:
    assert PythonAdapter().detect(tmp_path) is None


def test_returns_none_for_pure_node_project(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "x", "version": "0.1.0"}\n', encoding="utf-8"
    )
    (tmp_path / "index.js").write_text("console.log(1);\n", encoding="utf-8")
    assert PythonAdapter().detect(tmp_path) is None


# ---- 該当 (Profile) -----------------------------------------------------


def test_detects_pyproject_toml(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.1"\n', encoding="utf-8"
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.language == "python"
    assert result.adapter_name == "python"
    # 物理事実が evidence に出ている。
    assert any(
        ev.kind == "file_exists" and ev.where == "pyproject.toml"
        for ev in result.evidence
    )


def test_detects_setup_py_only(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nsetup(name='x')\n", encoding="utf-8"
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.language == "python"


def test_detects_setup_cfg_only(tmp_path: Path) -> None:
    (tmp_path / "setup.cfg").write_text("[metadata]\nname = x\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.language == "python"


def test_detects_requirements_txt(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("requests>=2.0\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None


def test_detects_requirements_dev_variant(tmp_path: Path) -> None:
    """requirements-dev.txt / requirements.lock も Python signal."""
    (tmp_path / "requirements-dev.txt").write_text("pytest\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None


def test_detects_loose_py_files_with_low_confidence(tmp_path: Path) -> None:
    """マーカーが無くても .py が複数あれば低 confidence で当てる."""
    (tmp_path / "a.py").write_text("print(1)\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("print(2)\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("print(3)\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert 0.0 < result.confidence < 0.5  # generic より高く、明示マーカー より低い


def test_single_py_file_alone_does_not_trigger(tmp_path: Path) -> None:
    """1 個だけの .py は誤検出を避けるため non-match."""
    (tmp_path / "scratch.py").write_text("print(1)\n", encoding="utf-8")
    assert PythonAdapter().detect(tmp_path) is None


# ---- framework / test_runner --------------------------------------------


def test_pyproject_with_fastapi_dep_sets_framework(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["fastapi>=0.100", "uvicorn"]\n',
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.framework == "fastapi"


def test_pyproject_with_django_dep_sets_framework(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["django>=5.0"]\n',
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.framework == "django"


def test_pyproject_with_flask_dep_sets_framework(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["Flask>=3.0"]\n',
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.framework == "flask"


def test_pyproject_without_known_framework_leaves_framework_none(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["requests"]\n',
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.framework is None


def test_pyproject_with_pytest_dep_sets_test_runner(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (
            '[project]\nname = "x"\n'
            '[project.optional-dependencies]\ntest = ["pytest>=8.0"]\n'
        ),
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.test_runner == "pytest"


def test_pyproject_with_tool_pytest_section_sets_test_runner(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text(
        (
            '[project]\nname = "x"\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        ),
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.test_runner == "pytest"


def test_tests_dir_with_test_prefix_files_sets_pytest(tmp_path: Path) -> None:
    """tests/ + test_*.py 規約は pytest 推定 (pyproject 無しでも)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_a.py").write_text("def test_x(): pass\n", encoding="utf-8")
    (tests / "test_b.py").write_text("def test_y(): pass\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.test_runner == "pytest"


# ---- confidence ranking -------------------------------------------------


def test_confidence_strong_when_all_three_signals_present(tmp_path: Path) -> None:
    """pyproject + framework + test_runner が揃うと高 confidence (~0.9)."""
    (tmp_path / "pyproject.toml").write_text(
        (
            '[project]\nname = "x"\ndependencies = ["fastapi"]\n'
            '[project.optional-dependencies]\ntest = ["pytest"]\n'
        ),
        encoding="utf-8",
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.confidence >= 0.8


def test_confidence_medium_with_only_pyproject(tmp_path: Path) -> None:
    """pyproject のみで framework / runner 不明: 中程度 (0.5〜0.7)."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert 0.5 <= result.confidence <= 0.7


def test_confidence_loose_py_files_above_generic(tmp_path: Path) -> None:
    """*.py だけは generic (0.1) より高いが pyproject 単独より低い."""
    (tmp_path / "a.py").write_text("print()\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("print()\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("print()\n", encoding="utf-8")
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert 0.1 < result.confidence < 0.5


# ---- evidence path is project-root-relative ------------------------------


def test_evidence_where_is_relative(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n', encoding="utf-8"
    )
    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    for ev in result.evidence:
        assert not Path(ev.where).is_absolute(), ev.where


# ---- excluded dirs are not walked ---------------------------------------


def test_excluded_dirs_do_not_contribute_to_loose_py_count(tmp_path: Path) -> None:
    """venv/ や node_modules/ 配下の .py は数えない."""
    venv = tmp_path / ".venv"
    venv.mkdir()
    site = venv / "lib" / "site-packages"
    site.mkdir(parents=True)
    for i in range(10):
        (site / f"x{i}.py").write_text("pass\n", encoding="utf-8")
    # ルートには .py が 1 個だけ。
    (tmp_path / "scratch.py").write_text("pass\n", encoding="utf-8")
    # .venv を数えるとマッチしてしまうので、None になることを期待。
    assert PythonAdapter().detect(tmp_path) is None


# ---- realistic mini-project ---------------------------------------------


def test_realistic_mini_project_full_signal(tmp_path: Path) -> None:
    """src layout + tests + pyproject.toml + pytest + fastapi 全部入り."""
    (tmp_path / "pyproject.toml").write_text(
        (
            '[project]\nname = "demo"\n'
            'dependencies = ["fastapi>=0.110", "uvicorn"]\n'
            '[project.optional-dependencies]\n'
            'test = ["pytest>=8", "httpx"]\n'
            '[tool.pytest.ini_options]\n'
            'testpaths = ["tests"]\n'
        ),
        encoding="utf-8",
    )
    src = tmp_path / "src" / "demo"
    src.mkdir(parents=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    (src / "main.py").write_text(
        "from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8"
    )
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text(
        "def test_root(): pass\n", encoding="utf-8"
    )

    result = PythonAdapter().detect(tmp_path)
    assert result is not None
    assert result.language == "python"
    assert result.framework == "fastapi"
    assert result.test_runner == "pytest"
    assert result.confidence >= 0.8


def test_cleanup(tmp_path: Path) -> None:
    """tmp_path は pytest が自動掃除するが、念のため空にできることを担保."""
    (tmp_path / "junk.txt").write_text("x", encoding="utf-8")
    shutil.rmtree(tmp_path)
    assert not tmp_path.exists()
