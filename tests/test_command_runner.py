"""Step 7 項目 B: command verification_type 実装.

設計 (Codex 計画レビュー):
- shell=False, argv 配列のみ
- env = os.environ.copy() (Phase 1 はフル継承、hardening は Phase 2)
- stdin = DEVNULL
- stdout / stderr capture、各 64 KiB cap、末尾優先で残す
- working_dir は project root 配下に閉じ込め (R1 と同じガード)
- timeout は failed として扱う
- expected_exit_code (default 0) と一致したら passed、不一致は failed
- command が見つからない (FileNotFoundError) は failed として扱う (crash しない)
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from qgb.cli import EXIT_DENY, EXIT_NOT_READY, EXIT_OK, main

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


def _inject_command_stage(
    project: Path,
    *,
    command: list[str],
    expected_exit_code: int = 0,
    timeout_seconds: int | None = None,
    working_dir: str | None = None,
) -> None:
    """Replace S1 with a command verification_type stage."""
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    policy["stages"][0] = {
        "id": "S1",
        "name": "command runs",
        "responsibility": "executes a declared command",
        "depends_on": [],
        "verification_type": "command",
        "required_contract_fields": ["command"],
    }
    # S2 (substring_match) は file_exists 系の depends_on があるので、
    # S2 も独立にして command 単体で判定できるようにする。
    policy["stages"] = [policy["stages"][0]]
    pp.write_text(
        json.dumps(policy, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # REQ meta を S1 のみに。
    meta_path = project / ".quality-system" / "req" / "REQ-APP-001.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["stages"] = [meta["stages"][0]]
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # S1 contract を command 用に書き換える。
    contracts_dir = project / ".quality-system" / "contracts" / "REQ-APP-001"
    # 不要な S2 contract は残しても (preflight は採用されない stage_id は無視)。
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
    if working_dir is not None:
        contract["working_dir"] = working_dir
    (contracts_dir / "S1.json").write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )


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


def _stage_log(project: Path, stage_id: str) -> str:
    return (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / f"{stage_id}.log"
    ).read_text(encoding="utf-8")


# ---- happy path ---------------------------------------------------------


def test_command_zero_exit_passes(tmp_path: Path) -> None:
    """python -c 'pass' は exit 0、expected_exit_code=0 で passed."""
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(project, command=[sys.executable, "-c", "pass"])
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    gate = _gate(project)
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "passed"
    assert s1["exit_code"] == 0


def test_command_nonzero_exit_fails_by_default(tmp_path: Path) -> None:
    """python -c 'import sys; sys.exit(3)' は default expected=0 と不一致 → DENY."""
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project, command=[sys.executable, "-c", "import sys; sys.exit(3)"]
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "failed"
    assert s1["exit_code"] == 3


def test_command_matches_expected_nonzero(tmp_path: Path) -> None:
    """expected_exit_code=2 のとき exit 2 は passed."""
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project,
        command=[sys.executable, "-c", "import sys; sys.exit(2)"],
        expected_exit_code=2,
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK


# ---- safety: shell=False, argv only -----------------------------------


def test_command_does_not_invoke_shell(tmp_path: Path) -> None:
    """shell metacharacter は literal として扱われる (shell=False 担保)."""
    project = _copy_generic_minimal(tmp_path)
    # ';' を shell が解釈するとここで exit 0 になってしまう。
    # 我々は argv[0] を literally exec するので、ENOENT で failed になる。
    _inject_command_stage(project, command=["nosuchcmd ; true"])
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    # log に "shell" や "true" などの shell 解釈痕跡が出ないことは検証しにくいので、
    # 「実行できなかった」ことが残るかを確認。
    assert "result: failed" in log


# ---- working_dir within project ---------------------------------------


def test_command_working_dir_resolved_under_project(tmp_path: Path) -> None:
    """working_dir に project-root 相対 path を渡すと cwd になる."""
    project = _copy_generic_minimal(tmp_path)
    # target/ の中身を ls させ、stdout が記録される。
    _inject_command_stage(
        project,
        command=[sys.executable, "-c", "import os; print(os.getcwd())"],
        working_dir="target",
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    assert (project / "target").name in log  # "target" がログに出る


def test_command_working_dir_escape_is_rejected(tmp_path: Path) -> None:
    """working_dir で project root を escape させない (R1)."""
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project,
        command=[sys.executable, "-c", "pass"],
        working_dir="../escape-attempt",
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "outside the project root" in log


# ---- timeout -----------------------------------------------------------


def test_command_timeout_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project,
        command=[sys.executable, "-c", "import time; time.sleep(5)"],
        timeout_seconds=1,
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "timeout" in log.lower()


# ---- output capture + cap ---------------------------------------------


def test_command_stdout_captured_in_log(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project,
        command=[sys.executable, "-c", "print('hello-from-runner')"],
    )
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    log = _stage_log(project, "S1")
    assert "hello-from-runner" in log


def test_command_stderr_captured_in_log(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(
        project,
        command=[
            sys.executable,
            "-c",
            "import sys; print('on-stderr-channel', file=sys.stderr)",
        ],
    )
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    log = _stage_log(project, "S1")
    assert "on-stderr-channel" in log


def test_command_long_stdout_is_capped(tmp_path: Path) -> None:
    """64 KiB cap。末尾優先 (failure traceback が末尾に出ることが多い)."""
    project = _copy_generic_minimal(tmp_path)
    # 100 KiB の文字列を吐く。
    _inject_command_stage(
        project,
        command=[
            sys.executable,
            "-c",
            "import sys; sys.stdout.write('X' * (100*1024))",
        ],
    )
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    log = _stage_log(project, "S1")
    # log は capped されている。stdout 全文 100KB は入っていない。
    assert len(log) < 200 * 1024  # log には他の行も含むが上限を圧倒的に下回る
    # truncated indicator
    assert "truncated" in log.lower()


# ---- command not found -----------------------------------------------


def test_command_not_found_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(project, command=["nosuchcommand-qgb-test"])
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "result: failed" in log
    # No traceback — graceful failure.


# ---- preflight: command verification_type は Step 7 で sup されている ----


def test_command_no_longer_unsupported_in_run(tmp_path: Path) -> None:
    """Step 6 までは preflight が unsupported_verification_type で弾いていた。
    Step 7 で command が runtime support に加わる。
    """
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(project, command=[sys.executable, "-c", "pass"])
    # NOT_READY ではなく実行される。
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code != EXIT_NOT_READY


# ---- contract.command validation -------------------------------------


def test_command_with_empty_argv_is_failed(tmp_path: Path) -> None:
    """command=[] は schema で minItems=1 違反なので preflight でも弾かれる."""
    project = _copy_generic_minimal(tmp_path)
    _inject_command_stage(project, command=["dummy"])
    # contract を後から壊す。
    cp = project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json"
    c = json.loads(cp.read_text(encoding="utf-8"))
    c["command"] = []
    cp.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # qgb validate は schema 違反を弾くが、 qgb run の preflight には
    # 「contract が schema を満たしているか」のフルチェックは入っていない
    # (validate との責務分離)。runner 側で「argv が空」を failed として扱う。
    assert exit_code in (EXIT_DENY, EXIT_NOT_READY)
