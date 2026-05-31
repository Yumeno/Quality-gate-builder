"""Step 7 項目 A: TDD phase=red の expected-failure 本実装.

Phase 1 受け入れ条件 14: phase: red の DENY を期待結果として証跡化できる.

F-016 (TDD サイクル対応) の decision.meaning テンプレート:

| phase    | result | meaning |
|----------|--------|---------|
| red      | DENY   | The required test fails as expected before implementation. |
| green    | ALLOW  | Required checks passed against the freshly implemented code. |
| refactor | ALLOW  | Required checks remained passing after refactor. |
| verify   | ALLOW  | Defined checks passed. This is not proof of total correctness. |
| verify   | DENY   | Defined checks did not pass. This is not a failure but a signal to revise. |

Codex 計画レビュー方針:
- phase=red + DENY: exit 1、meaning は "expected failure" 文言
- phase=red + ALLOW: exit 0、ただし unexpected_pass を annotation で残す
- phase=green/refactor + DENY: 通常 failure 扱い (verify と同じ exit 1)
- exit code と gate status は乖離させない (CI の自動化を読みやすくする)
"""

from __future__ import annotations

import json
import shutil
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


# ---- phase=red + DENY: expected failure -------------------------------


def test_phase_red_deny_uses_expected_failure_meaning(tmp_path: Path) -> None:
    """phase=red で DENY のとき meaning は "expected" 文言になる."""
    project = _copy_generic_minimal(tmp_path)
    # target を消して DENY 状況を作る。
    (project / "target" / "sample.txt").unlink()

    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "red", "--path", str(project)]
    )
    assert exit_code == EXIT_DENY  # exit code は DENY と一致 (gate status と乖離させない)
    gate = _gate(project)
    assert gate["phase"] == "red"
    assert gate["status"] == "DENY"
    meaning = gate["decision"]["meaning"].lower()
    assert "expected" in meaning, gate["decision"]["meaning"]


def test_phase_red_allow_uses_unexpected_pass_meaning(tmp_path: Path) -> None:
    """phase=red で ALLOW (= 期待外の成功) は exit 0 だが annotation を残す.

    TDD の red ステップで実装前に通ってしまった = テストが書けていない、
    可能性が高い。"unexpected" の signal を gate.meaning に残す。
    """
    project = _copy_generic_minimal(tmp_path)
    # target は残しておく → 全 stage passed → ALLOW

    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "red", "--path", str(project)]
    )
    assert exit_code == EXIT_OK
    gate = _gate(project)
    assert gate["phase"] == "red"
    assert gate["status"] == "ALLOW"
    meaning = gate["decision"]["meaning"].lower()
    assert "unexpected" in meaning, gate["decision"]["meaning"]


# ---- phase=verify (既定): 既存の挙動 ---------------------------------


def test_phase_verify_allow_meaning_unchanged(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--path", str(project)]
    )
    assert exit_code == EXIT_OK
    gate = _gate(project)
    assert gate["phase"] == "verify"
    meaning = gate["decision"]["meaning"].lower()
    assert "defined checks passed" in meaning


def test_phase_verify_deny_meaning_is_revision_signal(tmp_path: Path) -> None:
    """phase=verify の DENY は "revision signal" 文言 (F-016 表)."""
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "verify", "--path", str(project)]
    )
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    meaning = gate["decision"]["meaning"].lower()
    # "signal" / "revise" のいずれかが入る (spec 表通り)
    assert ("signal" in meaning) or ("revise" in meaning), gate["decision"][
        "meaning"
    ]


# ---- phase=green / refactor: ALLOW 文言 ------------------------------


def test_phase_green_allow_meaning(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "green", "--path", str(project)]
    )
    assert exit_code == EXIT_OK
    gate = _gate(project)
    assert gate["phase"] == "green"
    meaning = gate["decision"]["meaning"].lower()
    # "freshly implemented" / "implementation" のいずれかが入る
    assert ("implementation" in meaning) or (
        "freshly" in meaning
    ), gate["decision"]["meaning"]


def test_phase_refactor_allow_meaning(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "refactor", "--path", str(project)]
    )
    assert exit_code == EXIT_OK
    gate = _gate(project)
    assert gate["phase"] == "refactor"
    meaning = gate["decision"]["meaning"].lower()
    assert ("refactor" in meaning) and ("passing" in meaning or "passed" in meaning)


# ---- phase=green/refactor + DENY: 通常 failure 扱い (verify と差別なし) ----


def test_phase_green_deny_is_normal_failure(tmp_path: Path) -> None:
    """phase=green の DENY は "normal failure"。"expected" は使わない."""
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--phase", "green", "--path", str(project)]
    )
    assert exit_code == EXIT_DENY
    gate = _gate(project)
    meaning = gate["decision"]["meaning"].lower()
    assert "expected" not in meaning, gate["decision"]["meaning"]
    # implementation phase の文脈の failure であることが分かる
    assert "implementation" in meaning


# ---- gate schema: phase=red の DENY も schema-valid -----------------


def test_phase_red_deny_gate_schema_valid(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "target" / "sample.txt").unlink()
    assert (
        main(
            [
                "run",
                "REQ-APP-001",
                "--yes",
                "--phase",
                "red",
                "--path",
                str(project),
            ]
        )
        == EXIT_DENY
    )

    from qgb.core.schema import validate as schema_validate

    gate = _gate(project)
    issues = schema_validate(gate, "gate")
    assert not issues, [(i.path, i.message) for i in issues]
