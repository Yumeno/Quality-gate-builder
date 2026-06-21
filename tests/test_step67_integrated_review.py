"""Step 6+7 統合レビュー補修テスト.

memory review-process 段 4 の補修 (Codex 横断 + 観点別 5 subagent
の集約 finding):

- A6: adopted vs results の cardinality 完全性 (silent skip 禁止)
- A7: decide() の postcondition assert
- A2: gate.json path serialization は POSIX `/` 固定
- A5: design_stages._load_template_stages の shape 防御
- A3: Python adapter の .PY 大文字対応
- A9: summary.md の all-waived DENY 文言分岐
- A10: gate.json.decision.meaning に "this project's policy" 注
- A13: cli.py の --phase help が Step 7 後の状態を反映
- A11: design_stages.py の lazy import を top-level に
- A12: python.py の _Signals.evidence 型嘘修正
- A4/A8: docstring の Phase 2 out-of-scope 明示 (テスト不要)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from qgb.cli import EXIT_DENY, main

REPO_ROOT = Path(__file__).resolve().parents[1]
GENERIC_MINIMAL = REPO_ROOT / "examples" / "generic-minimal"


def _copy_generic_minimal(dest: Path) -> Path:
    target = dest / "generic-minimal"
    shutil.copytree(
        GENERIC_MINIMAL,
        target,
        ignore=shutil.ignore_patterns("artifacts", "evidence"),
    )
    (target / ".quality-system" / "artifacts").mkdir(exist_ok=True)
    return target


def _gate(project: Path) -> dict:
    return json.loads(
        (
            project
            / ".quality-system"
            / "evidence"
            / "REQ-APP-001"
            / "latest"
            / "gate.json"
        ).read_text(encoding="utf-8")
    )


# ---- A6: cardinality invariant ----------------------------------------


def test_gate_stages_match_adopted_one_to_one(tmp_path: Path) -> None:
    """adopted で実行された stage は必ず gate.json#stages に出る."""
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    # generic-minimal は 2 stages (S1, S2)
    assert len(gate["stages"]) == 2
    ids = [s["id"] for s in gate["stages"]]
    assert ids == ["S1", "S2"]


def test_missing_result_synthesises_failed_entry(tmp_path: Path) -> None:
    """Codex A6: results に欠落があれば synthetic missing result を埋める.

    実装側で「silent skip しない」契約を担保する。run_stages の戻り値が
    adopted より少ない場合でも、gate.json は adopted と同じ stage 数を持ち、
    欠落は failed として明示される。
    """
    from qgb.core.decision import Decision
    from qgb.core.evidence import Timestamps, build_gate_document
    from qgb.core.preflight import AdoptedStage
    from qgb.core.runner import StageResult

    adopted = [
        AdoptedStage(
            stage_id="S1",
            name="present",
            verification_type="file_exists",
            depends_on=(),
            contract_ref=".quality-system/contracts/REQ-X-001/S1.json",
            contract={},
            required=True,
        ),
        AdoptedStage(
            stage_id="S2",
            name="missing in results",
            verification_type="file_exists",
            depends_on=(),
            contract_ref=".quality-system/contracts/REQ-X-001/S2.json",
            contract={},
            required=True,
        ),
    ]
    results = [
        StageResult(
            stage_id="S1", name="present",
            verification_type="file_exists",
            contract_ref=adopted[0].contract_ref,
            result="passed", exit_code=None,
            log_text="ok\n",
        )
    ]
    decision = Decision(status="DENY", failed_stage="S2", meaning="...")
    ts = Timestamps(compact="2026-01-01T000000Z", rfc3339="2026-01-01T00:00:00Z")
    gate = build_gate_document(
        req_id="REQ-X-001",
        phase="verify",
        timestamps=ts,
        run_id="r0001",
        decision=decision,
        adopted=adopted,
        results=results,
        basis=["REQ-X-001"],
        run_dir_rel=".quality-system/artifacts/REQ-X-001/runs/x",
        curated_latest_rel=".quality-system/evidence/REQ-X-001/latest",
    )
    # adopted の 2 stages すべて gate.json#stages に出る (S2 が missing で
    # synthesised される)。
    assert len(gate["stages"]) == 2
    s2 = next(s for s in gate["stages"] if s["id"] == "S2")
    assert s2["result"] == "failed"


# ---- A7: decide postcondition -----------------------------------------


def test_decide_allow_requires_judgement_passed_positive(tmp_path: Path) -> None:
    """decide() は judgement_passed=0 で ALLOW を返さない (defensive).

    現状の実装は all-waived のとき DENY を返すが、もし将来の改修で
    誤って status=ALLOW + judgement_passed=0 を組んでも、postcondition
    assert で検知される。
    """
    from qgb.core.decision import decide
    # 空 adopted + 空 results は status=DENY を返すべき (judgement なし)。
    decision = decide([], [], "verify")
    # ALLOW にはならない (judgement_passed=0)。
    assert decision.status == "DENY"


# ---- A2: POSIX forward-slash path serialization ----------------------


def test_gate_json_paths_use_forward_slashes(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    # paths.run_dir / paths.curated_latest_dir / stages[].log_ref は
    # すべて POSIX `/`。
    assert "\\" not in gate["paths"]["run_dir"], gate["paths"]["run_dir"]
    assert "\\" not in gate["paths"]["curated_latest_dir"]
    for s in gate["stages"]:
        assert "\\" not in s["log_ref"], s["log_ref"]


# ---- A5: template shape validation -----------------------------------


def test_load_template_stages_rejects_malformed_template(tmp_path: Path) -> None:
    """壊れた template policy.json は KeyError でなく明示的エラー."""
    # 壊れた template を _TEMPLATES_DIR を monkeypatch して差し込む。
    import qgb.core.design_stages as ds
    from qgb.core.design_stages import _load_template_stages

    fake_root = tmp_path / "fake-template" / ".quality-system"
    fake_root.mkdir(parents=True)
    (fake_root / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": [{"name": "missing-id"}],  # id 欠落
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    import pytest as _pytest

    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(ds, "_TEMPLATES_DIR", tmp_path)
    try:
        with _pytest.raises(ValueError, match="(?i)stage|id|missing"):
            _load_template_stages("fake-template")
    finally:
        monkeypatch.undo()


# ---- A3: .PY case-insensitive matching ------------------------------
# Phase 3 Step 3.0 で adapter / detect 一式が撤去されたため本テストは削除。
# 元テストは PythonAdapter が Windows 大文字小文字非依存 FS で .PY を
# 認識することの確認だったが、対象プロジェクトの言語判定は Phase 5 スキル
# (LLM) の責務に統合されたため adapter 自体が不要になった。


# ---- A9: summary.md all-waived wording -------------------------------


def test_summary_md_all_waived_uses_no_judgement_wording(tmp_path: Path) -> None:
    """all-waived DENY のときの summary.md は "stage failed" を匂わせない."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        s["waived"] = True
        s["waiver_reason"] = "all waived"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    summary = (
        project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest" / "summary.md"
    ).read_text(encoding="utf-8")
    # "stage `` が failed" のような空 failed_stage 漏れがない。
    assert "`` が failed" not in summary
    # 「判定対象がない」「no judgement material」のような文脈が含まれる。
    summary_lower = summary.lower()
    assert (
        ("判定対象" in summary)
        or ("judgement" in summary_lower)
        or ("material" in summary_lower)
    )


# ---- A10: decision.meaning に "this project" 注 ---------------------


def test_decision_meaning_includes_project_scope_in_allow(tmp_path: Path) -> None:
    """gate.json.decision に project-local 性が明記される.

    RA2 補修後: meaning は F-016 verbatim、scope は別 field に分離。
    本テストは A10 の意図 (P11 注を gate.json に残す) を decision.scope
    経由で担保する。verbatim 一致と project-local 性の両立を、
    test_decision_meaning_stays_verbatim と
    test_decision_scope_carries_p11_note の合算でロックしている。
    """
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    scope = gate["decision"]["scope"].lower()
    assert ("project" in scope) or ("policy" in scope) or ("p11" in scope)


# ---- A13: --phase help は Step 7 状態 --------------------------------


# ---- RA1: synthetic missing provenance --------------------------------


def test_synthetic_missing_result_carries_provenance(tmp_path: Path) -> None:
    """Codex RA1: synthetic failed entry は通常 failure と区別される.

    auditor が「runner が result を落とした」と「stage が legitimate に
    failed した」を区別できる必要がある。``synthetic: true`` と
    ``synthetic_reason`` で見分けが付く。
    """
    from qgb.core.decision import Decision
    from qgb.core.evidence import Timestamps, build_gate_document
    from qgb.core.preflight import AdoptedStage

    adopted = [
        AdoptedStage(
            stage_id="S1",
            name="missing in results",
            verification_type="file_exists",
            depends_on=(),
            contract_ref=".quality-system/contracts/REQ-X-001/S1.json",
            contract={},
            required=True,
        ),
    ]
    decision = Decision(status="DENY", failed_stage="S1", meaning="...")
    ts = Timestamps(
        compact="2026-01-01T000000Z", rfc3339="2026-01-01T00:00:00Z"
    )
    gate = build_gate_document(
        req_id="REQ-X-001",
        phase="verify",
        timestamps=ts,
        run_id="r0001",
        decision=decision,
        adopted=adopted,
        results=[],  # 空 results
        basis=["REQ-X-001"],
        run_dir_rel=".quality-system/artifacts/REQ-X-001/runs/x",
        curated_latest_rel=".quality-system/evidence/REQ-X-001/latest",
    )
    s1 = gate["stages"][0]
    assert s1["result"] == "failed"
    assert s1["synthetic"] is True
    assert s1["synthetic_reason"] == "missing_result_for_adopted_stage"


def test_normal_failed_entry_has_no_synthetic_marker(tmp_path: Path) -> None:
    """通常の failed entry は synthetic マーカーを持たない (誤分類を防ぐ)."""
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    failed_stage = next(s for s in gate["stages"] if s["result"] == "failed")
    assert "synthetic" not in failed_stage, failed_stage


# ---- RA2: decision.scope を別 field に分離 --------------------------


def test_decision_meaning_stays_verbatim(tmp_path: Path) -> None:
    """RA2: decision.meaning は F-016 表の verbatim 文字列に戻る."""
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    # verify + ALLOW = "Defined checks passed. This is not proof of total correctness."
    # 完全一致 (verbatim 制約)
    assert gate["decision"]["meaning"] == (
        "Defined checks passed. This is not proof of total correctness."
    )


def test_decision_scope_carries_p11_note(tmp_path: Path) -> None:
    """RA2: project-local 注は decision.scope に分離される."""
    project = _copy_generic_minimal(tmp_path)
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    gate = _gate(project)
    scope = gate["decision"]["scope"].lower()
    # "project" / "policy" / "P11" のいずれかが入る
    assert (
        ("project" in scope) or ("policy" in scope) or ("p11" in scope)
    ), gate["decision"]["scope"]


# ---- A13 ---------------------------------------------------------------


def test_run_phase_help_does_not_claim_verify_only(tmp_path: Path) -> None:
    """`qgb run --help` の --phase 説明が "Phase 1 wires only 'verify'" を
    含まないことを担保 (Step 7 で red も実装された)."""
    import io

    captured = io.StringIO()
    real_stdout = sys.stdout
    sys.stdout = captured
    try:
        try:
            main(["run", "--help"])
        except SystemExit:
            pass
    finally:
        sys.stdout = real_stdout
    out = captured.getvalue()
    assert "wires only 'verify'" not in out, out
