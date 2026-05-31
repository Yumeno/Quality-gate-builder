"""Step 7 Codex 横断レビュー補修テスト.

Codex 指摘 (中以上):
- 2: timeout 時の TimeoutExpired.stdout/stderr が bytes でも落ちない
- 3: 非 UTF-8 出力で runner が落ちない
- 4: knowledge.jsonl 末尾が newline なしの partial line でも新規 waiver が破壊されない
- 5: all-waived DENY で failed_stage が空文字列になる
- 6: waived stage に依存する unwaived stage は satisfied 扱い
- 7: contract.timeout_seconds / expected_exit_code の型違反を runner が拒否
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from qgb.cli import EXIT_DENY, EXIT_OK, main

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


def _replace_with_command_contract(
    project: Path,
    *,
    command: list,
    expected_exit_code=0,
    timeout_seconds=None,
) -> None:
    """policy / req meta / contract を single command stage に書き換える."""
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    policy["stages"] = [
        {
            "id": "S1",
            "name": "command runs",
            "responsibility": "executes a declared command",
            "depends_on": [],
            "verification_type": "command",
            "required_contract_fields": ["command"],
        }
    ]
    pp.write_text(json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8")

    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = [meta["stages"][0]]
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    contracts_dir = project / ".quality-system" / "contracts" / "REQ-APP-001"
    contract: dict = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "command",
        "command": command,
        "expected_exit_code": expected_exit_code,
    }
    if timeout_seconds is not None:
        contract["timeout_seconds"] = timeout_seconds
    (contracts_dir / "S1.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---- 補修 2: timeout 時に bytes/str どちらでも落ちない ---------------


def test_timeout_with_some_stdout_does_not_crash(tmp_path: Path) -> None:
    """timeout 直前に少しだけ stdout を出すコマンドでも runner は failed で済む."""
    project = _copy_generic_minimal(tmp_path)
    code = (
        "import sys, time;"
        " sys.stdout.write('partial output');"
        " sys.stdout.flush();"
        " time.sleep(5)"
    )
    _replace_with_command_contract(
        project, command=[sys.executable, "-c", code], timeout_seconds=1
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY  # runner が AttributeError を投げず failed として記録
    gate = _gate(project)
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "failed"


# ---- 補修 3: 非 UTF-8 出力で runner が落ちない -----------------------


def test_non_utf8_stdout_does_not_crash(tmp_path: Path) -> None:
    """Latin-1 のような任意 bytes を stdout に流しても runner は failed/passed を返す."""
    project = _copy_generic_minimal(tmp_path)
    # 0xff を含むバイト列を stdout に書く Python スニペット (UTF-8 では invalid)。
    code = (
        "import sys;"
        " sys.stdout.buffer.write(b'hello\\xff\\xfe-bytes\\n');"
        " sys.stdout.buffer.flush()"
    )
    _replace_with_command_contract(project, command=[sys.executable, "-c", code])
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # crash しなければ OK (UnicodeDecodeError が漏れない)。passed が成立。
    assert exit_code == EXIT_OK


# ---- 補修 4: knowledge.jsonl の partial 末尾でも新規 waiver は健全 ----


def test_knowledge_jsonl_partial_tail_does_not_corrupt_new_entry(tmp_path: Path) -> None:
    """末尾が newline で終わっていない partial line があっても新規 waiver は健全に append."""
    project = _copy_generic_minimal(tmp_path)
    # S1 を waive。
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        if s["stage_id"] == "S1":
            s["waived"] = True
            s["waiver_reason"] = "test waiver"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    # knowledge.jsonl を partial で初期化 (末尾改行なし)。
    kdir = project / ".quality-system" / "knowledge"
    kdir.mkdir(parents=True, exist_ok=True)
    kjsonl = kdir / "knowledge.jsonl"
    kjsonl.write_text(
        '{"id":"DUMMY-001","kind":"user_instruction","title":"x","source_type":"user",'
        '"created_at":"2026-01-01T00:00:00Z"}\n'
        '{"id":"PARTIAL-002","kind":"user_instr',  # 末尾が壊れていて newline なし
        encoding="utf-8",
    )

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])

    # 新規 waiver が独立した行として読める。
    text = kjsonl.read_text(encoding="utf-8")
    # 全行を試しに parse して、waiver エントリがあることを確認。
    parseable_waivers = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("kind") == "waiver":
            parseable_waivers.append(entry)
    assert parseable_waivers, "new waiver must be a valid standalone JSON line"
    assert parseable_waivers[0]["applies_to"] == "REQ-APP-001"
    assert parseable_waivers[0]["stage_id"] == "S1"


# ---- 補修 5: all-waived の failed_stage は空文字列 ----------------------


def test_all_waived_req_has_empty_failed_stage(tmp_path: Path) -> None:
    """全 stage waived の DENY は failed_stage が空文字列 (waived は判定材料でない)."""
    project = _copy_generic_minimal(tmp_path)
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        s["waived"] = True
        s["waiver_reason"] = "all waived"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # run は実行されるが decision で DENY (judgement material 不在)。
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # 注意: gate.schema.json は DENY のとき failed_stage を minLength: 1 で要求している。
    # 補修方針として「all-waived は ALLOW でも DENY でもなく、preflight 段階で
    # NOT_READY とする」が schema 整合的。本テストは挙動が NOT_READY であるか、
    # それとも DENY + failed_stage="" + schema 緩和 を採用するかを Step 7 補修で
    # 決定するための入口。ここでは Codex 推奨どおり failed_stage="" にする方針で
    # 進める (decision.py を緩和、schema 側も同時に緩和)。
    from qgb.cli import EXIT_NOT_READY
    assert exit_code in (EXIT_DENY, EXIT_NOT_READY)
    # gate が生成されている場合のみ確認 (NOT_READY ルートでは生成されない)。
    gate_path = (
        project / ".quality-system" / "evidence" / "REQ-APP-001" / "latest" / "gate.json"
    )
    if gate_path.is_file():
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        # all-waived のときは failed_stage が waived stage を指してはならない。
        if gate["status"] == "DENY":
            assert gate["failed_stage"] == "", gate


# ---- 補修 6: waived stage に依存する unwaived stage は satisfied dep ---


def test_unwaived_stage_with_waived_dep_runs_normally(tmp_path: Path) -> None:
    """waived stage は satisfied dependency として扱う (実行されないが下流を妨げない)."""
    project = _copy_generic_minimal(tmp_path)
    # S1 を waive (S2 は S1 に depends_on)。S2 は実行されて pass する想定。
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for s in meta["stages"]:
        if s["stage_id"] == "S1":
            s["waived"] = True
            s["waiver_reason"] = "waiver propagation test"
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # S2 の target を pass する状態に。
    (project / "target" / "sample.txt").write_text("hello\n", encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK  # S2 が waived dep ([S1]) でも pass する
    gate = _gate(project)
    s2 = next(s for s in gate["stages"] if s["id"] == "S2")
    assert s2["result"] == "passed"  # waived dep is treated as satisfied


# ---- 補修 7: contract type validation ---------------------------------


def test_command_with_string_timeout_is_failed(tmp_path: Path) -> None:
    """timeout_seconds="60" (string) を runner が拒否. crash しない."""
    project = _copy_generic_minimal(tmp_path)
    _replace_with_command_contract(
        project,
        command=[sys.executable, "-c", "pass"],
        timeout_seconds="60",  # 文字列 - schema は弾かない場合もあるが runner で拒否
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # NOT_READY (schema が type:integer を要求) または DENY (runner 拒否) のいずれか。
    from qgb.cli import EXIT_NOT_READY
    assert exit_code in (EXIT_DENY, EXIT_NOT_READY)


def test_command_with_negative_timeout_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _replace_with_command_contract(
        project, command=[sys.executable, "-c", "pass"], timeout_seconds=-1
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    from qgb.cli import EXIT_NOT_READY
    assert exit_code in (EXIT_DENY, EXIT_NOT_READY)
