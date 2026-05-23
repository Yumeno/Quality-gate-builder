"""Step 5 acceptance tests: `qgb run` against examples/generic-minimal/.

These tests are the contract that finalises Step 5 (#20). The hand-written
``examples/generic-minimal/`` (Step 4) is the reference; running ``qgb run``
against a *copy* of it must produce:

* exit 0 + ALLOW + a curated gate.json equivalent to the reference one,
* exit 1 + DENY when ``target/sample.txt`` is removed,
* exit 2 + NOT_READY when an invariant is broken (e.g. missing contract file).

The tests copy the example to ``tmp_path`` so they never mutate the repo
working tree. Inputs from the example are read-only; only the copy is
exercised.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from qgb.cli import EXIT_DENY, EXIT_NOT_READY, EXIT_OK, main
from qgb.core.schema import validate as schema_validate

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


# ---- helpers -------------------------------------------------------------


def _copy_generic_minimal(dest: Path) -> Path:
    """Copy the generic-minimal example tree to ``dest``.

    Returns the project root inside ``dest``. The volatile ``artifacts/``
    and any leftover ``evidence/`` (both ``.gitignore``'d) from prior
    in-repo runs are deliberately stripped so tests always start from a
    clean fixture state.
    """
    target = dest / "generic-minimal"
    shutil.copytree(
        GENERIC_MINIMAL,
        target,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
    return target


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _gate(project_root: Path) -> dict:
    return _read_json(
        project_root
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "gate.json"
    )


# ---- core: ALLOW path ----------------------------------------------------


def test_run_generic_minimal_returns_allow(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _copy_generic_minimal(tmp_path)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])

    assert exit_code == EXIT_OK
    gate = _gate(project)
    assert gate["status"] == "ALLOW"
    assert gate["decision"]["result"] == "ALLOW"
    assert gate["failed_stage"] == ""
    assert [s["result"] for s in gate["stages"]] == ["passed", "passed"]


def test_run_writes_curated_gate_and_summary(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_OK

    curated = project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest"
    assert (curated / "gate.json").is_file()
    assert (curated / "summary.md").is_file()
    # log_ref entries must resolve to real files.
    gate = _read_json(curated / "gate.json")
    for stage in gate["stages"]:
        assert (curated / stage["log_ref"]).is_file(), stage["log_ref"]


def test_run_writes_volatile_run_dir(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_OK

    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"
    assert runs_dir.is_dir()
    children = [p for p in runs_dir.iterdir() if p.is_dir()]
    assert len(children) == 1
    run_dir = children[0]
    # gate.json + summary.md + stages/ must all be present in the volatile run dir too.
    assert (run_dir / "gate.json").is_file()
    assert (run_dir / "summary.md").is_file()
    assert (run_dir / "stages").is_dir()


def test_curated_gate_conforms_to_strict_schema(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--path", str(project)])

    gate = _gate(project)
    issues = schema_validate(gate, "gate")
    assert not issues, [(i.path, i.message) for i in issues]


def test_curated_gate_matches_reference_structure(tmp_path: Path) -> None:
    """Phase 1 contract: generated gate matches the hand-written reference shape."""
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--path", str(project)])

    gate = _gate(project)

    # Top-level required fields per gate.schema.json (strict).
    expected_keys = {
        "schema_version",
        "req_id",
        "timestamp_utc",
        "timestamp_rfc3339",
        "run_id",
        "phase",
        "status",
        "failed_stage",
        "decision",
        "runner",
        "paths",
        "stages",
        "basis",
    }
    assert set(gate.keys()) == expected_keys

    assert gate["req_id"] == "REQ-APP-001"
    assert gate["runner"]["name"] == "qgb"
    # paths.run_dir suffix equals <timestamp_utc>-<run_id> (Step 5 三次補修).
    run_dir = gate["paths"]["run_dir"]
    assert run_dir.endswith(f"{gate['timestamp_utc']}-{gate['run_id']}"), (
        run_dir,
        gate["timestamp_utc"],
        gate["run_id"],
    )
    assert (
        gate["paths"]["curated_latest_dir"]
        == ".quality-system/evidence/REQ-APP-001/latest"
    )
    # basis[] required content (§7.5).
    basis = set(gate["basis"])
    assert "REQ-APP-001" in basis
    assert "POLICY-default" in basis
    assert "CONTRACT-REQ-APP-001-S1" in basis
    assert "CONTRACT-REQ-APP-001-S2" in basis


def test_curated_and_volatile_gates_have_identical_content(tmp_path: Path) -> None:
    """Phase 1: the gate written to curated/latest and to artifacts/runs/<ts>/ are equal."""
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--path", str(project)])

    curated = _gate(project)
    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"
    run_dir = next(p for p in runs_dir.iterdir() if p.is_dir())
    volatile = _read_json(run_dir / "gate.json")

    assert curated == volatile


def test_timestamps_in_two_formats_describe_same_instant(tmp_path: Path) -> None:
    import re

    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--path", str(project)])

    gate = _gate(project)
    utc = gate["timestamp_utc"]
    rfc = gate["timestamp_rfc3339"]
    m = re.fullmatch(
        r"(\d{4})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})Z", utc
    )
    assert m, utc
    expected_rfc = (
        f"{m.group(1)}-{m.group(2)}-{m.group(3)}T"
        f"{m.group(4)}:{m.group(5)}:{m.group(6)}Z"
    )
    assert rfc == expected_rfc


# ---- DENY path -----------------------------------------------------------


def test_run_returns_deny_when_target_is_missing(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY

    gate = _gate(project)
    assert gate["status"] == "DENY"
    assert gate["decision"]["result"] == "DENY"
    assert gate["failed_stage"] == "S1"
    # In Phase 1, S2 is skipped (or failed) after S1 fails because S2 depends_on S1.
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "failed"


def test_run_returns_deny_when_keyword_missing(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").write_text(
        "no greeting here\n", encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY

    gate = _gate(project)
    assert gate["status"] == "DENY"
    assert gate["failed_stage"] == "S2"
    s2 = next(s for s in gate["stages"] if s["id"] == "S2")
    assert s2["result"] == "failed"


def test_deny_gate_conforms_to_strict_schema(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()

    main(["run", "REQ-APP-001", "--path", str(project)])

    gate = _gate(project)
    issues = schema_validate(gate, "gate")
    assert not issues, [(i.path, i.message) for i in issues]


# ---- NOT_READY path ------------------------------------------------------


def test_run_returns_not_ready_when_contract_ref_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _copy_generic_minimal(tmp_path)
    # Break the reference: remove S1.json so contract_ref points nowhere.
    (project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json").unlink()

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY

    # A NOT_READY run must not write any curated gate.json. Step 5 補修:
    # the in-repo example no longer ships a hand-written gate.json under
    # .quality-system/evidence/, so the destination should still be empty
    # after a rejected preflight.
    curated_gate = (
        project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest" / "gate.json"
    )
    assert not curated_gate.exists(), (
        "NOT_READY runs must not create or overwrite curated gate.json"
    )


def test_run_returns_not_ready_when_req_meta_stage_id_unknown(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    # Inject a stage id that does not exist in policy.json.
    meta["stages"].append(
        {
            "stage_id": "S999",
            "contract_ref": ".quality-system/contracts/REQ-APP-001/S1.json",
            "required": True,
        }
    )
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


def test_preflight_helpers_are_individually_callable(tmp_path: Path) -> None:
    """Step 5 三次補修 (B 部分前倒し): the 5 helpers are usable independently.

    ``qgb validate-policy`` (Step 6) will compose these helpers in a
    different order, so we lock down their individual contracts here.
    The composite ``run_preflight`` is exercised throughout the rest of
    this module, so we only need to confirm direct invocation here.
    """
    from qgb.core.loader import load_policy, load_req_meta
    from qgb.core.preflight import (
        PreflightReport,
        check_runtime_support,
        inspect_policy_graph,
        resolve_adopted_stages,
        validate_schema_sources,
    )

    project = _copy_generic_minimal(tmp_path)

    report = PreflightReport()
    validate_schema_sources(project, report)
    assert not report.issues, report.issues

    policy = load_policy(project)
    policy_stages = inspect_policy_graph(policy, report)
    assert {sid for sid in policy_stages} == {"S1", "S2"}

    req_meta = load_req_meta(project, "REQ-APP-001")
    adopted = resolve_adopted_stages(
        project, "REQ-APP-001", policy_stages, req_meta, report
    )
    assert [a.stage_id for a in adopted] == ["S1", "S2"]

    runnable = check_runtime_support(adopted, report)
    assert [a.stage_id for a in runnable] == ["S1", "S2"]
    assert not report.issues


def test_preflight_issue_defaults_to_blocker_severity(tmp_path: Path) -> None:
    """Step 5 三次補修 (B 部分前倒し): PreflightIssue.severity defaults to blocker.

    Step 5 introduces severity as a future-compatible field. Until Step 6
    validate-policy starts emitting warnings, the runner treats every
    issue as a blocker, so the default is verified here directly on the
    in-process preflight call.
    """
    from qgb.core.preflight import run_preflight

    project = _copy_generic_minimal(tmp_path)
    # Force a NOT_READY: remove the S1 contract file.
    (project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json").unlink()

    report = run_preflight(project, "REQ-APP-001")
    assert report.issues, "preflight should have produced at least one issue"
    for issue in report.issues:
        assert issue.severity == "blocker", (issue.kind, issue.severity)


def test_preflight_report_diagnostic_api(tmp_path: Path) -> None:
    """Step 6a Commit 1: PreflightReport の診断 API は severity を区別する。

    iter_issues() は severity フィルタを受ける、blocking_issues() と
    warnings() は同等の絞り込みを返す、has_blockers() は blocker の有無、
    ready_for_run() は blocker が無いことを表す。これらは validate-policy
    実装の足場であり、Step 6a Commit 2 で初の warning が乗ったときに
    挙動が分岐する地点になる。
    """
    from qgb.core.preflight import PreflightIssue, PreflightReport

    report = PreflightReport()
    assert list(report.iter_issues()) == []
    assert report.blocking_issues() == []
    assert report.warnings() == []
    assert not report.has_blockers()
    assert report.ready_for_run()

    blocker = PreflightIssue(
        kind="missing_contract",
        where="x",
        message="m",
        severity="blocker",
    )
    warning = PreflightIssue(
        kind="missing_contract",
        where="y",
        message="m",
        severity="warning",
    )
    report.issues.extend([blocker, warning])

    assert list(report.iter_issues()) == [blocker, warning]
    assert list(report.iter_issues(severity="blocker")) == [blocker]
    assert list(report.iter_issues(severity="warning")) == [warning]
    assert report.blocking_issues() == [blocker]
    assert report.warnings() == [warning]
    assert report.has_blockers()
    assert not report.ready_for_run()


def test_preflight_report_warnings_only_is_ready_for_run(tmp_path: Path) -> None:
    """warning だけのレポートは ready_for_run() == True。

    Step 6a Commit 1 の段階では Phase 1 のどの検査も warning を発しないが、
    Commit 2 で stage_count_out_of_range が warning として乗る。その時点で
    qgb run は warning を無視して続行する必要があるため、API レベルで
    先にロックする。
    """
    from qgb.core.preflight import PreflightIssue, PreflightReport

    report = PreflightReport()
    report.issues.append(
        PreflightIssue(
            kind="missing_contract",
            where="x",
            message="advisory",
            severity="warning",
        )
    )
    assert report.warnings()
    assert not report.has_blockers()
    assert report.ready_for_run()


def test_preflight_legacy_ready_matches_ready_for_run() -> None:
    """ready() は Step 5 までの後方互換。新規呼び出しは ready_for_run() を使う。

    cli.py / runner.py が新 API に移行済みであることを担保しつつ、Step 5
    で書かれた外部スクリプトが落ちないことも併せて確認する。
    """
    from qgb.core.preflight import PreflightIssue, PreflightReport

    report = PreflightReport()
    assert report.ready() is report.ready_for_run() is True

    report.issues.append(
        PreflightIssue(
            kind="missing_contract",
            where="x",
            message="m",
            severity="blocker",
        )
    )
    assert report.ready() is report.ready_for_run() is False


def test_run_returns_not_ready_when_req_meta_order_violates_depends_on(
    tmp_path: Path,
) -> None:
    """Step 5 三次補修 (M1): REQ meta order must respect policy depends_on.

    policy.json declares S2 depends_on [S1]. If REQ meta writes the
    stages in the order [S2, S1], the runner would otherwise execute S2
    before S1 has run, producing misleading results. Preflight catches
    the order violation as NOT_READY.
    """
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    # Reverse the stage order.
    meta["stages"] = list(reversed(meta["stages"]))
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


def test_run_returns_not_ready_for_unknown_req(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    exit_code = main(["run", "REQ-APP-999", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


# ---- subprocess smoke (real entry point) ---------------------------------


def _run_qgb_subprocess(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "qgb", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_run_subprocess_allow(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    result = _run_qgb_subprocess("run", "REQ-APP-001", "--path", str(project))
    assert result.returncode == EXIT_OK, result.stderr
    assert "ALLOW" in result.stdout


def test_run_subprocess_deny(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()
    result = _run_qgb_subprocess("run", "REQ-APP-001", "--path", str(project))
    assert result.returncode == EXIT_DENY
    # DENY message should mention which stage failed.
    assert "DENY" in (result.stdout + result.stderr)


# ---- QGB_KEEP_RUNS -------------------------------------------------------


def test_run_keep_runs_prunes_old_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timezone

    from qgb.core import evidence as evidence_mod

    project = _copy_generic_minimal(tmp_path)
    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"

    monkeypatch.setenv("QGB_KEEP_RUNS", "2")

    # Drive make_timestamps with a counter so each run gets a distinct
    # timestamp directory, otherwise four runs in the same wall-clock
    # second collapse into one run-dir and the prune assertion is moot.
    counter = {"i": 0}
    real_make_timestamps = evidence_mod.make_timestamps

    def fake_make_timestamps(now=None):  # noqa: ANN001 - matches signature
        counter["i"] += 1
        i = counter["i"]
        # 12:00:01 .. 12:00:04 UTC on a fixed date, sortable lexically.
        instant = datetime(2026, 1, 1, 12, 0, i, tzinfo=timezone.utc)
        return real_make_timestamps(instant)

    monkeypatch.setattr(evidence_mod, "make_timestamps", fake_make_timestamps)

    for _ in range(4):
        main(["run", "REQ-APP-001", "--path", str(project)])

    children = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    assert len(children) == 2, [c.name for c in children]


# ---- R3 / MR3: required=false is rejected by schema in Phase 1 -----------


def test_required_false_in_req_meta_is_not_ready(tmp_path: Path) -> None:
    """MR3: writing required=false in REQ meta is preflight NOT_READY.

    Phase 1's curated gate.schema.json requires every stages[] entry to
    have result=passed for ALLOW. Accepting required=false at REQ meta
    would silently mislead designers about which stages affect ALLOW,
    so req-meta.schema.json constrains required to ``const: true`` in
    Phase 1. The optional-stage semantics is a Phase 2 design surface.
    """
    project = _copy_generic_minimal(tmp_path)

    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    for stage in meta["stages"]:
        if stage["stage_id"] == "S2":
            stage["required"] = False
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


def test_required_true_in_req_meta_is_accepted(tmp_path: Path) -> None:
    """MR3: required=true (the default in Phase 1) still validates."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    for stage in meta["stages"]:
        stage["required"] = True
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    assert main(["run", "REQ-APP-001", "--path", str(project)]) == EXIT_OK


# ---- R2: same-second runs must not collide -------------------------------


def test_run_same_second_does_not_overwrite_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Three runs forced onto the same wall-clock second must keep three run-dirs.

    Step 5 三次補修: collisions are now absorbed by ``run_id`` instead of
    walking ``timestamp_utc`` forward. All three runs keep the same
    timestamp (wall-clock truth) but receive distinct run_ids r0001,
    r0002, r0003.
    """
    from datetime import datetime, timezone

    from qgb.core import evidence as evidence_mod

    project = _copy_generic_minimal(tmp_path)
    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"

    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        evidence_mod,
        "make_timestamps",
        lambda now=None: evidence_mod._timestamps_from_instant(fixed),
    )
    monkeypatch.setenv("QGB_KEEP_RUNS", "10")

    for _ in range(3):
        assert main(["run", "REQ-APP-001", "--path", str(project)]) == EXIT_OK

    children = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
    assert len(children) == 3, children
    assert children[0] == "2026-01-01T120000Z-r0001"
    assert children[1] == "2026-01-01T120000Z-r0002"
    assert children[2] == "2026-01-01T120000Z-r0003"


def test_run_reserves_run_dir_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RR1: run_dir reservation must survive a concurrent pre-claim.

    Step 5 三次補修: a process that pre-claims ``<ts>-r0001`` must not
    cause a parallel ``qgb run`` to overwrite it. The reservation walks
    forward to ``r0002`` instead.
    """
    from datetime import datetime, timezone

    from qgb.core import evidence as evidence_mod

    project = _copy_generic_minimal(tmp_path)
    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    # Pre-claim the first run_id a parallel sibling would have taken.
    (runs_dir / "2026-01-01T120000Z-r0001").mkdir()

    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        evidence_mod,
        "make_timestamps",
        lambda now=None: evidence_mod._timestamps_from_instant(fixed),
    )

    assert main(["run", "REQ-APP-001", "--path", str(project)]) == EXIT_OK

    children = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
    assert "2026-01-01T120000Z-r0001" in children
    assert "2026-01-01T120000Z-r0002" in children
    pre_claimed = runs_dir / "2026-01-01T120000Z-r0001"
    assert not list(pre_claimed.iterdir()), (
        f"pre-claimed run_dir was overwritten: {list(pre_claimed.iterdir())}"
    )


def test_run_reservation_failure_raises_when_all_slots_taken(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RR1: if every run_id slot for the second is taken, reservation must raise.

    Step 5 三次補修: silent schema-invalid gate.json is worse than a
    runtime error. Pre-claim every r0001..rffff slot for the target
    second and confirm RunDirReservationError fires.
    """
    from datetime import datetime, timezone

    from qgb.core import evidence as evidence_mod

    project = _copy_generic_minimal(tmp_path)
    runs_dir = project / ".quality-system" / "artifacts" / "REQ-APP-001" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)

    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    ts = evidence_mod._timestamps_from_instant(fixed)

    # Patch the run_id space down to two slots, then pre-claim both.
    monkeypatch.setattr(evidence_mod, "_RUN_ID_MAX", 2)
    (runs_dir / f"{ts.compact}-r0001").mkdir()
    (runs_dir / f"{ts.compact}-r0002").mkdir()

    monkeypatch.setattr(
        evidence_mod,
        "make_timestamps",
        lambda now=None: evidence_mod._timestamps_from_instant(fixed),
    )

    with pytest.raises(evidence_mod.RunDirReservationError):
        main(["run", "REQ-APP-001", "--path", str(project)])


def test_run_same_second_gate_paths_stay_in_lockstep(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """timestamp stays as wall-clock truth; run_id alone disambiguates."""
    from datetime import datetime, timezone

    from qgb.core import evidence as evidence_mod

    project = _copy_generic_minimal(tmp_path)

    fixed = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        evidence_mod,
        "make_timestamps",
        lambda now=None: evidence_mod._timestamps_from_instant(fixed),
    )

    main(["run", "REQ-APP-001", "--path", str(project)])
    main(["run", "REQ-APP-001", "--path", str(project)])

    gate = _gate(project)  # curated = latest = second run
    assert gate["timestamp_utc"] == "2026-01-01T120000Z"  # NOT advanced.
    assert gate["timestamp_rfc3339"] == "2026-01-01T12:00:00Z"
    assert gate["run_id"] == "r0002"
    assert gate["paths"]["run_dir"].endswith("2026-01-01T120000Z-r0002")


# ---- R1: contract.target must not escape project root --------------------


def test_run_target_escape_is_rejected_as_failed(tmp_path: Path) -> None:
    """A contract.target that resolves outside project_root must not be read.

    The runner records the stage as ``failed`` (not as a happy "file does
    not exist") so the resulting gate is DENY, and crucially the basis
    never claims a file outside the project as evidence (P7, NF-007).
    """
    project = _copy_generic_minimal(tmp_path)
    # Drop a file outside the project root and try to point S1 at it.
    outside = tmp_path / "outside.txt"
    outside.write_text("contains hello\n", encoding="utf-8")

    s1_path = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    s1 = _read_json(s1_path)
    s1["target"] = "../outside.txt"
    s1_path.write_text(json.dumps(s1, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY

    gate = _gate(project)
    assert gate["status"] == "DENY"
    s1_stage = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1_stage["result"] == "failed"
    # log must explain the rejection, not pretend the file is missing.
    log_text = (
        project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest" / "stages" / "S1.log"
    ).read_text(encoding="utf-8")
    assert "outside the project root" in log_text


def test_run_substring_match_target_escape_is_rejected(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("hello\n", encoding="utf-8")

    s2_path = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S2.json"
    s2 = _read_json(s2_path)
    s2["target"] = "../outside.txt"
    s2_path.write_text(json.dumps(s2, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    s2_stage = next(s for s in gate["stages"] if s["id"] == "S2")
    assert s2_stage["result"] == "failed"


def test_run_absolute_target_path_is_rejected(tmp_path: Path) -> None:
    """MR2: absolute paths are rejected even when they land under the project.

    contract.target must be project-rooted relative. Accepting an
    absolute path that happens to fall under the project would silently
    break when the project moved on disk (P9: input contracts must be
    unambiguous).
    """
    project = _copy_generic_minimal(tmp_path)
    # Sit the target somewhere *inside* the project to make sure the
    # rejection is about the path *form*, not about the destination.
    inside_abs = (project / "target" / "sample.txt").resolve()

    s1_path = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    s1 = _read_json(s1_path)
    s1["target"] = str(inside_abs)
    s1_path.write_text(json.dumps(s1, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    s1_stage = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1_stage["result"] == "failed"
    log_text = (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / "S1.log"
    ).read_text(encoding="utf-8")
    assert "absolute path" in log_text


def test_run_symlink_target_pointing_outside_is_rejected(tmp_path: Path) -> None:
    """A symlink whose ``resolve()`` lands outside the project must not be read.

    Resolving the path before the relative_to() check means that even if
    the contract.target is a project-internal path, but it's actually a
    symlink to ``/etc/passwd`` / ``..\\other``, the runner rejects it.
    This complements the textual ``..`` rejection from R1.

    On Windows, creating a symlink requires either Developer Mode or
    elevated permissions; the test skips when ``os.symlink`` is denied
    rather than failing.
    """
    import os

    project = _copy_generic_minimal(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("hello\n", encoding="utf-8")

    link_path = project / "target" / "linked.txt"
    try:
        os.symlink(outside, link_path)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation not permitted in this environment: {exc}")

    s1_path = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    s1 = _read_json(s1_path)
    s1["target"] = "target/linked.txt"
    s1_path.write_text(json.dumps(s1, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    s1_stage = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1_stage["result"] == "failed"
    log_text = (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / "S1.log"
    ).read_text(encoding="utf-8")
    assert "outside the project root" in log_text


def test_run_absolute_contract_ref_is_rejected_as_not_ready(tmp_path: Path) -> None:
    """MR2: absolute contract_ref in REQ meta is preflight NOT_READY.

    contract_ref is consumed by the loader during preflight, so an
    absolute path here cannot even be opened safely — that's a NOT_READY
    issue, not a stage failure.
    """
    project = _copy_generic_minimal(tmp_path)
    s1_abs = (
        project
        / ".quality-system"
        / "contracts"
        / "REQ-APP-001"
        / "S1.json"
    ).resolve()

    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = _read_json(meta_path)
    meta["stages"][0]["contract_ref"] = str(s1_abs)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


# ---- existing examples test must still pass ------------------------------


def test_running_does_not_break_existing_examples_test(tmp_path: Path) -> None:
    """Sanity: qgb run on a copy must not touch the in-repo example tree.

    Step 5 補修: the hand-written reference now lives under
    ``examples/generic-minimal/evidence-reference/``, separate from
    ``.quality-system/evidence/`` (which is the destination ``qgb run``
    writes to). This test asserts the reference still has its frozen
    timestamp, proving the run executed elsewhere.
    """
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--path", str(project)])

    ref_gate = _read_json(
        GENERIC_MINIMAL
        / "evidence-reference"
        / "REQ-APP-001"
        / "latest"
        / "gate.json"
    )
    assert ref_gate["timestamp_utc"] == "2026-05-21T120000Z"
    assert ref_gate["run_id"] == "r0001"
