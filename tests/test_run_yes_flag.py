"""Step 6b 項目 1: ``qgb run`` の実行前確認プロンプトと ``--yes`` フラグ.

要件 §F-008 (要件§448):
    qgb run は実行前に確認プロンプトを出す (--yes でスキップ可)。

設計:

* 既定 (TTY 接続時): プロンプトを出す。``y`` / ``yes`` のみ続行、それ以外は
  abort して EXIT_NOT_READY を返す。run は始まっていないので curated
  evidence は書き換えない。
* ``--yes`` フラグ: プロンプトを完全にスキップして実行。
* 非 TTY (CI / リダイレクト / パイプ): プロンプトしても応答できないので、
  ``--yes`` 未指定なら abort して、CI 用に ``--yes`` を付けるよう促す。

プロンプトの宛先は stderr (stdout は ``--json`` の出力経路)。
"""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

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


# ---- --yes: prompt skipped ------------------------------------------------


def test_run_with_yes_flag_skips_prompt_and_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--yes`` は確認プロンプトを完全にスキップして本来の判定を返す。"""
    project = _copy_generic_minimal(tmp_path)

    # stdin/stdout が TTY か否かに関わらず --yes ならプロンプトを出さない。
    # input() が呼ばれていたら EOFError でテストが落ちる。
    monkeypatch.setattr("sys.stdin", io.StringIO(""))

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK


def test_run_with_yes_flag_in_deny_path(tmp_path: Path) -> None:
    """``--yes`` は DENY パスでも従来通り EXIT_DENY を返す。"""
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


# ---- TTY: prompt accepted -------------------------------------------------


def test_run_prompt_accepted_with_y(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """TTY 想定で stdin に 'y' を流し込めばプロンプトを通過する。"""
    project = _copy_generic_minimal(tmp_path)

    monkeypatch.setattr("sys.stdin", io.StringIO("y\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_OK

    captured = capsys.readouterr()
    # プロンプトは stderr に出る (stdout は JSON 用に空けておく)。
    assert "REQ-APP-001" in captured.err
    assert "proceed" in captured.err.lower() or "実行" in captured.err


def test_run_prompt_accepted_with_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_generic_minimal(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    assert (
        main(["run", "REQ-APP-001", "--path", str(project)]) == EXIT_OK
    )


# ---- TTY: prompt declined -------------------------------------------------


def test_run_prompt_declined_aborts_without_writing_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """プロンプトを却下すると NOT_READY で止まり、curated evidence は触らない。"""
    project = _copy_generic_minimal(tmp_path)

    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY

    # 中断したので curated evidence は作られない。
    curated_gate = (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "gate.json"
    )
    assert not curated_gate.exists()

    captured = capsys.readouterr()
    assert (
        "aborted" in captured.err.lower()
        or "中断" in captured.err
        or "cancel" in captured.err.lower()
    )


def test_run_prompt_empty_input_declines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空入力 (Enter のみ) は安全側に倒して NOT_READY。

    ``y`` / ``yes`` のみが続行条件で、それ以外は全て abort。
    """
    project = _copy_generic_minimal(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    assert (
        main(["run", "REQ-APP-001", "--path", str(project)])
        == EXIT_NOT_READY
    )


# ---- Non-TTY: abort without --yes -----------------------------------------


def test_run_non_tty_without_yes_aborts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """非 TTY で --yes 未指定なら明示的に止まる。CI で気付かず走るのを防ぐ。"""
    project = _copy_generic_minimal(tmp_path)

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY

    captured = capsys.readouterr()
    # --yes を促すヒントが出る。
    assert "--yes" in captured.err


def test_run_non_tty_with_yes_executes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _copy_generic_minimal(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    assert (
        main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    )


# ---- preflight failure beats prompt --------------------------------------


def test_run_preflight_not_ready_bypasses_prompt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """preflight が NOT_READY を返す場合、プロンプトを出さずに即座に止まる。

    実行候補が成立していない時点で確認の意味がない。``input()`` を呼ぼうと
    していたら EOFError で落ちるはずなので、これが通れば「preflight 失敗時は
    プロンプトを通っていない」ことが担保される。
    """
    project = _copy_generic_minimal(tmp_path)
    # contract_ref が指す S1.json を消して preflight 失敗にする。
    (project / ".quality-system" / "contracts" / "REQ-APP-001" / "S1.json").unlink()

    # stdin は空。プロンプトを出していたら input() が EOFError で落ちる。
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    exit_code = main(["run", "REQ-APP-001", "--path", str(project)])
    assert exit_code == EXIT_NOT_READY


# ---- JSON output unaffected ----------------------------------------------


def test_run_json_output_with_yes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--yes --json`` の組み合わせで stdout は純粋な JSON のまま。"""
    project = _copy_generic_minimal(tmp_path)

    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--json", "--path", str(project)]
    )
    assert exit_code == EXIT_OK

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "ALLOW"


def test_run_json_abort_emits_json_on_decline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Codex 補修 1 (medium): ``--json`` 指定時の abort も JSON で stdout に出す。

    preflight NOT_READY が JSON で出るのと同じ契約に揃える。"abort by user" も
    "abort because non-TTY without --yes" も run コマンドが返す合法な
    NOT_READY 経路。stderr のみで stdout 空、は JSON 消費側にとって紛らわしい。
    """
    project = _copy_generic_minimal(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO("n\n"))
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)

    exit_code = main(
        ["run", "REQ-APP-001", "--json", "--path", str(project)]
    )
    assert exit_code == EXIT_NOT_READY

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["ok"] is False
    assert parsed["status"] == "NOT_READY"
    assert parsed["req_id"] == "REQ-APP-001"
    # abort の理由が機械可読に取れる。
    assert parsed.get("reason") in ("declined", "non_tty_without_yes")


def test_run_json_abort_emits_json_on_non_tty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """非 TTY abort も同様に JSON。"""
    project = _copy_generic_minimal(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)

    exit_code = main(
        ["run", "REQ-APP-001", "--json", "--path", str(project)]
    )
    assert exit_code == EXIT_NOT_READY

    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["status"] == "NOT_READY"
    assert parsed["reason"] == "non_tty_without_yes"
