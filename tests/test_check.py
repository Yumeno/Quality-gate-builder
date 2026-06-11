"""Tests for ``qgb check`` / ``qgb dev`` (Phase 2 Step 2.4).

The load-bearing assertions are the boundary ones (設計境界 3):

* check writes ONLY under ``.quality-system/artifacts/<REQ>/checks/``,
* curated ``evidence/<REQ>/latest/``, ``knowledge.jsonl`` and the
  official ``artifacts/<REQ>/runs/`` tree are byte-identical before and
  after a check (machine-verify, not just "looks untouched"),
* an unrelated knowledge orphan (blocker in validate-policy) does NOT
  change a per-REQ check's outcome or exit code.
"""

from __future__ import annotations

import copy
import json

from qgb.cli import main
from qgb.core.check import CHECK_MEANING_NOTE, run_check
from qgb.core.knowledge import (
    append_knowledge_entries,
    build_waiver_knowledge_entry,
)
from qgb.core.preflight import validate_policy_preflight
from qgb.core.schema import is_valid, validate

REQ = "REQ-APP-001"


def _norm_snapshot(snap: dict[str, bytes]) -> dict[str, bytes]:
    """Normalise snapshot keys to forward slashes (Windows-stable)."""
    return {k.replace("\\", "/"): v for k, v in snap.items()}


def _set_stage_waived(root, stage_ids: tuple[str, ...] = ("S2",)) -> None:
    """Mark the given stages waived in REQ-APP-001's meta (Step 7 fields)."""
    meta_path = root / ".quality-system" / "req" / f"{REQ}.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for entry in meta["stages"]:
        if entry["stage_id"] in stage_ids:
            entry["waived"] = True
            entry["waiver_reason"] = "accepted for check rehearsal tests"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _orphan_entry() -> dict:
    """A schema-valid waiver entry whose REQ does not exist (orphan)."""
    return build_waiver_knowledge_entry(
        "REQ-GONE-001",
        "S1",
        "orphan fixture for check advisory tests",
        decided_by="tester",
        created_at="2026-06-11T00:00:00Z",
    )


# ---------------------------------------------------------------------------
# core: run_check
# ---------------------------------------------------------------------------


class TestRunCheckBoundary:
    def test_allow_writes_checks_dir_only(
        self, copy_generic_minimal, snapshot_dir
    ):
        root = copy_generic_minimal()
        before = _norm_snapshot(snapshot_dir(root))

        out = run_check(root, REQ)

        assert out.decision is not None
        assert out.decision.status == "ALLOW"
        assert out.gate is not None
        assert out.gate["mode"] == "check"
        assert "curated_latest_dir" not in out.gate["paths"]
        assert out.check_dir is not None and out.check_dir.is_dir()
        assert (out.check_dir / "gate.json").is_file()
        assert (out.check_dir / "summary.md").is_file()
        assert (out.check_dir / "stages" / "S1.log").is_file()
        assert (out.check_dir / "stages" / "S2.log").is_file()

        after = _norm_snapshot(snapshot_dir(root))
        # Snapshot includes directories, so the allowed additions are the
        # checks/ subtree plus its newly created parent dir for this REQ.
        checks_prefix = f".quality-system/artifacts/{REQ}/checks"
        req_artifacts_dir = f".quality-system/artifacts/{REQ}"
        new_keys = set(after) - set(before)
        assert new_keys, "check must write volatile artifacts (debuggability)"
        assert all(
            k.startswith(checks_prefix) or k == req_artifacts_dir
            for k in new_keys
        ), f"unexpected additions outside checks/: {sorted(new_keys)}"
        # Every pre-existing entry is byte-identical.
        for k in before:
            assert after[k] == before[k], f"check mutated pre-existing entry {k}"

    def test_official_outputs_untouched_when_present(
        self, copy_generic_minimal, snapshot_dir
    ):
        root = copy_generic_minimal()
        # Produce official curated evidence + a runs/ dir first.
        assert main(["run", REQ, "--path", str(root), "--yes"]) == 0
        qs = root / ".quality-system"
        evidence_before = _norm_snapshot(snapshot_dir(qs / "evidence"))
        runs_root = qs / "artifacts" / REQ / "runs"
        runs_before = sorted(p.name for p in runs_root.iterdir())

        out = run_check(root, REQ)

        assert out.decision is not None and out.decision.status == "ALLOW"
        assert _norm_snapshot(snapshot_dir(qs / "evidence")) == evidence_before
        assert sorted(p.name for p in runs_root.iterdir()) == runs_before

    def test_deny_records_failed_stage_and_still_writes(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        (root / "target" / "sample.txt").unlink()

        out = run_check(root, REQ)

        assert out.decision is not None
        assert out.decision.status == "DENY"
        assert out.gate is not None
        assert out.gate["failed_stage"] == "S1"
        assert out.check_dir is not None
        assert (out.check_dir / "gate.json").is_file()
        # DENY rehearsal gates satisfy both gate schemas too.
        assert validate(out.gate, "gate") == []
        assert validate(out.gate, "gate-runtime") == []

    def test_meaning_carries_rehearsal_note(self, copy_generic_minimal):
        root = copy_generic_minimal()
        out = run_check(root, REQ)
        assert out.gate is not None
        assert out.gate["decision"]["meaning"].endswith(CHECK_MEANING_NOTE)
        # summary.md carries the human-facing rehearsal banner and drops
        # the curated_latest_dir row (there is no curated dir to cite).
        assert out.check_dir is not None
        summary = (out.check_dir / "summary.md").read_text(encoding="utf-8")
        assert "正式な採用判定ではない" in summary
        assert "curated_latest_dir" not in summary

    def test_meaning_is_official_meaning_plus_note(
        self, copy_generic_minimal, capsys
    ):
        """The official wording stays verbatim (F-016); check only appends."""
        root = copy_generic_minimal()
        assert main(["run", REQ, "--path", str(root), "--yes"]) == 0
        capsys.readouterr()
        run_gate = json.loads(
            (
                root / ".quality-system" / "evidence" / REQ / "latest"
                / "gate.json"
            ).read_text(encoding="utf-8")
        )
        run_meaning = run_gate["decision"]["meaning"]
        assert CHECK_MEANING_NOTE not in run_meaning
        out = run_check(root, REQ)
        assert out.gate is not None
        assert (
            out.gate["decision"]["meaning"]
            == f"{run_meaning} {CHECK_MEANING_NOTE}"
        )

    def test_preflight_blocked_writes_nothing(self, copy_generic_minimal):
        root = copy_generic_minimal()
        (root / ".quality-system" / "req" / f"{REQ}.meta.json").unlink()

        out = run_check(root, REQ)

        assert out.decision is None
        assert out.gate is None
        assert out.check_dir is None
        assert out.preflight.has_blockers()
        assert not (
            root / ".quality-system" / "artifacts" / REQ / "checks"
        ).exists()

    def test_prune_reuses_keep_runs(self, copy_generic_minimal):
        root = copy_generic_minimal()
        for _ in range(3):
            run_check(root, REQ, keep_runs=2)
        checks_root = root / ".quality-system" / "artifacts" / REQ / "checks"
        assert len([p for p in checks_root.iterdir() if p.is_dir()]) == 2

    def test_cli_prune_via_qgb_keep_runs_env(
        self, copy_generic_minimal, monkeypatch, capsys
    ):
        """The production prune path is env-driven (CLI passes no keep_runs)."""
        root = copy_generic_minimal()
        monkeypatch.setenv("QGB_KEEP_RUNS", "2")
        for _ in range(3):
            assert main(["check", REQ, "--path", str(root)]) == 0
        capsys.readouterr()
        checks_root = root / ".quality-system" / "artifacts" / REQ / "checks"
        assert len([p for p in checks_root.iterdir() if p.is_dir()]) == 2

    def test_check_never_prunes_official_runs(self, copy_generic_minimal):
        """checks/ is pruned; runs/ must survive even past the keep limit."""
        root = copy_generic_minimal()
        runs_root = root / ".quality-system" / "artifacts" / REQ / "runs"
        runs_root.mkdir(parents=True)
        for i in (1, 2, 3):
            d = runs_root / f"2026-01-01T00000{i}Z-r0001"
            d.mkdir()
            (d / "gate.json").write_text("{}", encoding="utf-8")
        run_check(root, REQ, keep_runs=1)
        assert len(list(runs_root.iterdir())) == 3
        checks_root = root / ".quality-system" / "artifacts" / REQ / "checks"
        assert len([p for p in checks_root.iterdir() if p.is_dir()]) == 1


class TestRunCheckWaived:
    """The only world state where run and check genuinely diverge."""

    def test_waived_req_check_never_appends_knowledge(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        _set_stage_waived(root, ("S2",))
        kjsonl = root / ".quality-system" / "knowledge" / "knowledge.jsonl"

        out = run_check(root, REQ)

        assert out.decision is not None and out.decision.status == "ALLOW"
        assert out.gate is not None
        results = {s["id"]: s["result"] for s in out.gate["stages"]}
        assert results == {"S1": "passed", "S2": "waived"}
        # check writes NO waiver evidence...
        assert not kjsonl.exists()
        # ...while its basis mirrors what an official run would record
        # (rehearsal fidelity; see check.py module docstring).
        assert f"KNOWLEDGE-WAIVER-{REQ}-S2" in out.gate["basis"]
        # Contrast: the official run does append the waiver evidence.
        assert main(["run", REQ, "--path", str(root), "--yes"]) == 0
        assert kjsonl.is_file()

    def test_waived_check_gate_valid_against_both_schemas(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        _set_stage_waived(root, ("S2",))
        out = run_check(root, REQ)
        assert out.gate is not None
        assert validate(out.gate, "gate") == []
        assert validate(out.gate, "gate-runtime") == []

    def test_all_waived_check_gate_deny_valid(self, copy_generic_minimal):
        root = copy_generic_minimal()
        _set_stage_waived(root, ("S1", "S2"))
        out = run_check(root, REQ)
        assert out.decision is not None and out.decision.status == "DENY"
        assert out.gate is not None
        assert out.gate["failed_stage"] == ""
        assert validate(out.gate, "gate") == []
        assert validate(out.gate, "gate-runtime") == []


class TestRunCheckCorruptKnowledge:
    def test_byte_torn_tail_does_not_crash_check(
        self, copy_generic_minimal, capsys
    ):
        """A multi-byte char cut mid-append must hit partial-tail skip."""
        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])
        kjsonl = root / ".quality-system" / "knowledge" / "knowledge.jsonl"
        torn = json.dumps(
            {"id": "TORN", "kind": "waiver", "reason": "日本語の理由"},
            ensure_ascii=False,
        ).encode("utf-8")[:-3]  # cuts inside the last multi-byte char
        with kjsonl.open("ab") as fh:
            fh.write(torn)  # no trailing newline: the partial-tail shape

        out = run_check(root, REQ)

        assert out.decision is not None and out.decision.status == "ALLOW"
        assert any(
            f.knowledge_id == "WAIVER-REQ-GONE-001-S1"
            for f in out.orphan_findings
        )
        # The REQ-less path survives too and still enforces the orphan.
        assert main(["check", "--path", str(root)]) == 2
        capsys.readouterr()

    def test_mid_file_corruption_is_loud_not_silent(
        self, copy_generic_minimal, capsys
    ):
        """補修 B1: a byte corrupted INSIDE a terminated line must not be
        silently tolerated (the old strict decoder crashed loudly; the
        errors="replace" decode alone would have let it parse as valid
        JSON and pass)."""
        from qgb.core.knowledge import check_knowledge_orphans
        from qgb.core.validate import run_validate

        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])
        jp_entry = build_waiver_knowledge_entry(
            "REQ-GONE-002",
            "S1",
            "日本語の理由です",
            decided_by="tester",
            created_at="2026-06-11T00:00:00Z",
        )
        append_knowledge_entries(root, [jp_entry])
        kjsonl = root / ".quality-system" / "knowledge" / "knowledge.jsonl"
        data = kjsonl.read_bytes()
        assert data.endswith(b"\n")
        corrupted = data.replace("日".encode(), b"\xe6\xff\xa5", 1)
        assert corrupted != data
        kjsonl.write_bytes(corrupted)

        # qgb validate reports it loudly as a read error...
        report = run_validate(root)
        assert any("U+FFFD" in re_.message for re_ in report.read_errors)
        # ...the per-REQ check therefore goes NOT_READY (no silent pass)...
        assert main(["check", REQ, "--path", str(root)]) == 2
        capsys.readouterr()
        # ...and the orphan scan derives nothing from the corrupted line
        # while still seeing the intact one.
        ids = {f.knowledge_id for f in check_knowledge_orphans(root)}
        assert "WAIVER-REQ-GONE-001-S1" in ids
        assert "WAIVER-REQ-GONE-002-S1" not in ids


class TestRunCheckOrphanAdvisory:
    def test_unrelated_orphan_blocker_does_not_change_outcome(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])

        # The same world state IS a blocker for validate-policy...
        assert validate_policy_preflight(root, None).has_blockers()

        # ...but the per-REQ check rehearsal is not blocked by it.
        out = run_check(root, REQ)
        assert out.decision is not None
        assert out.decision.status == "ALLOW"
        assert any(f.severity == "blocker" for f in out.orphan_findings)


class TestCheckGateSchema:
    def test_check_gate_valid_against_both_gate_schemas(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        out = run_check(root, REQ)
        assert out.gate is not None
        assert validate(out.gate, "gate") == []
        assert validate(out.gate, "gate-runtime") == []

    def test_mode_check_with_curated_dir_is_schema_invalid(
        self, copy_generic_minimal
    ):
        root = copy_generic_minimal()
        out = run_check(root, REQ)
        assert out.gate is not None
        polluted = copy.deepcopy(out.gate)
        polluted["paths"]["curated_latest_dir"] = (
            f".quality-system/evidence/{REQ}/latest"
        )
        assert not is_valid(polluted, "gate")
        assert not is_valid(polluted, "gate-runtime")

    def test_official_gate_without_curated_dir_stays_invalid(
        self, copy_generic_minimal
    ):
        """Backward-compat guard: mode-less gates still require curated dir."""
        root = copy_generic_minimal()
        out = run_check(root, REQ)
        assert out.gate is not None
        demoted = copy.deepcopy(out.gate)
        del demoted["mode"]
        assert not is_valid(demoted, "gate")
        assert not is_valid(demoted, "gate-runtime")

    def test_official_run_gate_unchanged_and_still_valid(
        self, copy_generic_minimal, read_json
    ):
        """qgb run output is byte-compatible: no mode field, curated present."""
        root = copy_generic_minimal()
        assert main(["run", REQ, "--path", str(root), "--yes"]) == 0
        gate = read_json(
            root / ".quality-system" / "evidence" / REQ / "latest" / "gate.json"
        )
        assert "mode" not in gate
        assert "curated_latest_dir" in gate["paths"]
        assert validate(gate, "gate") == []


# ---------------------------------------------------------------------------
# CLI: qgb check / qgb dev
# ---------------------------------------------------------------------------


class TestCheckCli:
    def test_allow_json_exit0(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["check", REQ, "--path", str(root), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["command"] == "check"
        assert payload["rehearsal"] is True
        assert payload["status"] == "ALLOW"
        assert payload["gate"]["mode"] == "check"
        assert payload["check_dir"].startswith(
            f".quality-system/artifacts/{REQ}/checks/"
        )

    def test_allow_text_mentions_rehearsal(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["check", REQ, "--path", str(root)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "would ALLOW" in captured.out
        assert "not an official gate" in captured.out

    def test_deny_exit1_text_on_stderr(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        (root / "target" / "sample.txt").unlink()
        rc = main(["check", REQ, "--path", str(root)])
        assert rc == 1
        captured = capsys.readouterr()
        assert "would DENY" in captured.err
        assert "failed_stage: S1" in captured.err

    def test_not_ready_exit2(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        (root / ".quality-system" / "req" / f"{REQ}.meta.json").unlink()
        rc = main(["check", REQ, "--path", str(root), "--json"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "NOT_READY"
        assert payload["command"] == "check"

    def test_no_confirmation_needed_unlike_run(
        self, copy_generic_minimal, capsys
    ):
        """check has no F-008 prompt: non-TTY without --yes still runs."""
        root = copy_generic_minimal()
        # qgb run without --yes refuses in non-TTY contexts (F-008)...
        assert main(["run", REQ, "--path", str(root)]) == 2
        # ...while qgb check proceeds (it never mutates curated evidence).
        assert main(["check", REQ, "--path", str(root)]) == 0
        capsys.readouterr()

    def test_orphan_advisory_shown_but_not_blocking(
        self, copy_generic_minimal, capsys
    ):
        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])
        rc = main(["check", REQ, "--path", str(root), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        advisories = payload["orphan_advisories"]
        assert any(a["severity"] == "blocker" for a in advisories)
        assert any(a["knowledge_id"] == "WAIVER-REQ-GONE-001-S1" for a in advisories)

    def test_project_wide_clean_exit0(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["check", "--path", str(root), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "check"
        assert payload["scope"] == "project"
        assert payload["ok"] is True

    def test_project_wide_orphan_blocker_exit2(
        self, copy_generic_minimal, capsys
    ):
        """REQ-less check DOES enforce orphan blockers (validate-policy path)."""
        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])
        rc = main(["check", "--path", str(root), "--json"])
        assert rc == 2
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert any(
            b["kind"] == "knowledge_orphan" for b in payload["blockers"]
        )

    def test_deny_text_shows_orphan_advisory(
        self, copy_generic_minimal, capsys
    ):
        root = copy_generic_minimal()
        append_knowledge_entries(root, [_orphan_entry()])
        (root / "target" / "sample.txt").unlink()
        rc = main(["check", REQ, "--path", str(root)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "knowledge orphan advisories" in err
        assert "WAIVER-REQ-GONE-001-S1" in err

    def test_phase_red_deny_exit1_with_expected_meaning(
        self, copy_generic_minimal, capsys
    ):
        root = copy_generic_minimal()
        (root / "target" / "sample.txt").unlink()
        rc = main(["check", REQ, "--path", str(root), "--phase", "red", "--json"])
        assert rc == 1
        payload = json.loads(capsys.readouterr().out)
        meaning = payload["gate"]["decision"]["meaning"]
        assert "fails as expected" in meaning
        assert meaning.endswith(CHECK_MEANING_NOTE)
        assert payload["gate"]["phase"] == "red"

    def test_req_less_phase_is_warned(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["check", "--path", str(root), "--phase", "red"])
        assert rc == 0
        assert "--phase is ignored" in capsys.readouterr().err

    def test_dev_is_thin_alias(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["dev", REQ, "--path", str(root), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["command"] == "check"
        assert payload["rehearsal"] is True

    def test_dev_text_output(self, copy_generic_minimal, capsys):
        root = copy_generic_minimal()
        rc = main(["dev", REQ, "--path", str(root)])
        assert rc == 0
        assert "would ALLOW" in capsys.readouterr().out
