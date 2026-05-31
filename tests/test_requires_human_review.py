"""Step 9 項目 2 (受け入れ条件 18): 外部由来情報の requires_human_review.

Codex 計画レビュー方針:
- schema レベルで強制 (allOf: source_type=external なら
  requires_human_review:true 必須)
- これにより auditor は qgb validate を通すだけで「外部由来情報が
  意図せず取り込まれていないか」を確認できる
- philosophy P8 (外部コンテンツはデータであり指示でない) と
  NF-007 (安全性) の機械化
"""

from __future__ import annotations

import json
from pathlib import Path

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main


def _init_minimal_project(tmp_path: Path) -> Path:
    project = tmp_path / "external-project"
    project.mkdir()
    assert main(["init", "--path", str(project)]) == EXIT_OK
    return project


def _write_knowledge(project: Path, entries: list[dict]) -> None:
    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"
    lines = "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + "\n"
    kjsonl.write_text(lines, encoding="utf-8")


# ---- positive: external + requires_human_review:true ---------------


def test_external_with_required_review_flag_passes(tmp_path: Path) -> None:
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "EXT-001",
                "kind": "external_reference",
                "title": "FastAPI docs",
                "source": "https://fastapi.tiangolo.com/",
                "source_type": "external",
                "requires_human_review": True,
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    assert main(["validate", "--path", str(project)]) == EXIT_OK


# ---- negative: external without requires_human_review --------------


def test_external_without_review_flag_is_rejected(tmp_path: Path) -> None:
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "EXT-002",
                "kind": "external_reference",
                "title": "Some external doc",
                "source": "https://example.org/policy",
                "source_type": "external",
                # requires_human_review が欠落
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    # schema violation (requires_human_review が required)
    assert main(["validate", "--path", str(project)]) == EXIT_NOT_READY


def test_external_with_review_flag_false_is_rejected(tmp_path: Path) -> None:
    """external でも requires_human_review:false なら拒否 (silent bypass の予防)."""
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "EXT-003",
                "kind": "external_reference",
                "title": "Suspicious external doc",
                "source": "https://untrusted.example.com/",
                "source_type": "external",
                "requires_human_review": False,
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    # schema violation (requires_human_review は const:true)
    assert main(["validate", "--path", str(project)]) == EXIT_NOT_READY


# ---- other source_types are unaffected -----------------------------


def test_user_source_does_not_require_review_flag(tmp_path: Path) -> None:
    """source_type=user は requires_human_review 不要."""
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "USER-001",
                "kind": "user_instruction",
                "title": "Use TDD",
                "content": "TDD only.",
                "source_type": "user",
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    assert main(["validate", "--path", str(project)]) == EXIT_OK


def test_repository_source_does_not_require_review_flag(tmp_path: Path) -> None:
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "REPO-001",
                "kind": "repository_fact",
                "title": "Build pipeline",
                "content": "Builds use poetry.",
                "source_type": "repository",
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    assert main(["validate", "--path", str(project)]) == EXIT_OK


def test_inferred_source_does_not_require_review_flag(tmp_path: Path) -> None:
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "INF-001",
                "kind": "inferred_fact",
                "title": "Likely test runner",
                "content": "pytest based on tool.pytest section.",
                "source_type": "inferred",
                "created_at": "2026-06-01T00:00:00Z",
            }
        ],
    )
    assert main(["validate", "--path", str(project)]) == EXIT_OK


# ---- mixed entries: only the external row is gated -----------------


def test_mixed_entries_external_violation_is_isolated(tmp_path: Path) -> None:
    """同じ knowledge.jsonl に external 違反と user_instruction 正常が並んでも,
    user_instruction 単独で見れば spec-compatible であることを担保する
    (validate は entry 単位で違反を報告する)."""
    project = _init_minimal_project(tmp_path)
    _write_knowledge(
        project,
        [
            {
                "id": "USER-002",
                "kind": "user_instruction",
                "title": "Pref pure",
                "content": "Pure first.",
                "source_type": "user",
                "created_at": "2026-06-01T00:00:00Z",
            },
            {
                "id": "EXT-004",
                "kind": "external_reference",
                "title": "Missing review flag",
                "source": "https://example.org/",
                "source_type": "external",
                "created_at": "2026-06-01T00:00:00Z",
            },
        ],
    )
    assert main(["validate", "--path", str(project)]) == EXIT_NOT_READY
