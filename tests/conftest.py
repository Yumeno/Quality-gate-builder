"""Shared test helpers for qgb tests.

Phase 2 Step 2.2 補修 A5 (Codex / subagent test-quality 中 反映):
patch substrate のテスト (`test_patch_apply.py` / `test_patch_cli.py`) で
重複定義されていた fixture / helper を集約。Phase 1 既存テストは引き続き
各ファイル内でローカル fixture を使うので、本ファイル追加で既存挙動への
影響はゼロ (新規 helper を pytest が自動で import するだけ)。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


@pytest.fixture
def copy_generic_minimal(tmp_path: Path):
    """Return a callable that copies examples/generic-minimal/ under tmp_path.

    Phase 2 Step 2.2 patch substrate のテストで頻出する pattern (Phase 1
    Step 5/6 から確立した「本物の example をコピーして tmp 上で操作」)。
    artifacts / evidence は最初から除外、artifacts は空 dir として再作成。
    """

    def _copy(name: str = "project") -> Path:
        target = tmp_path / name
        shutil.copytree(
            GENERIC_MINIMAL,
            target,
            ignore=shutil.ignore_patterns("artifacts", "evidence"),
        )
        (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
        return target

    return _copy


@pytest.fixture
def write_patch():
    """Return a callable that writes a list of patch ops to a JSON file."""

    def _write(path: Path, ops: list[dict]) -> None:
        path.write_text(
            json.dumps(ops, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    return _write


@pytest.fixture
def read_json():
    """Return a callable that reads a UTF-8 JSON file and returns parsed value."""

    def _read(path: Path) -> object:
        return json.loads(path.read_text(encoding="utf-8"))

    return _read


@pytest.fixture
def snapshot_dir():
    """Return a callable that snapshots every file under a directory as a dict."""

    def _snapshot(path: Path) -> dict[str, str]:
        snap: dict[str, str] = {}
        for f in path.rglob("*"):
            if f.is_file():
                snap[str(f.relative_to(path))] = f.read_text(encoding="utf-8")
        return snap

    return _snapshot
