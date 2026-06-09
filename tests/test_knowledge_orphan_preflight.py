"""Tests for knowledge orphan check via validate-policy (Phase 2 Step 2.3 軸 4).

spec 完了条件: 「orphan check が validate-policy 経由で blocker として出る
(add-waiver を打った後に元 REQ を削除したら検出されること)」を CLI レベルで
spec lock。run_preflight には統合しない (P9: REQ-A の orphan が qgb run
REQ-B を塞いではならない) ことも確認。
"""

from __future__ import annotations

import json

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main
from qgb.core.edit_commands import add_waiver
from qgb.core.preflight import run_preflight


class TestOrphanViaValidatePolicy:
    def test_add_waiver_then_delete_req_is_blocker(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        """spec 完了条件そのもの: add-waiver → REQ 削除 → validate-policy
        が knowledge_orphan blocker で exit 2。"""
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "external dependency")
        # Delete the REQ meta (the waiver knowledge entry remains).
        (project / ".quality-system" / "req" / "REQ-APP-001.meta.json").unlink()

        exit_code = main(
            ["validate-policy", "--path", str(project), "--json"]
        )
        assert exit_code == EXIT_NOT_READY
        payload = json.loads(capsys.readouterr().out)
        kinds = [i["kind"] for i in payload["blockers"]]
        assert "knowledge_orphan" in kinds

    def test_intact_project_has_no_orphan_findings(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "external dependency")
        exit_code = main(
            ["validate-policy", "--path", str(project), "--json"]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        kinds = [
            i["kind"]
            for i in payload.get("blockers", []) + payload.get("warnings", [])
        ]
        assert "knowledge_orphan" not in kinds

    def test_non_waiver_orphan_is_warning_only(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        """非 waiver kind の orphan は warning → exit 0 (歴史的知識は REQ
        削除後も価値を持ちうる)。"""
        project = copy_generic_minimal()
        kdir = project / ".quality-system" / "knowledge"
        kdir.mkdir(parents=True, exist_ok=True)
        entry = {
            "id": "K-HIST",
            "kind": "repository_fact",
            "title": "historical note",
            "source_type": "repository",
            "created_at": "2026-06-10T00:00:00Z",
            "applies_to": "REQ-GONE-999",
        }
        (kdir / "knowledge.jsonl").write_text(
            json.dumps(entry) + "\n", encoding="utf-8"
        )
        exit_code = main(
            ["validate-policy", "--path", str(project), "--json"]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        orphan_warnings = [
            i for i in payload.get("warnings", [])
            if i["kind"] == "knowledge_orphan"
        ]
        assert len(orphan_warnings) == 1
        # And it is NOT among the blockers.
        assert all(
            i["kind"] != "knowledge_orphan" for i in payload.get("blockers", [])
        )


class TestOrphanNotInRunPreflight:
    def test_run_preflight_ignores_orphans(self, copy_generic_minimal) -> None:
        """P9: validate-policy の design-quality 診断は run を塞がない。
        orphan waiver (REQ-GONE) があっても REQ-APP-001 の run preflight は
        knowledge_orphan を含まない。"""
        project = copy_generic_minimal()
        kdir = project / ".quality-system" / "knowledge"
        kdir.mkdir(parents=True, exist_ok=True)
        entry = {
            "id": "WAIVER-REQ-GONE-999-S1",
            "kind": "waiver",
            "title": "Waiver for REQ-GONE-999 / S1",
            "applies_to": "REQ-GONE-999",
            "stage_id": "S1",
            "reason": "orphaned",
            "decided_by": "user",
            "source_type": "user",
            "created_at": "2026-06-10T00:00:00Z",
        }
        (kdir / "knowledge.jsonl").write_text(
            json.dumps(entry) + "\n", encoding="utf-8"
        )
        report = run_preflight(project, "REQ-APP-001")
        kinds = [i.kind for i in report.issues]
        assert "knowledge_orphan" not in kinds
        assert report.ready_for_run()
