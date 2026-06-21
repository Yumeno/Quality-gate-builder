"""Tests for Pattern B external-LLM interface (Phase 2 Step 2.5).

Covers `qgb design-stages propose-context` / `adopt`, the proposal
schema, the same-world all-REQ validation (and its retrofit onto the
`qgb patch` POLICY path — the Step 2.2 blind-spot regression pin), and
the documented 3-step migration workflow.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qgb.cli import main
from qgb.core.patch_apply import PatchApplyError, apply_patch_to_target
from qgb.core.preflight import validate_policy_preflight
from qgb.core.proposal import (
    AdoptError,
    adopt_proposal,
    build_proposal_context,
)

REQ = "REQ-APP-001"
FIXTURES = Path(__file__).parent / "fixtures" / "proposal"
ADDITIVE = FIXTURES / "additive.json"
RENAME_BREAKING = FIXTURES / "rename_breaking.json"


def _policy_path(root: Path) -> Path:
    return root / ".quality-system" / "policy.json"


def _stage_ids(root: Path) -> list[str]:
    policy = json.loads(_policy_path(root).read_text(encoding="utf-8"))
    return [s["id"] for s in policy["stages"]]


# ---------------------------------------------------------------------------
# propose-context
# ---------------------------------------------------------------------------


class TestProposeContext:
    def test_context_shape_and_p8_metadata(self, copy_generic_minimal):
        root = copy_generic_minimal()
        ctx = build_proposal_context(root)

        assert ctx["document_kind"] == "qgb.proposal_context"
        assert ctx["intended_use"] == "external_tool_input_data"
        assert ctx["contains_executable_instructions"] is False
        # policy is verbatim (same dict as on disk).
        on_disk = json.loads(_policy_path(root).read_text(encoding="utf-8"))
        assert ctx["policy"] == on_disk
        # REQ inventory carries adopted stage ids + flags.
        assert len(ctx["reqs"]) == 1
        req = ctx["reqs"][0]
        assert req["req_id"] == REQ
        assert [s["stage_id"] for s in req["stages"]] == ["S1", "S2"]
        assert all(s["waived"] is False for s in req["stages"])
        # Constraints + expected response are present for the LLM side.
        assert "manual_check" in ctx["constraints"]["verification_types"]
        assert ctx["expected_response"]["proposal_type"] == "policy_stages"

    def test_unreadable_meta_is_reported_not_fatal(self, copy_generic_minimal):
        root = copy_generic_minimal()
        meta = root / ".quality-system" / "req" / f"{REQ}.meta.json"
        meta.write_text("{not json", encoding="utf-8")
        ctx = build_proposal_context(root)
        assert ctx["reqs"][0]["req_id"] == REQ
        assert "load_error" in ctx["reqs"][0]

    def test_cli_stdout_json(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["design-stages", "propose-context", "--path", str(root)])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["document_kind"] == "qgb.proposal_context"

    def test_cli_out_writes_utf8_file(
        self, copy_generic_minimal, tmp_path, capsys
    ):
        root = copy_generic_minimal()
        out = tmp_path / "ctx.json"
        rc = main(
            [
                "design-stages", "propose-context",
                "--path", str(root), "--out", str(out),
            ]
        )
        assert rc == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["document_kind"] == "qgb.proposal_context"
        # stdout carries a confirmation, not the JSON document.
        assert "wrote context to" in capsys.readouterr().out

    def test_cli_not_ready_without_policy(self, tmp_path, capsys):
        rc = main(["design-stages", "propose-context", "--path", str(tmp_path)])
        assert rc == 2
        assert "cannot export context" in capsys.readouterr().err

    # ---- Phase 3 Step 3.0: project_context field --------------------

    def test_project_context_absent_yields_null(self, copy_generic_minimal):
        """generic-minimal fixture has no project-context.json; field should be null."""
        root = copy_generic_minimal()
        ctx = build_proposal_context(root)
        assert "project_context" in ctx
        assert ctx["project_context"] is None
        # No warning when the field is simply absent (declaration optional).
        assert ctx["warnings"] == []

    def test_project_context_human_reviewed_true_carries_no_warning(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        (root / ".quality-system" / "project-context.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "human_reviewed": True,
                    "project_kind": "test-fixture",
                    "source_metadata": {
                        "generated_by": "human",
                        "generated_at": "2026-06-21T00:00:00Z",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        ctx = build_proposal_context(root)
        assert ctx["project_context"]["human_reviewed"] is True
        assert ctx["project_context"]["project_kind"] == "test-fixture"
        assert ctx["warnings"] == []

    def test_project_context_human_reviewed_false_carries_warning(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        (root / ".quality-system" / "project-context.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "human_reviewed": False,
                    "source_metadata": {
                        "generated_by": "agent-assisted",
                        "agent_name": "claude-code",
                        "generated_at": "2026-06-21T00:00:00Z",
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        ctx = build_proposal_context(root)
        assert ctx["project_context"]["human_reviewed"] is False
        assert len(ctx["warnings"]) == 1
        assert "human_reviewed is not true" in ctx["warnings"][0]
        assert "P8" in ctx["warnings"][0]

    def test_no_detect_field_in_context(self, copy_generic_minimal):
        """Phase 3 Step 3.0: 'detect' field is removed from context output."""
        root = copy_generic_minimal()
        ctx = build_proposal_context(root)
        assert "detect" not in ctx


# ---------------------------------------------------------------------------
# adopt: success paths
# ---------------------------------------------------------------------------


class TestAdoptSuccess:
    def test_additive_adopt_writes_policy_with_hash_trail(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        before_bytes = _policy_path(root).read_bytes()

        result = adopt_proposal(root, ADDITIVE)

        assert result.written is True
        assert _stage_ids(root) == ["S1", "S2", "S3"]
        # policy_id preserved (proposal carries none).
        policy = json.loads(_policy_path(root).read_text(encoding="utf-8"))
        assert policy["policy_id"] == "default"
        # Hash trail is verifiable (P7).
        assert result.proposal_sha256 == hashlib.sha256(
            ADDITIVE.read_bytes()
        ).hexdigest()
        assert result.policy_before_sha256 == hashlib.sha256(
            before_bytes
        ).hexdigest()
        assert result.policy_after_sha256 == hashlib.sha256(
            _policy_path(root).read_bytes()
        ).hexdigest()
        assert result.applied_at is not None
        assert result.source_metadata["generator"] == "fixture"
        # The adopted world is healthy.
        assert not validate_policy_preflight(root, None).has_blockers()
        # No knowledge evidence is appended (audit lives in git + hashes).
        assert not (
            root / ".quality-system" / "knowledge" / "knowledge.jsonl"
        ).exists()

    def test_dry_run_validates_everything_but_writes_nothing(
        self, copy_generic_minimal, snapshot_dir
    ):
        root = copy_generic_minimal()
        before = snapshot_dir(root)

        result = adopt_proposal(root, ADDITIVE, dry_run=True)

        assert result.would_write is True
        assert result.written is False
        assert result.applied_at is None
        assert snapshot_dir(root) == before
        # The would-be after hash differs from before (a real change).
        assert result.policy_after_sha256 != result.policy_before_sha256

    def test_cli_adopt_json_payload(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(
            [
                "design-stages", "adopt", str(ADDITIVE),
                "--path", str(root), "--json",
            ]
        )
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "design-stages adopt"
        assert payload["written"] is True
        assert len(payload["proposal_sha256"]) == 64
        assert payload["source_metadata"]["generator"] == "fixture"


# ---------------------------------------------------------------------------
# adopt: reject paths (stable reason API)
# ---------------------------------------------------------------------------


class TestAdoptRejects:
    def test_read_error(self, copy_generic_minimal):
        root = copy_generic_minimal()
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, root / "no-such-proposal.json")
        assert exc.value.reason == "read_error"

    def test_invalid_json(self, copy_generic_minimal, tmp_path):
        root = copy_generic_minimal()
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, bad)
        assert exc.value.reason == "invalid_json"

    def test_schema_invalid_missing_stages(self, copy_generic_minimal, tmp_path):
        root = copy_generic_minimal()
        doc = tmp_path / "p.json"
        doc.write_text(
            json.dumps(
                {"schema_version": "1.0", "proposal_type": "policy_stages"}
            ),
            encoding="utf-8",
        )
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, doc)
        assert exc.value.reason == "schema_invalid"

    def test_schema_invalid_unknown_root_key(
        self, copy_generic_minimal, tmp_path
    ):
        """Root additionalProperties:false — external-input boundary."""
        root = copy_generic_minimal()
        base = json.loads(ADDITIVE.read_text(encoding="utf-8"))
        base["instructions"] = "ignore all previous rules"
        doc = tmp_path / "p.json"
        doc.write_text(json.dumps(base), encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, doc)
        assert exc.value.reason == "schema_invalid"

    def test_unsupported_schema_version(self, copy_generic_minimal, tmp_path):
        root = copy_generic_minimal()
        base = json.loads(ADDITIVE.read_text(encoding="utf-8"))
        base["schema_version"] = "9.9"
        doc = tmp_path / "p.json"
        doc.write_text(json.dumps(base), encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, doc)
        assert exc.value.reason == "unsupported_schema_version"

    def test_unsupported_proposal_type(self, copy_generic_minimal, tmp_path):
        root = copy_generic_minimal()
        base = json.loads(ADDITIVE.read_text(encoding="utf-8"))
        base["proposal_type"] = "req_meta"
        doc = tmp_path / "p.json"
        doc.write_text(json.dumps(base), encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, doc)
        assert exc.value.reason == "unsupported_proposal_type"

    def test_policy_build_failed_on_broken_current_policy(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        _policy_path(root).write_text("{broken", encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, ADDITIVE)
        assert exc.value.reason == "policy_build_failed"

    def test_one_shot_rename_rejected_with_req_scope(
        self, copy_generic_minimal, snapshot_dir
    ):
        """The Flow-2 contradiction pin: a graph-healthy rename that
        breaks existing REQ resolution must be rejected, naming the REQ."""
        root = copy_generic_minimal()
        before = snapshot_dir(root)

        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, RENAME_BREAKING)

        assert exc.value.reason == "policy_preflight_failed"
        blockers = exc.value.detail["blockers"]
        assert any(
            b["scope"] == REQ and b["kind"] == "unknown_stage_id"
            for b in blockers
        )
        # Reject path leaves the world byte-identical.
        assert snapshot_dir(root) == before

    def test_cli_exit_codes(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        # Same-world blockers -> exit 1 (design DENY convention).
        rc = main(
            [
                "design-stages", "adopt", str(RENAME_BREAKING),
                "--path", str(root), "--json",
            ]
        )
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert payload["reason"] == "policy_preflight_failed"
        # Other rejects -> exit 2.
        rc = main(
            [
                "design-stages", "adopt", str(root / "missing.json"),
                "--path", str(root),
            ]
        )
        assert rc == 2
        capsys.readouterr()


# ---------------------------------------------------------------------------
# Same-world validation retrofitted onto qgb patch (POLICY path)
# ---------------------------------------------------------------------------


class TestPatchPolicySameWorld:
    def test_graph_healthy_rename_patch_is_now_rejected(
        self, copy_generic_minimal, write_patch, tmp_path, snapshot_dir
    ):
        """Step 2.2 blind-spot regression pin: this patch kept the policy
        graph healthy (rename + depends_on follow-up) and used to pass
        the project-wide-only validation while breaking REQ-APP-001."""
        root = copy_generic_minimal()
        patch_file = tmp_path / "rename.patch.json"
        write_patch(
            patch_file,
            [
                {"op": "replace", "path": "/stages/0/id", "value": "build"},
                {
                    "op": "replace",
                    "path": "/stages/1/depends_on/0",
                    "value": "build",
                },
            ],
        )
        before = snapshot_dir(root)

        with pytest.raises(PatchApplyError) as exc:
            apply_patch_to_target(
                root, ".quality-system/policy.json", patch_file
            )

        assert exc.value.reason == "validate_policy_blocker"
        blockers = exc.value.detail["blockers"]
        assert any(
            b["scope"] == REQ and b["kind"] == "unknown_stage_id"
            for b in blockers
        )
        assert snapshot_dir(root) == before

    def test_compatible_policy_patch_still_applies(
        self, copy_generic_minimal, write_patch, tmp_path
    ):
        """An additive policy patch keeps working under the stricter check."""
        root = copy_generic_minimal()
        patch_file = tmp_path / "add.patch.json"
        write_patch(
            patch_file,
            [
                {
                    "op": "add",
                    "path": "/stages/-",
                    "value": {
                        "id": "S3",
                        "name": "extra",
                        "responsibility": "extra stage for the test",
                        "depends_on": [],
                        "verification_type": "file_exists",
                        "required_contract_fields": ["target"],
                    },
                }
            ],
        )
        result = apply_patch_to_target(
            root, ".quality-system/policy.json", patch_file
        )
        assert result.written is True
        assert _stage_ids(root) == ["S1", "S2", "S3"]


# ---------------------------------------------------------------------------
# The documented 3-step migration (additive adopt -> meta patch -> removal)
# ---------------------------------------------------------------------------


class TestThreeStepMigration:
    def test_full_migration_succeeds_where_one_shot_fails(
        self, copy_generic_minimal, write_patch, tmp_path
    ):
        root = copy_generic_minimal()

        # Step (a): additive adopt — S3 joins S1/S2.
        adopt_proposal(root, ADDITIVE)
        assert _stage_ids(root) == ["S1", "S2", "S3"]

        # Step (b): migrate REQ-APP-001 from S1 to S3. The new stage
        # needs its contract on disk first (contracts are per-REQ files,
        # not part of the proposal).
        contract_dir = root / ".quality-system" / "contracts" / REQ
        (contract_dir / "S3.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "req_id": REQ,
                    "stage_id": "S3",
                    "verification_type": "file_exists",
                    "target": "target/sample.txt",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        meta_patch = tmp_path / "migrate.patch.json"
        write_patch(
            meta_patch,
            [
                {
                    "op": "replace",
                    "path": "/stages/0",
                    "value": {
                        "stage_id": "S3",
                        "contract_ref": (
                            f".quality-system/contracts/{REQ}/S3.json"
                        ),
                        "required": True,
                    },
                }
            ],
        )
        apply_patch_to_target(
            root, f".quality-system/req/{REQ}.meta.json", meta_patch
        )

        # Step (c): removal adopt — S1 disappears, S2 re-roots onto S3.
        removal = tmp_path / "removal.json"
        removal.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "proposal_type": "policy_stages",
                    "source_metadata": {"generator": "fixture"},
                    "stages": [
                        {
                            "id": "S3",
                            "name": "設定ファイル存在",
                            "responsibility": "target/sample.txt が存在する",
                            "depends_on": [],
                            "verification_type": "file_exists",
                            "required_contract_fields": ["target"],
                        },
                        {
                            "id": "S2",
                            "name": "キーワード包含",
                            "responsibility": (
                                "target/sample.txt に \"hello\" が含まれる"
                            ),
                            "depends_on": ["S3"],
                            "verification_type": "substring_match",
                            "required_contract_fields": [
                                "target", "must_contain",
                            ],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        adopt_proposal(root, removal)
        assert _stage_ids(root) == ["S3", "S2"]

        # The migrated world passes an official rehearsal end-to-end.
        assert main(["check", REQ, "--path", str(root), "--json"]) == 0


# ---------------------------------------------------------------------------
# A-series: missing AdoptError reason coverage (policy_schema_invalid,
# atomic_write_failed) + collect_same_world_blockers dedupe
# ---------------------------------------------------------------------------


class TestAdoptMissingReasons:
    """Cover the two AdoptError reasons not exercised by TestAdoptRejects."""

    def test_policy_schema_invalid(self, copy_generic_minimal):
        """Assembled policy violates policy.schema.json (missing required field)."""
        root = copy_generic_minimal()
        policy = _policy_path(root)
        current = json.loads(policy.read_text(encoding="utf-8"))
        del current["schema_version"]
        policy.write_text(
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, ADDITIVE)
        assert exc.value.reason == "policy_schema_invalid"
        assert exc.value.detail["issues"]

    def test_atomic_write_failed(self, copy_generic_minimal, monkeypatch):
        """Simulate os.replace failure on the final atomic swap."""
        root = copy_generic_minimal()

        from qgb.core import patch_apply as pa_mod
        from qgb.core.patch_apply import PatchApplyError

        def _boom(target, doc):
            raise PatchApplyError(
                reason="io_error",
                message="simulated os.replace failure",
            )

        monkeypatch.setattr(pa_mod, "_atomic_write_json", _boom)
        # Re-import to pick up the monkeypatch (proposal.py imports the
        # function directly, so patch the module-level ref too).
        import qgb.core.proposal as prop_mod
        monkeypatch.setattr(prop_mod, "_atomic_write_json", _boom)

        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, ADDITIVE)
        assert exc.value.reason == "atomic_write_failed"


class TestDedupeBlockers:
    """Verify collect_same_world_blockers deduplication."""

    def test_project_wide_blocker_not_duplicated_per_req(
        self, copy_generic_minimal
    ):
        """A knowledge orphan blocker appears in the project-wide report AND
        in every per-REQ report. Dedupe should keep only the first occurrence
        (scope="<project>") and suppress REQ-scoped duplicates."""
        from qgb.core.preflight import (
            PreflightIssue,
            PreflightReport,
            collect_same_world_blockers,
        )

        shared = PreflightIssue(
            kind="knowledge_orphan",
            where="knowledge.jsonl#WAIV-1",
            message="waiver references non-existent REQ",
            severity="blocker",
        )
        req_only = PreflightIssue(
            kind="unknown_stage_id",
            where="REQ-APP-001.meta.json stages[0]",
            message="stage_id 'S99' not in policy",
            severity="blocker",
        )
        project_report = PreflightReport(issues=[shared])
        req_report = PreflightReport(issues=[shared, req_only])

        reports = [
            (None, project_report),
            ("REQ-APP-001", req_report),
        ]
        blockers = collect_same_world_blockers(reports)

        # shared blocker: deduped to scope="<project>" (first occurrence)
        shared_hits = [b for b in blockers if b["kind"] == "knowledge_orphan"]
        assert len(shared_hits) == 1
        assert shared_hits[0]["scope"] == "<project>"

        # REQ-specific blocker: kept with REQ scope
        req_hits = [b for b in blockers if b["kind"] == "unknown_stage_id"]
        assert len(req_hits) == 1
        assert req_hits[0]["scope"] == "REQ-APP-001"

        assert len(blockers) == 2


class TestBOMTolerance:
    """BOM-encoded proposal and policy files are handled correctly."""

    def test_proposal_with_bom_is_accepted(self, copy_generic_minimal):
        """PS5.1 Out-File writes UTF-8 with BOM; adopt must tolerate it."""
        root = copy_generic_minimal()
        bom_proposal = root / "bom_proposal.json"
        raw = ADDITIVE.read_bytes()
        bom_proposal.write_bytes(b"\xef\xbb\xbf" + raw)
        result = adopt_proposal(root, bom_proposal)
        assert result.written is True

    def test_policy_with_bom_is_readable(self, copy_generic_minimal):
        """Current policy.json with BOM should not block adopt."""
        root = copy_generic_minimal()
        policy = root / ".quality-system" / "policy.json"
        raw = policy.read_bytes()
        policy.write_bytes(b"\xef\xbb\xbf" + raw)
        result = adopt_proposal(root, ADDITIVE)
        assert result.written is True


class TestRecursionGuard:
    """Deep-nest proposal does not crash with raw traceback."""

    def test_deeply_nested_proposal_gives_schema_invalid(
        self, copy_generic_minimal, tmp_path
    ):
        root = copy_generic_minimal()
        nested: dict = {"schema_version": "1.0", "proposal_type": "policy_stages", "stages": []}
        current = nested["stages"]
        for _ in range(500):
            inner: list = []
            current.append({"x": inner})
            current = inner
        doc = tmp_path / "deep.json"
        doc.write_text(json.dumps(nested), encoding="utf-8")
        with pytest.raises(AdoptError) as exc:
            adopt_proposal(root, doc)
        assert exc.value.reason in ("schema_invalid", "invalid_json")


# ---------------------------------------------------------------------------
# Legacy design-stages surface stays untouched
# ---------------------------------------------------------------------------


class TestLegacyDesignStages:
    def test_flag_form_still_works(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["design-stages", "--path", str(root), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        # Legacy rule-based proposal payload, not the Step 2.5 surfaces.
        assert "stages" in json.dumps(payload)
