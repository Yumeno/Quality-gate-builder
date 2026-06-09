"""Tests for qgb.core.knowledge (Phase 2 Step 2.3 store layer).

append-only + partial-tail tolerant な追記、waiver entry builder の
唯一性 (evidence との id 整合)、orphan check の severity 設計を spec lock。
"""

from __future__ import annotations

import json
from pathlib import Path

from qgb.core.evidence import waiver_knowledge_id as evidence_wid
from qgb.core.knowledge import (
    append_knowledge_entries,
    build_waiver_knowledge_entry,
    check_knowledge_orphans,
    knowledge_jsonl_path,
    read_existing_ids,
    waiver_knowledge_id,
)


def _entry(eid: str, **over) -> dict:
    base = {
        "id": eid,
        "kind": "user_instruction",
        "title": f"entry {eid}",
        "source_type": "user",
        "created_at": "2026-06-10T00:00:00Z",
    }
    base.update(over)
    return base


# ---- append ----------------------------------------------------------------


class TestAppend:
    def test_append_to_fresh_project(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        report = append_knowledge_entries(project, [_entry("K-1"), _entry("K-2")])
        assert report.appended_ids == ["K-1", "K-2"]
        assert report.skipped_ids == []
        kjsonl = knowledge_jsonl_path(project)
        lines = [
            json.loads(line)
            for line in kjsonl.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert [e["id"] for e in lines] == ["K-1", "K-2"]

    def test_existing_id_is_skipped(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        append_knowledge_entries(project, [_entry("K-1")])
        report = append_knowledge_entries(
            project, [_entry("K-1", title="changed"), _entry("K-2")]
        )
        assert report.appended_ids == ["K-2"]
        assert report.skipped_ids == ["K-1"]
        # The original K-1 content is preserved (no rewrite).
        kjsonl = knowledge_jsonl_path(project)
        first = json.loads(
            kjsonl.read_text(encoding="utf-8").splitlines()[0]
        )
        assert first["title"] == "entry K-1"

    def test_in_file_duplicate_appends_first_skips_second(
        self, copy_generic_minimal
    ) -> None:
        project = copy_generic_minimal()
        report = append_knowledge_entries(
            project, [_entry("K-1"), _entry("K-1", title="dup")]
        )
        assert report.appended_ids == ["K-1"]
        assert report.skipped_ids == ["K-1"]

    def test_partial_tail_gets_newline_first(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        kjsonl = knowledge_jsonl_path(project)
        kjsonl.parent.mkdir(parents=True, exist_ok=True)
        # Simulate a crashed writer: valid line + partial tail, no newline.
        kjsonl.write_text(
            json.dumps(_entry("K-OLD")) + "\n" + '{"id": "K-PART',
            encoding="utf-8",
        )
        report = append_knowledge_entries(project, [_entry("K-NEW")])
        assert report.appended_ids == ["K-NEW"]
        lines = kjsonl.read_text(encoding="utf-8").splitlines()
        # Partial tail stays on its own line; the new entry is parseable.
        assert json.loads(lines[-1])["id"] == "K-NEW"

    def test_empty_entries_is_noop(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        report = append_knowledge_entries(project, [])
        assert report.appended_ids == []
        assert not knowledge_jsonl_path(project).exists()


# ---- waiver builder ---------------------------------------------------------


class TestWaiverBuilder:
    def test_id_format_matches_evidence_helper(self) -> None:
        """Step 2.3 リファクタ保護: evidence.waiver_knowledge_id は knowledge
        へ委譲。両者の出力一致を spec lock (basis の KNOWLEDGE- prefix 規約が
        依存する)。"""
        assert waiver_knowledge_id("REQ-APP-001", "S2") == "WAIVER-REQ-APP-001-S2"
        assert evidence_wid("REQ-APP-001", "S2") == waiver_knowledge_id(
            "REQ-APP-001", "S2"
        )

    def test_entry_shape(self) -> None:
        entry = build_waiver_knowledge_entry(
            "REQ-APP-001",
            "S2",
            "external dependency",
            decided_by="alice",
            created_at="2026-06-10T00:00:00Z",
        )
        assert entry == {
            "id": "WAIVER-REQ-APP-001-S2",
            "kind": "waiver",
            "title": "Waiver for REQ-APP-001 / S2",
            "applies_to": "REQ-APP-001",
            "stage_id": "S2",
            "reason": "external dependency",
            "decided_by": "alice",
            "source_type": "user",
            "created_at": "2026-06-10T00:00:00Z",
        }


# ---- read_existing_ids -------------------------------------------------------


class TestReadExistingIds:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_existing_ids(tmp_path / "nope.jsonl") == set()

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        f = tmp_path / "k.jsonl"
        f.write_text(
            json.dumps(_entry("K-1")) + "\nnot json\n" + json.dumps(_entry("K-2")) + "\n",
            encoding="utf-8",
        )
        assert read_existing_ids(f) == {"K-1", "K-2"}


# ---- orphan check ------------------------------------------------------------


def _write_knowledge(project: Path, entries: list[dict]) -> None:
    kjsonl = knowledge_jsonl_path(project)
    kjsonl.parent.mkdir(parents=True, exist_ok=True)
    kjsonl.write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries),
        encoding="utf-8",
    )


def _waiver_entry(req_id: str, stage_id: str) -> dict:
    return build_waiver_knowledge_entry(
        req_id, stage_id, "test reason", decided_by="user",
        created_at="2026-06-10T00:00:00Z",
    )


class TestOrphanCheck:
    def test_no_knowledge_file_no_findings(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        assert check_knowledge_orphans(project) == []

    def test_intact_waiver_no_findings(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        _write_knowledge(project, [_waiver_entry("REQ-APP-001", "S2")])
        assert check_knowledge_orphans(project) == []

    def test_waiver_req_deleted_is_blocker(self, copy_generic_minimal) -> None:
        """spec 完了条件: add-waiver 後に REQ を削除したら検出される。"""
        project = copy_generic_minimal()
        _write_knowledge(project, [_waiver_entry("REQ-APP-001", "S2")])
        (project / ".quality-system" / "req" / "REQ-APP-001.meta.json").unlink()
        findings = check_knowledge_orphans(project)
        assert len(findings) == 1
        assert findings[0].severity == "blocker"
        assert findings[0].applies_to == "REQ-APP-001"

    def test_waiver_stage_removed_is_blocker(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        _write_knowledge(project, [_waiver_entry("REQ-APP-001", "S9")])
        findings = check_knowledge_orphans(project)
        assert len(findings) == 1
        assert findings[0].severity == "blocker"
        assert findings[0].stage_id == "S9"

    def test_non_waiver_req_missing_is_warning(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        _write_knowledge(
            project,
            [_entry("K-HIST", applies_to="REQ-GONE-999")],
        )
        findings = check_knowledge_orphans(project)
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_free_form_applies_to_ignored(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        _write_knowledge(
            project,
            [_entry("K-GLOBAL", applies_to="project-wide")],
        )
        assert check_knowledge_orphans(project) == []

    def test_applies_to_array_checks_each(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        _write_knowledge(
            project,
            [_entry("K-MULTI", applies_to=["REQ-APP-001", "REQ-GONE-999"])],
        )
        findings = check_knowledge_orphans(project)
        assert len(findings) == 1
        assert findings[0].applies_to == "REQ-GONE-999"

    def test_malformed_lines_skipped(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        kjsonl = knowledge_jsonl_path(project)
        kjsonl.parent.mkdir(parents=True, exist_ok=True)
        kjsonl.write_text("not json at all\n", encoding="utf-8")
        assert check_knowledge_orphans(project) == []
