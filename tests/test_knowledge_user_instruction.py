"""Step 9 項目 1 (受け入れ条件 17): user_instruction を knowledge.jsonl に保存.

Codex 計画レビュー方針:
- Phase 1 MVP は **手編集 + qgb validate の schema 通過** で「保存できる」を満たす
- 新規 CLI (`qgb add-knowledge`) は Phase 2 送り
- 既存 `_record_waiver_knowledge` (Step 7) との一貫性は維持しつつ、
  user_instruction は curated fact、waiver は runtime event として
  source / lifecycle が異なる

このテストは次を担保する:
1. `qgb init` が knowledge/knowledge.jsonl を生成する
2. user_instruction を手編集で追記した後の knowledge.jsonl は
   schema-valid で、qgb validate を通る
3. user_instruction が waiver と同居しても双方 schema 通過する
"""

from __future__ import annotations

import json
from pathlib import Path

from qgb.cli import EXIT_OK, main


def _init_minimal_project(tmp_path: Path) -> Path:
    project = tmp_path / "kbase-project"
    project.mkdir()
    exit_code = main(["init", "--path", str(project)])
    assert exit_code == EXIT_OK
    return project


def test_qgb_init_creates_empty_knowledge_jsonl(tmp_path: Path) -> None:
    """qgb init は空の knowledge.jsonl を生成する."""
    project = _init_minimal_project(tmp_path)
    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"
    assert kjsonl.is_file(), "qgb init must create knowledge.jsonl"
    # 初期状態は空 (各行 JSON object なので 0 行か空文字列)。
    assert kjsonl.read_text(encoding="utf-8").strip() == ""


def test_hand_edited_user_instruction_is_schema_valid(tmp_path: Path) -> None:
    """手編集で user_instruction を追記しても knowledge.jsonl は schema を通る."""
    project = _init_minimal_project(tmp_path)
    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"

    entry = {
        "id": "USER-INST-001",
        "kind": "user_instruction",
        "title": "Use TDD mode for new features",
        "content": "All new features must start in phase=red with a failing test.",
        "source": "user",
        "source_type": "user",
        "confidence": "explicit",
        "priority": "high",
        "created_at": "2026-06-01T00:00:00Z",
    }
    kjsonl.write_text(json.dumps(entry, ensure_ascii=False) + "\n", encoding="utf-8")

    # qgb validate が schema 通過。
    exit_code = main(["validate", "--path", str(project)])
    assert exit_code == EXIT_OK


def test_user_instruction_coexists_with_waiver(tmp_path: Path) -> None:
    """user_instruction と waiver が同じ knowledge.jsonl にあっても両方 schema 通過."""
    project = _init_minimal_project(tmp_path)
    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"

    user_entry = {
        "id": "USER-INST-002",
        "kind": "user_instruction",
        "title": "Prefer pure functions",
        "content": "Use pure functions where possible.",
        "source": "user",
        "source_type": "user",
        "confidence": "explicit",
        "priority": "medium",
        "created_at": "2026-06-01T00:00:00Z",
    }
    waiver_entry = {
        "id": "WAIVER-REQ-DEMO-001-S3",
        "kind": "waiver",
        "title": "Waiver for REQ-DEMO-001 / S3",
        "applies_to": "REQ-DEMO-001",
        "stage_id": "S3",
        "reason": "Internal CLI tool; no UI to verify",
        "decided_by": "user",
        "source_type": "user",
        "created_at": "2026-06-01T00:00:00Z",
    }
    lines = "\n".join(
        [
            json.dumps(user_entry, ensure_ascii=False),
            json.dumps(waiver_entry, ensure_ascii=False),
        ]
    ) + "\n"
    kjsonl.write_text(lines, encoding="utf-8")

    exit_code = main(["validate", "--path", str(project)])
    assert exit_code == EXIT_OK


def test_malformed_user_instruction_is_rejected(tmp_path: Path) -> None:
    """必須フィールドを欠いた user_instruction は schema 違反として弾かれる."""
    project = _init_minimal_project(tmp_path)
    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"
    bad_entry = {
        # id / title / source_type / created_at すべて欠落
        "kind": "user_instruction",
    }
    kjsonl.write_text(json.dumps(bad_entry, ensure_ascii=False) + "\n", encoding="utf-8")

    # qgb validate は NOT_READY (schema_violation) を返す。
    from qgb.cli import EXIT_NOT_READY
    exit_code = main(["validate", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY
