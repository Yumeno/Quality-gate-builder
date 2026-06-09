"""Tests for qgb add-waiver / add-knowledge (Phase 2 Step 2.3).

Codex 計画レビューで確定した 3 仕様を spec lock:

1. --force: 異 reason 上書きは req-meta のみ、knowledge は歴史保持 + 警告
2. atomicity: file 単位 atomic + idempotent recovery (meta / knowledge を
   独立判定して欠けている方だけ埋める)
3. add-knowledge: 補完なし / object & array 両対応 / 既存 id skip /
   --force なし / all-or-nothing
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main
from qgb.core.edit_commands import (
    EditError,
    add_knowledge,
    add_waiver,
)
from qgb.core.knowledge import knowledge_jsonl_path


def _meta(project: Path) -> dict:
    return json.loads(
        (project / ".quality-system" / "req" / "REQ-APP-001.meta.json").read_text(
            encoding="utf-8"
        )
    )


def _stage(project: Path, stage_id: str) -> dict:
    for entry in _meta(project)["stages"]:
        if entry["stage_id"] == stage_id:
            return entry
    raise AssertionError(f"stage {stage_id} not found")


def _knowledge_lines(project: Path) -> list[dict]:
    kjsonl = knowledge_jsonl_path(project)
    if not kjsonl.is_file():
        return []
    return [
        json.loads(line)
        for line in kjsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---- add_waiver: core ------------------------------------------------------


class TestAddWaiver:
    def test_fresh_waive_updates_meta_and_knowledge(
        self, copy_generic_minimal
    ) -> None:
        project = copy_generic_minimal()
        result = add_waiver(
            project, "REQ-APP-001", "S2", "external dependency"
        )
        assert result.meta_changed is True
        assert result.knowledge_appended is True
        assert result.no_op is False
        stage = _stage(project, "S2")
        assert stage["waived"] is True
        assert stage["waiver_reason"] == "external dependency"
        entries = _knowledge_lines(project)
        assert len(entries) == 1
        assert entries[0]["id"] == "WAIVER-REQ-APP-001-S2"
        assert entries[0]["reason"] == "external dependency"

    def test_same_reason_is_noop(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "reason A")
        result = add_waiver(project, "REQ-APP-001", "S2", "reason A")
        assert result.no_op is True
        assert len(_knowledge_lines(project)) == 1

    def test_different_reason_without_force_raises(
        self, copy_generic_minimal
    ) -> None:
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "reason A")
        with pytest.raises(EditError) as exc_info:
            add_waiver(project, "REQ-APP-001", "S2", "reason B")
        assert exc_info.value.reason == "waiver_conflict"
        # Meta unchanged.
        assert _stage(project, "S2")["waiver_reason"] == "reason A"

    def test_force_updates_meta_keeps_knowledge(
        self, copy_generic_minimal
    ) -> None:
        """Codex 確定仕様 1: force は req-meta のみ更新、knowledge.jsonl の
        既存 entry は audit history として保持、警告を返す。"""
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "reason A")
        result = add_waiver(
            project, "REQ-APP-001", "S2", "reason B", force=True
        )
        assert result.forced is True
        assert result.meta_changed is True
        assert result.warnings  # divergence warning present
        assert _stage(project, "S2")["waiver_reason"] == "reason B"
        # Knowledge entry keeps the ORIGINAL reason (append-only history).
        entries = _knowledge_lines(project)
        assert len(entries) == 1
        assert entries[0]["reason"] == "reason A"

    def test_stage_not_found(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        with pytest.raises(EditError) as exc_info:
            add_waiver(project, "REQ-APP-001", "S99", "reason")
        assert exc_info.value.reason == "stage_not_found"

    def test_req_not_found(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        with pytest.raises(EditError) as exc_info:
            add_waiver(project, "REQ-NONE-999", "S1", "reason")
        assert exc_info.value.reason == "req_not_found"

    def test_empty_reason_rejected(self, copy_generic_minimal) -> None:
        project = copy_generic_minimal()
        with pytest.raises(EditError) as exc_info:
            add_waiver(project, "REQ-APP-001", "S2", "   ")
        assert exc_info.value.reason == "invalid_reason"

    def test_dry_run_writes_nothing(
        self, copy_generic_minimal, snapshot_dir
    ) -> None:
        project = copy_generic_minimal()
        before = snapshot_dir(project)
        result = add_waiver(
            project, "REQ-APP-001", "S2", "reason", dry_run=True
        )
        assert result.would_write is True
        assert snapshot_dir(project) == before

    def test_recovery_appends_missing_knowledge(
        self, copy_generic_minimal
    ) -> None:
        """Codex 確定仕様 2 (idempotent recovery): meta は waive 済だが
        knowledge entry が無い状態 (= 過去の append 失敗や手編集) から
        再実行すると knowledge だけが埋まる。"""
        project = copy_generic_minimal()
        # Hand-waive the meta without knowledge (simulates partial failure).
        meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["stages"][1]["waived"] = True
        meta["stages"][1]["waiver_reason"] = "manual reason"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        assert _knowledge_lines(project) == []

        result = add_waiver(project, "REQ-APP-001", "S2", "manual reason")
        assert result.meta_changed is False
        assert result.knowledge_appended is True
        assert len(_knowledge_lines(project)) == 1

    def test_run_after_add_waiver_does_not_duplicate(
        self, copy_generic_minimal
    ) -> None:
        """add-waiver の即時 append と run 時の自動記録が同じ id を共有する
        ので、run しても knowledge entry は増えない (builder 共通化の検証)。"""
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "external dependency")
        exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
        assert exit_code == EXIT_OK
        waiver_entries = [
            e for e in _knowledge_lines(project) if e.get("kind") == "waiver"
        ]
        assert len(waiver_entries) == 1

    def test_force_dry_run_reports_would_be_changes(
        self, copy_generic_minimal, snapshot_dir
    ) -> None:
        """Step 2.3 補修 A1+A3: force + dry-run は would-be 値 (meta_changed
        = True) と乖離警告を返しつつ、disk には何も書かない。"""
        project = copy_generic_minimal()
        add_waiver(project, "REQ-APP-001", "S2", "reason A")
        before = snapshot_dir(project)
        result = add_waiver(
            project, "REQ-APP-001", "S2", "reason B", force=True, dry_run=True
        )
        assert result.forced is True
        assert result.meta_changed is True  # would-be value (A1)
        assert result.knowledge_appended is False  # entry already exists
        assert result.warnings
        assert snapshot_dir(project) == before

    def test_recovery_dry_run_reports_would_be_append(
        self, copy_generic_minimal, snapshot_dir
    ) -> None:
        """Step 2.3 補修 A1+A3: recovery (meta 済 / knowledge 欠落) +
        dry-run は knowledge_appended=True (would-be) を返し、書かない。"""
        project = copy_generic_minimal()
        meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["stages"][1]["waived"] = True
        meta["stages"][1]["waiver_reason"] = "manual reason"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        before = snapshot_dir(project)
        result = add_waiver(
            project, "REQ-APP-001", "S2", "manual reason", dry_run=True
        )
        assert result.meta_changed is False
        assert result.knowledge_appended is True  # would-be value (A1)
        assert snapshot_dir(project) == before

    def test_force_with_missing_knowledge_creates_entry_with_new_reason(
        self, copy_generic_minimal
    ) -> None:
        """Step 2.3 補修 B1 (Codex 横断レビュー指摘 1): meta は waived/旧
        reason だが knowledge entry が欠けている状態で --force + 新 reason
        を打つと、新規 entry は**新 reason** で作られ、警告は「既存 entry
        が歴史を保持」とは言わない (entry は存在しないから)。"""
        project = copy_generic_minimal()
        # meta だけ手で waive (knowledge なし)。
        meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["stages"][1]["waived"] = True
        meta["stages"][1]["waiver_reason"] = "old reason"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        result = add_waiver(
            project, "REQ-APP-001", "S2", "new reason", force=True
        )
        assert result.forced is True
        assert result.knowledge_appended is True
        entries = _knowledge_lines(project)
        assert len(entries) == 1
        # New entry records the NEW reason (the req-meta truth).
        assert entries[0]["reason"] == "new reason"
        # The warning tells the truth: no existing entry was preserved.
        assert any("No existing knowledge entry" in w for w in result.warnings)
        assert not any("keeps the original" in w for w in result.warnings)

    def test_generated_entry_schema_validated(
        self, copy_generic_minimal
    ) -> None:
        """Step 2.3 補修 B2 (Codex 横断レビュー指摘 2): add-waiver 自身が
        不正 knowledge entry を書けない。decided_by="" は schema の
        minLength 1 違反として reject される。"""
        project = copy_generic_minimal()
        with pytest.raises(EditError) as exc_info:
            add_waiver(
                project, "REQ-APP-001", "S2", "reason", decided_by=""
            )
        assert exc_info.value.reason == "knowledge_schema_violation"
        # Nothing was appended.
        assert _knowledge_lines(project) == []

    def test_knowledge_append_oserror_becomes_edit_error(
        self, copy_generic_minimal, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Step 2.3 補修 A2: meta patch 成功後の knowledge append IO 失敗は
        raw OSError でなく EditError(io_error) として届き、message が
        idempotent recovery (再実行で収束) を案内する。"""
        project = copy_generic_minimal()

        def _boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(
            "qgb.core.edit_commands.append_knowledge_entries", _boom
        )
        with pytest.raises(EditError) as exc_info:
            add_waiver(project, "REQ-APP-001", "S2", "reason")
        assert exc_info.value.reason == "io_error"
        assert "Re-run" in exc_info.value.message
        # The meta IS updated (per-file atomic; recovery is by re-running).
        assert _stage(project, "S2")["waived"] is True


# ---- add_knowledge: core ----------------------------------------------------


def _kentry(eid: str, **over) -> dict:
    base = {
        "id": eid,
        "kind": "user_instruction",
        "title": f"entry {eid}",
        "source_type": "user",
        "created_at": "2026-06-10T00:00:00Z",
    }
    base.update(over)
    return base


class TestAddKnowledge:
    def test_single_object(self, copy_generic_minimal, tmp_path: Path) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-1")), encoding="utf-8")
        result = add_knowledge(project, f)
        assert result.appended_ids == ["K-1"]
        assert result.written is True

    def test_array_of_entries(self, copy_generic_minimal, tmp_path: Path) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(
            json.dumps([_kentry("K-1"), _kentry("K-2")]), encoding="utf-8"
        )
        result = add_knowledge(project, f)
        assert result.appended_ids == ["K-1", "K-2"]

    def test_schema_violation_rejects_all(
        self, copy_generic_minimal, tmp_path: Path
    ) -> None:
        """all-or-nothing: 1 件でも schema 違反なら何も append しない。"""
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        bad = _kentry("K-BAD")
        del bad["created_at"]
        f.write_text(json.dumps([_kentry("K-OK"), bad]), encoding="utf-8")
        with pytest.raises(EditError) as exc_info:
            add_knowledge(project, f)
        assert exc_info.value.reason == "knowledge_schema_violation"
        # Nothing was appended (the file was never even created).
        assert not knowledge_jsonl_path(project).exists()

    def test_duplicate_id_skipped(
        self, copy_generic_minimal, tmp_path: Path
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-1")), encoding="utf-8")
        add_knowledge(project, f)
        result = add_knowledge(project, f)
        assert result.appended_ids == []
        assert result.skipped_ids == ["K-1"]

    def test_external_requires_human_review_enforced(
        self, copy_generic_minimal, tmp_path: Path
    ) -> None:
        """Step 9 (受け入れ条件 18) の P8 機械化が add-knowledge 経由でも
        効く: source_type=external で requires_human_review が無い entry は
        schema reject。"""
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(
            json.dumps(_kentry("K-EXT", source_type="external")),
            encoding="utf-8",
        )
        with pytest.raises(EditError) as exc_info:
            add_knowledge(project, f)
        assert exc_info.value.reason == "knowledge_schema_violation"

    def test_not_json(self, copy_generic_minimal, tmp_path: Path) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text("not json", encoding="utf-8")
        with pytest.raises(EditError) as exc_info:
            add_knowledge(project, f)
        assert exc_info.value.reason == "knowledge_not_json"

    def test_scalar_input_rejected(
        self, copy_generic_minimal, tmp_path: Path
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text("42", encoding="utf-8")
        with pytest.raises(EditError) as exc_info:
            add_knowledge(project, f)
        assert exc_info.value.reason == "invalid_knowledge_document"

    def test_dry_run_writes_nothing(
        self, copy_generic_minimal, tmp_path: Path, snapshot_dir
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-1")), encoding="utf-8")
        before = snapshot_dir(project)
        result = add_knowledge(project, f, dry_run=True)
        assert result.appended_ids == ["K-1"]
        assert result.written is False
        assert snapshot_dir(project) == before

    def test_dry_run_reports_existing_id_as_skip(
        self, copy_generic_minimal, tmp_path: Path
    ) -> None:
        """Step 2.3 補修 A3: dry-run でも既存 id は skip 側に分類される
        (実 run と同じ partition ロジック)。"""
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-1")), encoding="utf-8")
        add_knowledge(project, f)
        f2 = tmp_path / "k2.json"
        f2.write_text(
            json.dumps([_kentry("K-1"), _kentry("K-2")]), encoding="utf-8"
        )
        result = add_knowledge(project, f2, dry_run=True)
        assert result.appended_ids == ["K-2"]
        assert result.skipped_ids == ["K-1"]
        assert result.written is False


# ---- CLI 経路 ---------------------------------------------------------------


class TestCli:
    def test_add_waiver_cli_ok_json(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        exit_code = main(
            [
                "add-waiver",
                "REQ-APP-001",
                "S2",
                "--reason",
                "cli test",
                "--path",
                str(project),
                "--json",
            ]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["meta_changed"] is True
        assert payload["knowledge_appended"] is True

    def test_add_waiver_cli_conflict_exit_not_ready(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        main(
            [
                "add-waiver", "REQ-APP-001", "S2",
                "--reason", "A", "--path", str(project),
            ]
        )
        capsys.readouterr()
        exit_code = main(
            [
                "add-waiver", "REQ-APP-001", "S2",
                "--reason", "B", "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_NOT_READY
        payload = json.loads(capsys.readouterr().out)
        assert payload["reason"] == "waiver_conflict"

    def test_add_waiver_cli_force_warns(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        main(
            [
                "add-waiver", "REQ-APP-001", "S2",
                "--reason", "A", "--path", str(project),
            ]
        )
        capsys.readouterr()
        exit_code = main(
            [
                "add-waiver", "REQ-APP-001", "S2",
                "--reason", "B", "--force", "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["forced"] is True
        assert payload["warnings"]

    def test_add_knowledge_cli_json(
        self, copy_generic_minimal, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-CLI")), encoding="utf-8")
        exit_code = main(
            [
                "add-knowledge", str(f), "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["appended"] == ["K-CLI"]

    def test_add_knowledge_cli_schema_violation(
        self, copy_generic_minimal, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        bad = _kentry("K-BAD")
        del bad["created_at"]
        f.write_text(json.dumps(bad), encoding="utf-8")
        exit_code = main(
            [
                "add-knowledge", str(f), "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_NOT_READY
        payload = json.loads(capsys.readouterr().out)
        assert payload["reason"] == "knowledge_schema_violation"

    def test_add_waiver_cli_dry_run(
        self, copy_generic_minimal, capsys: pytest.CaptureFixture, snapshot_dir
    ) -> None:
        """Step 2.3 補修 A3: CLI --dry-run は exit 0 + would-be 値の JSON を
        返し、disk には何も書かない。"""
        project = copy_generic_minimal()
        before = snapshot_dir(project)
        exit_code = main(
            [
                "add-waiver", "REQ-APP-001", "S2",
                "--reason", "dry", "--dry-run",
                "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        assert payload["would_write"] is True
        assert payload["meta_changed"] is True  # would-be value (A1)
        assert snapshot_dir(project) == before

    def test_add_knowledge_cli_dry_run(
        self, copy_generic_minimal, tmp_path: Path,
        capsys: pytest.CaptureFixture, snapshot_dir,
    ) -> None:
        project = copy_generic_minimal()
        f = tmp_path / "k.json"
        f.write_text(json.dumps(_kentry("K-DRY")), encoding="utf-8")
        before = snapshot_dir(project)
        exit_code = main(
            [
                "add-knowledge", str(f), "--dry-run",
                "--path", str(project), "--json",
            ]
        )
        assert exit_code == EXIT_OK
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        assert payload["appended"] == ["K-DRY"]
        assert payload["written"] is False
        assert snapshot_dir(project) == before
