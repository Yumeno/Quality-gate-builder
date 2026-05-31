"""Step 6d Codex 横断レビューの補修テスト.

Codex 指摘 (中程度以上):
- 1: design-stages --commit の staging dir 固定名で pre-existing を削除する危険
- 3: policy.json.tmp 固定名で既存破壊
- 5: scaffold が壊れた policy で KeyError
- 6: command placeholder で PATH 上の同名コマンドが PASS する可能性
- 7: DesignProposal.committed の責務曖昧
"""

from __future__ import annotations

import json
from pathlib import Path

from qgb.cli import EXIT_NOT_READY, EXIT_OK, main


def _init_project(root: Path) -> None:
    qs = root / ".quality-system"
    qs.mkdir()
    (qs / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": [],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (qs / "config.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project": {"name": "x"},
                "qgb": {"core_language": "python", "version": "0.1.0"},
                "commands": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# ---- Codex 補修 1: pre-existing staging dir を削除しない ----------------


def test_commit_does_not_delete_pre_existing_user_staging_dir(
    tmp_path: Path,
) -> None:
    """ユーザーが偶然 <project>.qgb-stage という名前で何か置いていても消さない.

    Codex 補修 1: 旧実装は固定名 staging dir を毎回 rmtree していたが、
    tempfile.mkdtemp 化により unique 名になるため、ユーザーの既存ディレクトリは
    無関係に保存される。
    """
    project = tmp_path / "myproj"
    project.mkdir()
    _init_project(project)

    # ユーザーが先に作ってあるディレクトリを偽装。
    user_dir = tmp_path / "myproj.qgb-stage"
    user_dir.mkdir()
    (user_dir / "user-file.txt").write_text(
        "USER OWNED — DO NOT TOUCH\n", encoding="utf-8"
    )

    assert (
        main(["design-stages", "--commit", "--path", str(project)]) == EXIT_OK
    )

    # ユーザーディレクトリは無事。
    assert user_dir.is_dir()
    assert (user_dir / "user-file.txt").read_text(encoding="utf-8") == (
        "USER OWNED — DO NOT TOUCH\n"
    )


# ---- Codex 補修 3: tmp file が unique ------------------------------------


def test_commit_does_not_clobber_pre_existing_policy_tmp(
    tmp_path: Path,
) -> None:
    """policy.json.tmp が pre-existing でも破壊しない (unique 名で書く).

    旧実装は policy.json.tmp 固定名なので、同名の既存ファイルがあれば破壊
    していた。tempfile / UUID 化で unique 名にすれば無関係に保存される。
    """
    _init_project(tmp_path)
    rogue_tmp = tmp_path / ".quality-system" / "policy.json.tmp"
    rogue_tmp.write_text("PRE-EXISTING — do not touch\n", encoding="utf-8")

    assert (
        main(["design-stages", "--commit", "--path", str(tmp_path)]) == EXIT_OK
    )

    # 既存の .tmp は無傷。
    assert rogue_tmp.is_file()
    assert rogue_tmp.read_text(encoding="utf-8") == (
        "PRE-EXISTING — do not touch\n"
    )


# ---- Codex 補修 5: 壊れた policy で例外でなく NOT_READY ----------------


def test_scaffold_returns_not_ready_for_broken_policy(tmp_path: Path) -> None:
    """policy.json の stages[] が malformed でも traceback でなく NOT_READY.

    KeyError をユーザーに見せない。
    """
    qs = tmp_path / ".quality-system"
    qs.mkdir()
    # stage に必須 field id が欠落。
    (qs / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": [{"name": "missing-id"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # 例外で落ちず、NOT_READY (or USAGE) を返す。
    exit_code = main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)])
    assert exit_code == EXIT_NOT_READY


# ---- Codex 補修 6: command placeholder が誤 PASS しない ----------------


def test_command_placeholder_does_not_falsely_pass(tmp_path: Path) -> None:
    """verification_type=command の placeholder で run が DENY になる.

    旧実装は command=['TODO-replace-with-command-argv'] のみだったので、PATH 上に
    同名コマンドがあれば exit 0 で PASS するリスクがあった。Phase 1 の
    runner はまだ command を実装していないため、preflight で「unsupported
    verification_type」として弾かれて NOT_READY になることを最低限担保
    する (誤 PASS しない)。
    """
    qs = tmp_path / ".quality-system"
    qs.mkdir()
    (qs / "policy.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "policy_id": "default",
                "stages": [
                    {
                        "id": "S1",
                        "name": "cmd",
                        "responsibility": "command runs",
                        "depends_on": [],
                        "verification_type": "command",
                        "required_contract_fields": ["command"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (qs / "config.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "project": {"name": "x"},
                "qgb": {"core_language": "python", "version": "0.1.0"},
                "commands": {},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    assert main(["scaffold", "REQ-APP-001", "--path", str(tmp_path)]) == EXIT_OK

    # qgb run: command verification_type は Phase 1 では preflight で
    # unsupported として弾かれるはず → NOT_READY (誤 PASS にならない)。
    exit_code = main(
        ["run", "REQ-APP-001", "--yes", "--path", str(tmp_path)]
    )
    # NOT_READY (preflight が unsupported を弾く) または DENY のいずれか。
    # ALLOW (誤 PASS) ではないことを担保。
    assert exit_code != EXIT_OK


# ---- Codex 補修 7: DesignProposal に committed フィールドを持たせない ---


def test_design_proposal_dataclass_has_no_committed_field() -> None:
    """DesignProposal は純粋に proposal を表す。committed は CLI envelope のみ.

    Codex 補修 7: API 境界明確化のため、proposal data class から
    committed を削除し、commit status は CommitOutcome / CLI JSON envelope
    でのみ表現する。
    """
    from dataclasses import fields

    from qgb.core.design_stages import DesignProposal

    field_names = {f.name for f in fields(DesignProposal)}
    assert "committed" not in field_names, (
        f"DesignProposal.committed must be removed: {field_names}"
    )
