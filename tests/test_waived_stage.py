"""Step 7 項目 D: waived 段階 + knowledge.jsonl + KNOWLEDGE-* basis.

受け入れ条件 §12-16: waived を理由つきで knowledge.jsonl に記録できる.

要件 §F-007 + §6.3.3:
- REQ meta の stage に `waived: true` / `waiver_reason` を許容
- waived 段階は判定対象から除外
- knowledge.jsonl に WAIVER エントリを記録
- gate.json の basis[] に `KNOWLEDGE-<id>` を追加

Codex 計画レビューの最重要原則:
「waived は preflight / runner / decision / basis の全層で同じ意味にする。
"実行はされないが DENY に寄与"、"basis だけ残らない" のような不整合を出さない」
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from qgb.cli import EXIT_OK, main

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


def _waive_stage(project: Path, stage_id: str, reason: str) -> None:
    """REQ meta の指定 stage を waived にする."""
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        if s["stage_id"] == stage_id:
            s["waived"] = True
            s["waiver_reason"] = reason
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---- waived 段階は実行されない / judgment 対象外 ---------------------


def test_waived_stage_does_not_block_allow(tmp_path: Path) -> None:
    """waived 段階が failed していても ALLOW を出せる.

    target を消して S1 (file_exists) が fail する状況を作り、S1 を waive。
    S2 だけで判定するので、target を hello で埋めれば S2 は pass → ALLOW。
    """
    project = _copy_generic_minimal(tmp_path)
    # S1=file_exists を waive。S2=substring_match だけが判定対象になる。
    _waive_stage(project, "S1", "Internal scaffolding; target file not required.")
    # S1 が依存している context を満たすため target はそのまま残す
    # (waived の意味論: S1 は実行されないので target が無くても fail にならない)
    (project / "target" / "sample.txt").unlink()
    # S2 を fail させたくないので、ファイルを再作成して hello を含める。
    (project / "target").mkdir(exist_ok=True)
    (project / "target" / "sample.txt").write_text("hello world\n", encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK

    gate = _gate(project)
    assert gate["status"] == "ALLOW"
    # waived stage は stages[] に "waived" 結果で残る。
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "waived"


def test_waived_stage_appears_in_basis_as_knowledge(tmp_path: Path) -> None:
    """gate.json.basis[] に KNOWLEDGE-WAIVER-<REQ>-<stage> が入る."""
    project = _copy_generic_minimal(tmp_path)
    _waive_stage(project, "S1", "Internal scaffolding")
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    gate = _gate(project)
    basis = set(gate["basis"])
    # CONTRACT-* は waived でも残す (生成された contract は実在するため)
    assert "CONTRACT-REQ-APP-001-S1" in basis
    # KNOWLEDGE-WAIVER-* で waiver の根拠を残す
    knowledge_entries = [b for b in basis if b.startswith("KNOWLEDGE-WAIVER-")]
    assert any("REQ-APP-001" in k and "S1" in k for k in knowledge_entries), basis


# ---- knowledge.jsonl への WAIVER 記録 -------------------------------


def test_waived_stage_writes_knowledge_jsonl_entry(tmp_path: Path) -> None:
    """waived stage の run で knowledge.jsonl に WAIVER エントリが書かれる."""
    project = _copy_generic_minimal(tmp_path)
    _waive_stage(project, "S1", "Internal scaffolding; target file optional.")
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"
    assert kjsonl.is_file(), "knowledge.jsonl should be created by waiver flow"

    entries = [
        json.loads(line)
        for line in kjsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    waivers = [e for e in entries if e.get("kind") == "waiver"]
    assert waivers, "expected at least one waiver entry"
    w = waivers[0]
    assert w["kind"] == "waiver"
    assert w["stage_id"] == "S1"
    assert w["reason"] == "Internal scaffolding; target file optional."
    assert w["applies_to"] == "REQ-APP-001"
    assert "decided_by" in w
    assert "created_at" in w


def test_waiver_entry_is_idempotent_across_runs(tmp_path: Path) -> None:
    """同じ waiver は run を複数回しても重複 append されない."""
    project = _copy_generic_minimal(tmp_path)
    _waive_stage(project, "S1", "Internal scaffolding")
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    for _ in range(3):
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    kjsonl = project / ".quality-system" / "knowledge" / "knowledge.jsonl"
    entries = [
        json.loads(line)
        for line in kjsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    waivers = [
        e for e in entries
        if e.get("kind") == "waiver"
        and e.get("applies_to") == "REQ-APP-001"
        and e.get("stage_id") == "S1"
    ]
    assert len(waivers) == 1, f"expected idempotent, got {len(waivers)}"


# ---- runner 側: waived は実行されない --------------------------------


def test_waived_stage_log_indicates_skip(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _waive_stage(project, "S1", "Internal scaffolding")
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    log = (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / "S1.log"
    ).read_text(encoding="utf-8")
    # waived の事実と理由が log にも記録される。
    assert "waived" in log.lower()
    assert "Internal scaffolding" in log


# ---- decision: 全 stage waived の REQ は ALLOW を出せない ------------


def test_all_stages_waived_req_is_not_allow(tmp_path: Path) -> None:
    """全 stage waived の REQ は判定材料ゼロなので ALLOW にはならない.

    Phase 1 では「判定対象が空 = NOT_READY または DENY」が望ましい。
    ここでは「ALLOW でないこと」だけを担保 (Step 8 以降の P5 に従う)。
    """
    project = _copy_generic_minimal(tmp_path)
    _waive_stage(project, "S1", "all waived test")
    _waive_stage(project, "S2", "all waived test")

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # ALLOW (=0) ではないことだけ担保。
    assert exit_code != EXIT_OK


# ---- schema: waived: true で waiver_reason 必須 ---------------------


def test_waived_without_reason_is_preflight_not_ready(tmp_path: Path) -> None:
    """waived: true なのに waiver_reason 不在 → preflight NOT_READY (schema)."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        if s["stage_id"] == "S1":
            s["waived"] = True
            # waiver_reason は付けない。
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # NOT_READY (schema_violation で弾かれる)
    from qgb.cli import EXIT_NOT_READY
    assert exit_code == EXIT_NOT_READY
