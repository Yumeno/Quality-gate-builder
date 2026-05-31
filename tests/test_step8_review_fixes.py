"""Step 8 統合レビュー補修テスト.

Codex 段 3 判定:
- W1: json_schema runner が resolved target/schema path を log 出力する
- C1: validator instantiation / iter_errors の defensive try/except
- C2: sort key を list(e.absolute_path) に変更 (deterministic ordering)

Ph1 / W2 / W3 は docs 対応のためテスト不要 (本ファイル内では扱わない)。
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


def _replace_with_json_schema(
    project: Path, *, target: str, schema: str
) -> None:
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
    (contracts_dir / "S1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "req_id": "REQ-APP-001",
                "stage_id": "S1",
                "verification_type": "json_schema",
                "target": target,
                "schema": schema,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _stage_log(project: Path) -> str:
    return (
        project
        / ".quality-system"
        / "evidence"
        / "REQ-APP-001"
        / "latest"
        / "stages"
        / "S1.log"
    ).read_text(encoding="utf-8")


# ---- W1: resolved target/schema path is logged --------------------------


def test_json_schema_log_includes_resolved_target_path(tmp_path: Path) -> None:
    """Codex 段 3 W1: 他の runner と同様、resolved path を log に残す."""
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema(
        project, target="data.json", schema="data.schema.json"
    )

    assert main(["run", "REQ-APP-001", "--yes", "--path", str(project)]) == EXIT_OK
    log = _stage_log(project)
    # resolved target / schema が両方 log に出る
    assert "resolved target" in log
    assert "resolved schema" in log
    # 実 path も含まれる (Path.resolve() の結果)
    assert "data.json" in log
    assert "data.schema.json" in log


# ---- C1: validator defensive handling -----------------------------------


def test_json_schema_runner_does_not_crash_on_validator_exception(
    tmp_path: Path, monkeypatch
) -> None:
    """Codex 段 3 C1: validator/iter_errors で想定外例外が出ても failed として扱う.

    qgb run が tb を吐かず stage failed として記録する。これにより auditor は
    "runner が壊れた" を gate.json から読み取れる。

    実装側 ``_run_json_schema`` の ``jsonschema.validators.validator_for``
    のみを差し替えることで、qgb 自身の schema validation (preflight) と
    干渉しないようにする。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps({"type": "object"}), encoding="utf-8"
    )
    _replace_with_json_schema(
        project, target="data.json", schema="data.schema.json"
    )

    # _run_json_schema が呼ぶ ``iter_errors(target_data)`` のみを raise
    # に差し替える。target_data は {"x": 1} なので、それを引数に取った
    # ときだけ boom する形に。qgb 自身の schema validation 経路は別の
    # instance (REQ meta / contract 等の dict) を渡すので影響なし。
    import qgb.core.runner as runner_mod
    real_validator_for = runner_mod.jsonschema.validators.validator_for

    def fake_validator_for(schema, default=None):
        cls = (
            real_validator_for(schema, default=default)
            if default is not None
            else real_validator_for(schema)
        )
        real_iter = cls.iter_errors

        def maybe_boom(self, instance):
            # target_data に固有の sentinel ("x": 1) を持つときだけ boom
            if isinstance(instance, dict) and instance == {"x": 1}:
                raise RuntimeError("simulated validator failure")
            return real_iter(self, instance)

        # method を差し替えた lightweight wrapper class を返す
        return type(
            "Patched" + cls.__name__,
            (cls,),
            {"iter_errors": maybe_boom},
        )

    monkeypatch.setattr(
        runner_mod.jsonschema.validators,
        "validator_for",
        fake_validator_for,
    )

    # crash せず DENY (failed)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project)
    # 例外の事実 + 何が起きたかが log に残る
    assert "validator" in log.lower() or "runtime" in log.lower()
    assert "result: failed" in log


# ---- C2: deterministic error sort ---------------------------------------


def test_json_schema_errors_are_deterministically_sorted(tmp_path: Path) -> None:
    """Codex 段 3 C2: 複数のエラーが安定した順序で出る.

    複数の required 違反など順不同にならない field 集合を持つ schema で、
    実行ごとに同じ順で出ることを担保する。
    """
    project = _copy_generic_minimal(tmp_path)
    (project / "data.json").write_text(json.dumps({}), encoding="utf-8")
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "required": ["alpha", "beta", "gamma"],
                "properties": {
                    "alpha": {"type": "string"},
                    "beta": {"type": "integer"},
                    "gamma": {"type": "boolean"},
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema(
        project, target="data.json", schema="data.schema.json"
    )

    # 2 回実行して log のうち validation errors のセクションが同じ順序であること
    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    log_1 = _stage_log(project)
    # artifacts/evidence を一旦消して再実行
    qs = project / ".quality-system"
    shutil.rmtree(qs / "evidence", ignore_errors=True)
    shutil.rmtree(qs / "artifacts", ignore_errors=True)
    (qs / "artifacts").mkdir()

    main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    log_2 = _stage_log(project)

    # validation errors セクションが完全一致
    def _errors_section(text: str) -> list[str]:
        lines = text.splitlines()
        start = None
        for i, line in enumerate(lines):
            if line.startswith("validation errors"):
                start = i + 1
                break
        if start is None:
            return []
        # "result:" まで
        end = len(lines)
        for i in range(start, len(lines)):
            if lines[i].startswith("result:"):
                end = i
                break
        return lines[start:end]

    assert _errors_section(log_1) == _errors_section(log_2)


def test_json_schema_errors_with_mixed_int_str_paths_do_not_crash(
    tmp_path: Path,
) -> None:
    """収束ループ 1 周目 (Codex 段 5): absolute_path に int と str が
    混ざっても sort が落ちない.

    array index (int) と object key (str) が両方含まれるパスを持つ
    複数 error をシミュレートする schema/target を組む。
    """
    project = _copy_generic_minimal(tmp_path)
    # target: pages[0] と pages[1] の両方が schema 違反になる構造
    (project / "data.json").write_text(
        json.dumps(
            {
                "pages": [
                    {"path": 123},  # path is not string → array index 0 + object key 'path'
                    {},  # missing required 'path' → array index 1
                ]
            }
        ),
        encoding="utf-8",
    )
    (project / "data.schema.json").write_text(
        json.dumps(
            {
                "type": "object",
                "properties": {
                    "pages": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["path"],
                            "properties": {
                                "path": {"type": "string"}
                            },
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    _replace_with_json_schema(
        project, target="data.json", schema="data.schema.json"
    )

    # crash せず DENY (failed) として記録される (TypeError が漏れない)
    exit_code = main(["run", "REQ-APP-001", "--yes", "--path", str(project)])
    assert exit_code == EXIT_DENY
    log = _stage_log(project)
    # validation errors セクションに複数 error が並ぶ
    assert "validation errors" in log
    assert "result: failed" in log
