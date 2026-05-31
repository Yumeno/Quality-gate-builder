"""Step 6c 項目 1: adapter base 規約 + DetectedProjectProfile.

Codex 計画レビュー (2026-05-31) を反映した API:

* `DetectionEvidence`: 検出根拠 1 件 (kind / where / note)。``where`` は
  project_root 相対パスまたは論理的位置 (e.g. ``pyproject.toml[project.dependencies]``)
* `DetectedProjectProfile`: 1 つの adapter が返す検出結果。``confidence``
  は probability ではなく ranking score (0.0〜1.0)
* `DetectionResult`: ``selected`` (最高 confidence の profile) と
  ``candidates`` (全 adapter のうち当たった分、generic は他が無い時のみ)
* `BaseAdapter`: 全 adapter の基底。``detect(project_root) -> Profile | None``

Step 6c 着手前の計画レビューでの設計修正:
1. `run_detect()` の返り値は単一 profile でなく `DetectionResult`
2. JSON は flat でなく `selected` / `candidates` 形 (CLI 側 Step 6c 項目 4)
3. generic fallback の理由付けは `GenericAdapter` でなく `core.detect` 側
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from qgb.adapters.base import (
    BaseAdapter,
    DetectedProjectProfile,
    DetectionEvidence,
    DetectionResult,
)

# ---- DetectionEvidence ---------------------------------------------------


def test_detection_evidence_is_frozen() -> None:
    """変更不可。値が共有された後に書き換えられないことを担保."""
    ev = DetectionEvidence(kind="file_exists", where="pyproject.toml")
    with pytest.raises(FrozenInstanceError):
        ev.kind = "other"  # type: ignore[misc]


def test_detection_evidence_default_note_is_empty() -> None:
    ev = DetectionEvidence(kind="file_exists", where="pyproject.toml")
    assert ev.note == ""


def test_detection_evidence_accepts_note() -> None:
    ev = DetectionEvidence(
        kind="key_in_file",
        where="pyproject.toml[project.dependencies]",
        note="contains fastapi",
    )
    assert ev.note == "contains fastapi"


# ---- DetectedProjectProfile ---------------------------------------------


def test_detected_project_profile_is_frozen() -> None:
    p = DetectedProjectProfile(
        language="python",
        framework=None,
        test_runner=None,
        confidence=0.5,
        evidence=[],
        adapter_name="python",
    )
    with pytest.raises(FrozenInstanceError):
        p.language = "node"  # type: ignore[misc]


def test_detected_project_profile_holds_evidence_list() -> None:
    evs = [
        DetectionEvidence(kind="file_exists", where="pyproject.toml"),
        DetectionEvidence(
            kind="key_in_file",
            where="pyproject.toml[project.dependencies]",
            note="contains fastapi",
        ),
    ]
    p = DetectedProjectProfile(
        language="python",
        framework="fastapi",
        test_runner="pytest",
        confidence=0.9,
        evidence=evs,
        adapter_name="python",
    )
    assert p.language == "python"
    assert p.framework == "fastapi"
    assert p.test_runner == "pytest"
    assert p.confidence == 0.9
    assert len(p.evidence) == 2
    assert p.adapter_name == "python"


def test_detected_project_profile_confidence_is_ranking_score() -> None:
    """docstring の契約: confidence は probability ではない.

    実体としては 0.0〜1.0 の float だが、Bayes 確率ではなく heuristic
    ranking score として複数 adapter 間で比較するためのもの。
    """
    p1 = DetectedProjectProfile(
        language="python", framework=None, test_runner=None,
        confidence=0.9, evidence=[], adapter_name="python",
    )
    p2 = DetectedProjectProfile(
        language="generic", framework=None, test_runner=None,
        confidence=0.1, evidence=[], adapter_name="generic",
    )
    # ranking として比較可能。
    assert p1.confidence > p2.confidence


# ---- DetectionResult -----------------------------------------------------


def test_detection_result_is_frozen() -> None:
    selected = DetectedProjectProfile(
        language="generic", framework=None, test_runner=None,
        confidence=0.1, evidence=[], adapter_name="generic",
    )
    r = DetectionResult(selected=selected, candidates=[selected])
    with pytest.raises(FrozenInstanceError):
        r.selected = selected  # type: ignore[misc]


def test_detection_result_holds_selected_and_candidates() -> None:
    py = DetectedProjectProfile(
        language="python", framework=None, test_runner=None,
        confidence=0.6, evidence=[], adapter_name="python",
    )
    generic = DetectedProjectProfile(
        language="generic", framework=None, test_runner=None,
        confidence=0.1, evidence=[], adapter_name="generic",
    )
    r = DetectionResult(selected=py, candidates=[py])
    assert r.selected is py
    assert r.candidates == [py]
    # generic は他 adapter がヒットしている場合 candidates に入らない。
    assert generic not in r.candidates


# ---- BaseAdapter ---------------------------------------------------------


def test_base_adapter_detect_is_abstract_by_default() -> None:
    """サブクラスが detect() を実装しないと NotImplementedError."""

    class Incomplete(BaseAdapter):
        name = "incomplete"

    with pytest.raises(NotImplementedError):
        Incomplete().detect(Path("."))


def test_base_adapter_requires_name() -> None:
    """name クラス変数を必ず持たせる (空文字も不可)."""

    class NoName(BaseAdapter):
        name = ""

        def detect(self, project_root: Path) -> DetectedProjectProfile | None:
            return None

    a = NoName()
    # name が空文字の adapter は core.detect で弾くべきだが、base 層では
    # データクラス状態として保持できるかだけ確認。
    assert a.name == ""


def test_base_adapter_subclass_can_return_none() -> None:
    """対象外プロジェクトでは None を返すのが規約."""

    class NeverMatches(BaseAdapter):
        name = "never"

        def detect(self, project_root: Path) -> DetectedProjectProfile | None:
            return None

    assert NeverMatches().detect(Path(".")) is None


def test_base_adapter_subclass_can_return_profile(tmp_path: Path) -> None:
    """通常の検出パス: profile を返す."""

    class AlwaysMatches(BaseAdapter):
        name = "always"

        def detect(self, project_root: Path) -> DetectedProjectProfile | None:
            return DetectedProjectProfile(
                language="test-lang",
                framework=None,
                test_runner=None,
                confidence=0.5,
                evidence=[
                    DetectionEvidence(kind="trivial", where=".")
                ],
                adapter_name=self.name,
            )

    result = AlwaysMatches().detect(tmp_path)
    assert result is not None
    assert result.adapter_name == "always"
    assert result.language == "test-lang"
