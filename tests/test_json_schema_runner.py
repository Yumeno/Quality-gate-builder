"""Step 8 項目 1: json_schema verification_type 実装.

Codex 計画レビュー方針:
- target / schema 両方 resolve_project_relative (R1 ガード)
- target / schema が JSON parse 失敗 → failed
- schema 自身が JSON Schema として malformed → failed
- $ref present → failed (Phase 1 では $ref unsupported)
- validate エラー (型違反 / required 欠落 / enum 違反) → failed
- format は Phase 1 では検査しない (docstring 明記)
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


def _replace_with_json_schema_contract(
    project: Path,
    *,
    target: str,
    schema: str,
) -> None:
    """policy / req meta / contract を single json_schema stage に書き換える."""
    pp = project / ".quality-system" / "policy.json"
    policy = json.loads(pp.read_text(encoding="utf-8"))
    policy["stages"] = [
        {
            "id": "S1",
            "name": "schema check",
            "responsibility": "target validates against schema",
            "depends_on": [],
            "verification_type": "json_schema",
            "required_contract_fields": ["target", "schema"],
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
    contract = {
        "schema_version": "1.0",
        "req_id": "REQ-APP-001",
        "stage_id": "S1",
        "verification_type": "json_schema",
        "target": target,
        "schema": schema,
    }
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


def test_valid_target_and_schema_passes(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo", "version": 1}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    gate = _gate(project)
    s1 = next(s for s in gate["stages"] if s["id"] == "S1")
    assert s1["result"] == "passed"


# ---- validation error -------------------------------------------------


def test_target_violates_schema_fails(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo"}), encoding="utf-8"  # version 欠落
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["name", "version"],
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    # 違反箇所 (path / message) が log に出る
    assert "required" in log.lower() or "version" in log.lower()


def test_type_violation_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"name": "demo", "version": "not-an-int"}),
        encoding="utf-8",
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "version": {"type": "integer"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


# ---- target missing / unreadable -------------------------------------


def test_target_missing_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="does-not-exist.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "target" in log.lower()


def test_schema_missing_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="does-not-exist.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "schema" in log.lower()


# ---- malformed JSON / schema -----------------------------------------


def test_target_not_json_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text("not valid json {", encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


def test_schema_not_json_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text("not valid", encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


def test_schema_not_valid_json_schema_is_failed(tmp_path: Path) -> None:
    """schema 自身が JSON Schema として malformed (e.g. type が文字列でない) → failed."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": 123}), encoding="utf-8"  # type は string であるべき
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY


# ---- R1: path escape -------------------------------------------------


def test_target_escape_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    # project の外に target を置く
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="../outside.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "outside the project root" in log


def test_schema_escape_is_failed(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    outside = tmp_path / "outside.schema.json"
    outside.write_text(json.dumps({"type": "object"}), encoding="utf-8")
    _replace_with_json_schema_contract(
        project, target="data.json", schema="../outside.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "outside the project root" in log


# ---- $ref unsupported ----------------------------------------------


def test_schema_with_dollar_ref_is_failed(tmp_path: Path) -> None:
    """Codex 計画レビュー方針: Phase 1 では $ref unsupported。

    内部/外部問わず $ref が存在したら failed として扱う。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "$defs": {"X": {"type": "string"}},
                "properties": {"y": {"$ref": "#/$defs/X"}},
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "$ref" in log or "ref" in log.lower()


# ---- preflight support -----------------------------------------------


def test_json_schema_no_longer_unsupported_in_run(tmp_path: Path) -> None:
    """Step 8 で json_schema が runtime supported に加わる."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )

    from qgb.cli import EXIT_NOT_READY
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # NOT_READY ではなく実行される (passed)
    assert exit_code != EXIT_NOT_READY


# ---- Phase 2 Step 2.1: enforce_format / allow_internal_ref ---------------


def _set_contract_flags(
    project: Path,
    *,
    enforce_format: bool | None = None,
    allow_internal_ref: bool | None = None,
) -> None:
    """Mutate the S1 contract to add Step 2.1 opt-in flags."""
    path = (
        project
        / ".quality-system"
        / "contracts"
        / "REQ-APP-001"
        / "S1.json"
    )
    contract = json.loads(path.read_text(encoding="utf-8"))
    if enforce_format is not None:
        contract["enforce_format"] = enforce_format
    if allow_internal_ref is not None:
        contract["allow_internal_ref"] = allow_internal_ref
    path.write_text(
        json.dumps(contract, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# enforce_format: 4 cases (default opt-out / opt-in pass / opt-in fail /
# unknown format silent-ignore w/ log).


def test_format_default_off_lets_bad_date_time_pass(tmp_path: Path) -> None:
    """Codex 指摘 (後方互換固定点): enforce_format 未指定で format 違反は
    従来通り passed のまま (Phase 1 挙動を保存).

    Step 2.1 補修 A3: formats_seen が「存在する」だけでなく schema 上の
    具体的な format 名 (``date-time``) を含むことを assert する。`formats_seen`
    キーが空のままでテストが偶発的に通る回帰を防ぐ。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"when": "not-a-date-time"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"when": {"type": "string", "format": "date-time"}},
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    assert "enforce_format: false" in log
    # Step 2.1 補修 A3: 具体的な format 名 ('date-time') を含むことを確認
    assert "formats_seen" in log
    assert "date-time" in log
    # enforce_format=false のときは formats_checked / formats_ignored は出ない
    # (Codex 横断レビュー: 非対称性は仕様通り)
    assert "formats_checked" not in log
    assert "formats_ignored" not in log


def test_format_enforced_passes_on_valid_date_time(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"when": "2026-06-04T12:34:56Z"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"when": {"type": "string", "format": "date-time"}},
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, enforce_format=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    assert "enforce_format: true" in log
    assert "formats_checked" in log
    assert "date-time" in log


def test_format_enforced_fails_on_invalid_date_time(tmp_path: Path) -> None:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"when": "not-a-date-time"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {"when": {"type": "string", "format": "date-time"}},
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, enforce_format=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "result: failed" in log


def test_format_enforced_logs_unknown_format_as_ignored(tmp_path: Path) -> None:
    """Codex 指摘 3: typo'd format name (e.g. 'datetime') is silently ignored
    by jsonschema, but must appear in ``formats_ignored`` so the author can
    catch the typo from the evidence."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"when": "not-a-date-time"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "when": {"type": "string", "format": "datetime"}
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, enforce_format=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    assert "formats_ignored" in log
    assert "datetime" in log


# allow_internal_ref: 11 cases (Codex 指摘 1/2/8).


def _schema_with_ref(ref: str) -> dict:
    return {
        "type": "object",
        "$defs": {"X": {"type": "string"}},
        "properties": {"y": {"$ref": ref}},
    }


def _setup_ref_project(
    tmp_path: Path,
    *,
    ref: str,
    allow_internal_ref: bool | None = None,
) -> Path:
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"y": "string-value"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(_schema_with_ref(ref)), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    if allow_internal_ref is not None:
        _set_contract_flags(project, allow_internal_ref=allow_internal_ref)
    return project


def test_pointer_ref_rejected_when_flag_default(tmp_path: Path) -> None:
    """default false → 既存挙動 (どんな $ref も failed)."""
    project = _setup_ref_project(tmp_path, ref="#/$defs/X")
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "$ref" in log
    assert "found_refs" in log
    assert "#/$defs/X" in log


def test_pointer_ref_allowed_when_flag_true(tmp_path: Path) -> None:
    """allow_internal_ref=true で `#/...` は許容、validator が解決して passed."""
    project = _setup_ref_project(
        tmp_path, ref="#/$defs/X", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    assert "internal_refs_accepted" in log
    assert "#/$defs/X" in log


def test_root_ref_hash_only_allowed(tmp_path: Path) -> None:
    """`ref == "#"` (root pointer) は許容."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    # root pointer = self-reference. validation depth limit kicks in eventually,
    # but the ref-collection phase must accept it.
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object", "properties": {"x": {"$ref": "#"}}}),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, allow_internal_ref=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # validation outcome is not important; what matters is the ref was accepted.
    log = _stage_log(project, "S1")
    assert "internal_refs_accepted" in log
    assert "#" in log
    assert exit_code in (EXIT_OK, EXIT_DENY)


def test_anchor_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    """Codex 指摘 1: `#foo` is an $anchor ref, NOT a JSON Pointer.
    Must be rejected even with allow_internal_ref=true."""
    project = _setup_ref_project(
        tmp_path, ref="#foo", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "non-internal $ref rejected" in log
    assert "disallowed_refs" in log
    assert "#foo" in log


def test_relative_uri_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    project = _setup_ref_project(
        tmp_path, ref="../other.json#/x", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log
    assert "../other.json#/x" in log


def test_file_uri_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    project = _setup_ref_project(
        tmp_path, ref="file:///etc/passwd", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log
    assert "file:///etc/passwd" in log


def test_http_uri_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    project = _setup_ref_project(
        tmp_path,
        ref="https://example.com/schema.json",
        allow_internal_ref=True,
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log
    assert "https://example.com/schema.json" in log


def test_sibling_file_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    """`schema.json#/x` (relative file ref with pointer suffix) は拒否."""
    project = _setup_ref_project(
        tmp_path, ref="schema.json#/x", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log
    assert "schema.json#/x" in log


def test_empty_string_ref_rejected_even_when_flag_true(tmp_path: Path) -> None:
    """空文字列 $ref は拒否 (Codex 指摘 1 の境界例)."""
    project = _setup_ref_project(
        tmp_path, ref="", allow_internal_ref=True
    )
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log


def test_mixed_refs_logs_all_disallowed(tmp_path: Path) -> None:
    """Codex 指摘 8: 複数の disallowed ref は log にすべて列挙."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"y": "v"}), encoding="utf-8"
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "$defs": {"X": {"type": "string"}},
                "properties": {
                    "y": {"$ref": "#/$defs/X"},  # internal — allowed
                    "z": {"$ref": "#foo"},        # anchor — disallowed
                    "w": {"$ref": "https://example.com/s.json"},  # http
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, allow_internal_ref=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs (2)" in log
    assert "#foo" in log
    assert "https://example.com/s.json" in log


def test_self_reference_does_not_crash(tmp_path: Path) -> None:
    """Codex 指摘 2: self-reference (root) schema は crash しない."""
    project = _copy_generic_minimal(tmp_path)
    # ``true`` schema (always-pass) avoids actual recursion blow-up while
    # exercising the root-pointer accept path.
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"$ref": "#"}), encoding="utf-8"
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, allow_internal_ref=True)
    # Whether passed or failed is irrelevant; the runner must not crash.
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code in (EXIT_OK, EXIT_DENY)


def test_non_string_ref_value_does_not_crash(tmp_path: Path) -> None:
    """Step 2.1 補修 A2 (Codex Step 2.1 計画レビュー指摘 8 強化):

    `$ref` 値が文字列でない malformed schema (例: ``$ref: 123``) でも runner
    は crash せず、`_collect_dollar_refs` が ``repr(123)`` = ``'123'`` を
    収集して disallowed として扱う。schema.SchemaError 経路に逃がさず、
    Step 2.1 の ref allowlist 経路で precise にログ列挙できることを spec lock。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    # Note: jsonschema's check_schema may or may not reject non-string $ref
    # depending on draft version. The Step 2.1 contract is that
    # ``_collect_dollar_refs`` runs BEFORE ``check_schema`` so a non-string
    # $ref is always surfaced through the allowlist path, not as a generic
    # SchemaError.
    (project / "data.schema.json").write_text(
        json.dumps(
            {"type": "object", "properties": {"x": {"$ref": 123}}}
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, allow_internal_ref=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    # Must not crash. The non-string $ref is repr()-ed to '123' which is not
    # an internal pointer, so it ends up in disallowed_refs.
    assert exit_code == EXIT_DENY
    log = _stage_log(project, "S1")
    assert "disallowed_refs" in log
    assert "123" in log


def test_duplicate_ref_unique_count_and_listing(tmp_path: Path) -> None:
    """Step 2.1 補修 A1 (Codex 横断レビュー指摘):

    同じ `$ref` が複数箇所に出現したとき、`internal_refs_accepted` の
    count と列挙は **unique 基準** で揃っている (count = 列挙数)。
    生 list の長さ (重複含む) を見せる旧設計の回帰を防ぐ。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(
        json.dumps({"a": "x", "b": "y"}), encoding="utf-8"
    )
    # Same `$ref` appearing in two distinct properties → refs list has length 2
    # but the unique set has size 1.
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "$defs": {"S": {"type": "string"}},
                "properties": {
                    "a": {"$ref": "#/$defs/S"},
                    "b": {"$ref": "#/$defs/S"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema_contract(
        project, target="data.json", schema="data.schema.json"
    )
    _set_contract_flags(project, allow_internal_ref=True)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_OK
    log = _stage_log(project, "S1")
    # Step 2.1 補修 A1: count は dedup 後の 1、列挙も 1 件のみ
    assert "internal_refs_accepted (1):" in log
    assert "#/$defs/S" in log
