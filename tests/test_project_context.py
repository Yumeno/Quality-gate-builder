"""Phase 3 Step 3.0: project-context.{md,json} 二重ファイル設計のテスト.

カバー範囲:
- schema 検証 (project-context.schema.json の妥当性、必須/オプションフィールド)
- init 生成の雛形 (human_reviewed=false 初期値、validate 通過)
- loader.load_project_context (ファイル不在 = None、存在 = dict、BOM tolerant)
- design-stages propose-context との統合 (warning 経路、detect フィールド不在) は
  test_proposal.py の TestProposeContext で別途カバー
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from qgb.core.init import _materialise_project_context_json, run_init
from qgb.core.loader import LoaderError, load_project_context, project_context_path
from qgb.core.schema import validate as schema_validate
from qgb.core.validate import run_validate

# ---- schema -------------------------------------------------------------


class TestProjectContextSchema:
    def test_minimal_valid_instance(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": False,
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        assert schema_validate(instance, "project-context") == []

    def test_full_valid_instance(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": True,
            "project_kind": "python-cli",
            "purpose": "DBA がクエリプラン差分を比較するため",
            "scope": {
                "in_scope": ["Python source", "pytest tests"],
                "out_of_scope": ["web UI"],
            },
            "technologies": ["python", "pytest"],
            "artifact_kinds": ["source-code", "tests"],
            "platform": ["windows", "linux"],
            "non_adopted_methods": [
                {"method": "snapshot testing", "reason": "出力が日付依存"}
            ],
            "references": [
                {"kind": "design_doc", "path": "docs/architecture.md"}
            ],
            "source_metadata": {
                "generated_by": "agent-assisted",
                "agent_name": "claude-code",
                "agent_version": "4.7",
                "generated_at": "2026-06-21T00:00:00Z",
                "source_md_sha256": "a" * 64,
            },
        }
        assert schema_validate(instance, "project-context") == []

    def test_missing_required_schema_version(self) -> None:
        instance = {
            "human_reviewed": False,
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any("schema_version" in i.message for i in issues)

    def test_missing_required_human_reviewed(self) -> None:
        instance = {
            "schema_version": "1.0",
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any("human_reviewed" in i.message for i in issues)

    def test_missing_required_source_metadata(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": False,
        }
        issues = schema_validate(instance, "project-context")
        assert any("source_metadata" in i.message for i in issues)

    def test_unsupported_schema_version_rejected(self) -> None:
        """schema_version は '1.0' const なので他バージョンは reject."""
        instance = {
            "schema_version": "2.0",
            "human_reviewed": False,
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any(
            "schema_version" in i.path or "schema_version" in i.message
            for i in issues
        )

    def test_invalid_generated_by_enum_rejected(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": False,
            "source_metadata": {
                "generated_by": "robot",  # human / agent-assisted のみ
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any("generated_by" in i.path for i in issues)

    def test_invalid_source_md_sha256_pattern_rejected(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": False,
            "source_metadata": {
                "generated_by": "agent-assisted",
                "generated_at": "2026-06-21T00:00:00Z",
                "source_md_sha256": "not-a-sha",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any("source_md_sha256" in i.path for i in issues)

    def test_human_reviewed_must_be_boolean(self) -> None:
        instance = {
            "schema_version": "1.0",
            "human_reviewed": "true",  # string ではなく bool が期待される
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        issues = schema_validate(instance, "project-context")
        assert any("human_reviewed" in i.path for i in issues)


# ---- init ---------------------------------------------------------------


class TestInitProjectContext:
    def test_init_creates_project_context_json(self, tmp_path: Path) -> None:
        run_init(tmp_path, project_name="test-init")
        path = project_context_path(tmp_path)
        assert path.is_file(), "project-context.json should be created by init"

    def test_init_template_is_valid(self, tmp_path: Path) -> None:
        """init 生成の雛形は schema validate を通る."""
        run_init(tmp_path, project_name="test-init")
        path = project_context_path(tmp_path)
        instance = json.loads(path.read_text(encoding="utf-8"))
        assert schema_validate(instance, "project-context") == []

    def test_init_template_has_human_reviewed_false(self, tmp_path: Path) -> None:
        """雛形は human_reviewed: false 初期値 (人間が編集後に true に変える運用)."""
        run_init(tmp_path, project_name="test-init")
        path = project_context_path(tmp_path)
        instance = json.loads(path.read_text(encoding="utf-8"))
        assert instance["human_reviewed"] is False

    def test_init_template_generated_by_human(self, tmp_path: Path) -> None:
        """init 直後の generated_by は 'human' (人間が雛形を編集する前提)."""
        run_init(tmp_path, project_name="test-init")
        path = project_context_path(tmp_path)
        instance = json.loads(path.read_text(encoding="utf-8"))
        assert instance["source_metadata"]["generated_by"] == "human"

    def test_materialise_accepts_injected_now(self) -> None:
        """Phase 3 Step 3.0 B-5: _materialise_project_context_json の now 注入経路.

        docstring が "tests can pin the timestamp" と謳う以上、injection 経路が
        生成 JSON の generated_at フィールドに反映されることを直接テストする。
        段 1 correctness レビュー指摘 M-3 への対応。
        """
        fixed = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
        text = _materialise_project_context_json(now=fixed)
        instance = json.loads(text)
        assert instance["source_metadata"]["generated_at"] == "2026-01-02T03:04:05Z"

    def test_materialise_strips_microseconds(self) -> None:
        """注入された now が microsecond を持っていても RFC3339 shape に切り詰める."""
        fixed = datetime(2026, 1, 2, 3, 4, 5, 999_999, tzinfo=timezone.utc)
        text = _materialise_project_context_json(now=fixed)
        instance = json.loads(text)
        # microsecond は切り捨て、RFC3339 形式 (qgb の format checker が通る形)
        assert instance["source_metadata"]["generated_at"] == "2026-01-02T03:04:05Z"

    def test_materialise_default_now_is_valid_rfc3339(self) -> None:
        """now を渡さないとき default は datetime.now(timezone.utc) で、生成 JSON は schema 通過."""
        text = _materialise_project_context_json()
        instance = json.loads(text)
        # schema validate を通る (date-time format も含めて)
        assert schema_validate(instance, "project-context") == []

    def test_init_output_validates_via_qgb_validate(self, tmp_path: Path) -> None:
        """init 後の qgb validate が project-context.json を schema validate する."""
        run_init(tmp_path, project_name="test-init")
        report = run_validate(tmp_path)
        assert not report.has_problems(), report
        schema_names = sorted(name for _, name in report.files_checked)
        assert "project-context" in schema_names


# ---- loader -------------------------------------------------------------


class TestLoadProjectContext:
    def test_returns_none_when_file_absent(self, tmp_path: Path) -> None:
        # .quality-system/ 自体は存在しない: load は None を返す (LoaderError でない)。
        assert load_project_context(tmp_path) is None

    def test_returns_none_when_quality_system_exists_but_no_file(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / ".quality-system").mkdir()
        assert load_project_context(tmp_path) is None

    def test_returns_dict_when_present(self, tmp_path: Path) -> None:
        qs = tmp_path / ".quality-system"
        qs.mkdir()
        instance = {
            "schema_version": "1.0",
            "human_reviewed": True,
            "project_kind": "test",
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        (qs / "project-context.json").write_text(
            json.dumps(instance, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        loaded = load_project_context(tmp_path)
        assert loaded == instance

    def test_bom_tolerant(self, tmp_path: Path) -> None:
        """PowerShell 5.1 の Out-File は UTF-8 BOM 付きで書く (Step 2.5 規約)."""
        qs = tmp_path / ".quality-system"
        qs.mkdir()
        instance = {
            "schema_version": "1.0",
            "human_reviewed": True,
            "source_metadata": {
                "generated_by": "human",
                "generated_at": "2026-06-21T00:00:00Z",
            },
        }
        text = json.dumps(instance, ensure_ascii=False, indent=2)
        # BOM (utf-8-sig) で書き込み。
        (qs / "project-context.json").write_text(text, encoding="utf-8-sig")
        loaded = load_project_context(tmp_path)
        assert loaded == instance

    def test_invalid_json_raises_loader_error(self, tmp_path: Path) -> None:
        qs = tmp_path / ".quality-system"
        qs.mkdir()
        (qs / "project-context.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(LoaderError) as exc_info:
            load_project_context(tmp_path)
        assert exc_info.value.kind == "invalid_json"

    def test_non_object_raises_loader_error(self, tmp_path: Path) -> None:
        qs = tmp_path / ".quality-system"
        qs.mkdir()
        (qs / "project-context.json").write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(LoaderError) as exc_info:
            load_project_context(tmp_path)
        assert exc_info.value.kind == "wrong_type"
