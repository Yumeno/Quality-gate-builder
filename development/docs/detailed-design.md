# quality-gate-builder 詳細設計 v0.1 (Phase 1 Step 0〜2 確定範囲)

## 1. 本書の位置づけ

本書は、Phase 1 Step 0〜2 の実装を通じて確定した詳細設計を記録する。要件定義書 (v0.3) と思想憲章を上位に置き、それらの抽象的な要求を「実装側でどう具体化するか」を凝固させた事項を扱う。

本書は以下の関係性に従う：

```
[思想憲章] philosophy.md
   ↓ 制約を与える
[要件定義書] requirements_and_development.md  v0.3
   ↓ 何を作るかを定める
[段階設計仕様] stage-design.md                    [フレームワーク境界] framework-shape.md
   ↓ 設計プロセスと境界
[本書 詳細設計] detailed-design.md
   ↓ どう作るかを記録
[実装] qgb/ qgb/core/ qgb/schemas/ tests/
```

要件定義書や思想憲章と矛盾する記述があれば、それらが優先される。本書は実装側の確定事項であり、上位文書を変更したい場合は本書ではなく上位文書から改訂する。

## 2. リポジトリ実体構造 (Step 0〜2 時点)

```text
quality-gate-builder/
  pyproject.toml                       # setuptools, jsonschema, pytest, ruff
  README.md
  LICENSE
  CLAUDE.md
  .gitignore

  qgb/                                  # Phase 1 で実装する Python パッケージ
    __init__.py                         # importlib.metadata.version() で __version__ 解決
    __main__.py                         # python -m qgb のエントリ
    cli.py                              # QgbArgumentParser, build_parser(), main()
    core/
      __init__.py
      schema.py                         # スキーマ読み込み + Draft 2020-12 検証 + RFC3339 date-time format checker
      validate.py                       # qgb validate の本体
    adapters/__init__.py               # Phase 1 では空
    schemas/                            # バンドルされる JSON Schema 群
      README.md
      config.schema.json
      policy.schema.json
      req-meta.schema.json
      contract.schema.json
      gate.schema.json                  # 採用判定証跡用 (strict)
      gate.runtime.schema.json          # 揮発側 (permissive)
      knowledge.schema.json
    templates/                          # Phase 1 中盤以降で使用予定
      .gitkeep

  development/docs/
    philosophy.md                       # 思想憲章 v1.0 (P1〜P11)
    requirements_and_development.md     # 要件定義書 v0.3
    stage-design.md                     # 段階設計フェーズ仕様 v1.0
    framework-shape.md                  # フレームワーク境界 v1.0
    detailed-design.md                  # 本書
    project-background.md
    wakaba-talk-summary.md
    yaoyorozu-system-references.md
    requirements_and_development.v0.2.md  # 履歴保存
    journal/                            # 作業記録
      phase1-step0-to-step2.md

  tests/
    __init__.py
    test_cli_smoke.py
    test_schemas.py
    test_validate.py
    fixtures/
      schemas/                          # JSON Schema 用 success/failure fixture
      projects/                         # .quality-system/ ツリーの fixture
        valid/
        schema_violation/
        field_mismatch/
        forward_compat_field/
        invalid_json/
```

`skills/source/`、`tools/`、`dist/skills/`、`examples/` は Phase 1 中盤以降 / Phase 5 で追加予定。

## 3. CLI 体系の確定事項

### 3.1 エントリポイント

- 提供入口は `python -m qgb` のみ（Phase 1）
- `[project.scripts]` に `qgb` console script は登録しない（Phase 3+ で検討、CLAUDE.md 整合）

### 3.2 サブコマンド一覧と実装状況

| サブコマンド | Step | 状態 | 役割 |
|---|---|---|---|
| `validate` | 2 | **実装済み** | 個別 JSON 仕様ファイルがスキーマに準拠しているか + §F-005 contract field 混在 |
| `init` | 3 | parser 登録のみ | `.quality-system/` 初期化 |
| `detect` | 6 | parser 登録のみ | 対象系の言語/フレームワーク推定 |
| `design-stages` | 6 | parser 登録のみ | 段階設計フェーズ |
| `scaffold` | 6 | parser 登録のみ | REQ + contract + テスト雛形 |
| `validate-policy` | 6 | parser 登録のみ | 段階設計の品質 + 正本ツリー整合性 |
| `verify` | 6 | parser 登録のみ | 軽量チェック (揮発側のみ) |
| `run` | 5 | parser 登録のみ | 採用判定 (preflight + ALLOW/DENY 出力) |

未実装サブコマンド呼び出しは `_handle_not_implemented` 共通 stub が EXIT_USAGE (=64) を返す。各 subparser に `set_defaults(handler=...)` を仕込んであり、Step ごとに stub を実 handler に差し替える設計。

### 3.3 終了コード規約

| コード | 意味 | 出力先 |
|---|---|---|
| 0 | 成功 (ALLOW、検査通過) | stdout |
| 1 | DENY | gate.json + stderr |
| 2 | NOT_READY (構成不備、ファイル不在、検証エラー) | stderr (gate.json は出さない) |
| 64 | CLI usage error (不明引数、未実装 subcommand) | stderr |
| その他 | 内部エラー | stderr |

実装：
- `qgb/cli.py` の `EXIT_OK / EXIT_DENY / EXIT_NOT_READY / EXIT_USAGE` 定数
- `QgbArgumentParser.error()` を override し、argparse の usage error を 64 に固定（要件定義書 §6.2.3）

### 3.4 コマンド別の責務分離 (思想 P9 単一責任原則)

```
qgb validate         = 各個別 JSON 仕様ファイルが機械正本契約 (スキーマ) に従っているか
                       + §F-005 contract field 混在
qgb validate-policy  = 正本ツリー全体の整合性と設計品質
                       (必須ファイル / contract_ref / stage_id / DAG /
                        canonical layout / manual_check only など)
qgb run preflight    = 上記 2 つを結合実行して READY/NOT_READY 判定
qgb run main         = READY 時の検査実行と ALLOW/DENY 出力
```

責務越境の禁止: `qgb validate` に integrity check を統合する案は Step 2 で一度試みて巻き戻した（commit `dccdf4a` → `6222035`）。スキーマ準拠とツリー整合は別の失敗モードであり、別のフィードバックを返すべき（Phase 5 スキル化観点でも重要）。

## 4. JSON Schema 規約 (Step 1 確定)

### 4.1 ファイル構成

| ファイル | 対象 | additionalProperties |
|---|---|---|
| `config.schema.json` | `.quality-system/config.json` | true |
| `policy.schema.json` | `.quality-system/policy.json` | true |
| `req-meta.schema.json` | `.quality-system/req/<REQ>.meta.json` | true |
| `contract.schema.json` | `.quality-system/contracts/<REQ>/<stage>.json` | true |
| `gate.schema.json` | `evidence/<REQ>/latest/gate.json` (採用判定) | **false** (strict、最も厳格) |
| `gate.runtime.schema.json` | `artifacts/<REQ>/runs/<ts>/gate.json` (揮発) | true |
| `knowledge.schema.json` | `knowledge.jsonl` の各行 | true |

採用判定証跡だけ厳格、それ以外は拡張可能性のため緩い設計。これは `yaoyorozu-system/core` の方針に倣う。

### 4.2 命名と識別子規約

| 識別子 | 形式 | 例 |
|---|---|---|
| REQ id | `^REQ-[A-Z0-9]+-[0-9]{3,}$` | `REQ-APP-001` |
| stage id | 自由命名 (`L1`, `S1`, `cmd` など)、policy 内で一意 | `S1`, `S2` |
| schema_version | `^[0-9]+\.[0-9]+$` | `1.0` |
| timestamp_utc | `^[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])T(0[0-9]\|1[0-9]\|2[0-3])([0-5][0-9]){2}Z$` | `2026-05-21T012345Z` |
| timestamp_rfc3339 | `format: date-time` (qgb 独自 RFC3339 shape checker) | `2026-05-21T01:23:45Z` |

### 4.3 gate.json の if/then 整合性制約

採用判定証跡 (gate.schema.json) は以下を schema レベルで強制：

```
status=ALLOW   ⇒  failed_stage = ""
              ⇒  decision.result = "ALLOW"
              ⇒  全 stages[].result = "passed"

status=DENY    ⇒  failed_stage != ""
              ⇒  decision.result = "DENY"
              ⇒  少なくとも 1 つの stages[].result = "failed"
```

揮発側 (gate.runtime.schema.json) も同じ if/then 制約を持つ (additionalProperties: true との違いのみ)。runtime は curated へ昇格する元データのため、意味論不整合を許してはならない。

### 4.4 stages[] (gate.json 内) の必須フィールド

採用判定証跡では：

```json
{
  "id": "S1",
  "name": "...",
  "result": "passed" | "failed",
  "verification_type": "command" | "file_exists" | ...,
  "exit_code": integer | null,
  "contract_ref": "..."  ,
  "log_ref": "stages/S1.log"
}
```

`exit_code` は null 許容だが**フィールド自体は必須**（外部プロセス非起動の stage では null を入れる）。`contract_ref` と `log_ref` は思想 P7 (再現可能な証跡) の機械的強制。

### 4.5 contract.schema.json の verification_type 別 if/then

base 必須: `schema_version`, `req_id`, `stage_id`, `verification_type`

verification_type 別の必須/任意フィールド：

| verification_type | 必須 | 任意 |
|---|---|---|
| `command` | `command` (argv 配列) | `expected_exit_code`, `working_dir`, `timeout_seconds` |
| `file_exists` | `target` | - |
| `substring_match` | `target`, `must_contain` (1 以上) | - |
| `json_schema` | `target`, `schema` | - |
| `manual_check` | `description` | - |

`command` は **argv 配列限定** (shell 文字列禁止、NF-007 安全性)。

### 4.6 RFC3339 date-time format

`jsonschema` の built-in `FormatChecker` には `date-time` が含まれない。`qgb.core.schema._build_format_checker` で stdlib のみ (`re` + `datetime.fromisoformat`) で実装した RFC3339 shape checker を追加登録。

検査基準: `YYYY-MM-DDTHH:MM:SS[.fff](Z|±HH:MM)` のシェイプ + `datetime.fromisoformat` で受理可能なこと。leap second 等の細部までは保証しない（NF-010 依存最小化を優先）。

### 4.7 JSON Pointer (RFC 6901) 準拠

`ValidationIssue.path` は RFC 6901 準拠の JSON Pointer。`/` と `~` を含むキーは `~1` と `~0` にエスケープ。`~` のエスケープが先（`~` → `~0`、その後 `/` → `~1`）でないと、`/` が偽の `~1` を生成して二重エスケープが壊れる。

## 5. qgb validate の責務 (Step 2 確定)

### 5.1 入力

- `--path <dir>` (default: `.`): プロジェクトルートのディレクトリ
  - 存在しない → exit 64
  - ファイル指定 → exit 64 (Codex 重大指摘 #1 対応)
- `--json`: 機械可読出力

### 5.2 走査対象 (canonical layout のみ)

```
<root>/.quality-system/
  config.json                          # 1 件
  policy.json                          # 1 件
  req/*.meta.json                      # 0 件以上、ソート
  contracts/<REQ>/*.json               # 0 件以上、REQ ソート × stage ソート
```

`contracts/<REQ>/<sub>/<file>.json` のような深い階層は **走査しない**（Step 6 の `validate-policy` で `misplaced_contract` として検出する）。

`.quality-system/` ディレクトリ自体が無い場合は「対象なし」として exit 0。

### 5.3 検査内容

1. **JSON parse**: 失敗時 → `ReadError`
2. **スキーマ検証**: schema_name (`config` / `policy` / `req-meta` / `contract`) に対応するバンドル schema で `qgb.core.schema.validate`
3. **contract field 混在検出** (§F-005): contract のみ。verification_type に対応する `_CONTRACT_TYPE_FIELDS` 集合 + base fields 以外で、かつ `_ALL_TYPE_FIELDS` に含まれる field を `FieldMismatch` として報告。未知 forward-compatible field (tags, notes, disabled など) は許容。

### 5.4 やらないこと

- 必須ファイル (config.json / policy.json) の欠落検出 → validate-policy
- `contract_ref` の resolve → validate-policy
- `stage_id` が policy に存在するか → validate-policy
- `depends_on` の DAG → validate-policy
- canonical layout 外配置の検出 → validate-policy
- 上記すべての結合判定 → run preflight

### 5.5 出力

#### text モード（デフォルト）

- 問題なし → stdout に「Checked N file(s):」と「OK: ...」
- 問題あり → stderr にチェック対象 + 「Read errors / Schema violations / Contract field mismatches」を順に列挙

#### `--json` モード

```json
{
  "ok": true | false,
  "files_checked": [{"path": "...", "schema": "config" | ...}],
  "schema_issues": [{"file": "...", "schema": "...", "path": "/...", "schema_path": "/...", "message": "..."}],
  "field_mismatches": [{"file": "...", "verification_type": "...", "field": "...", "owning_verification_type": "..."}],
  "read_errors": [{"file": "...", "message": "..."}],
  "summary": {
    "ok": bool,
    "files": N,
    "schema_issues": N,
    "field_mismatches": N,
    "read_errors": N,
    "total_problems": N
  }
}
```

`--json` 時は **stderr は完全に空**（CI/ツール連携で機械処理しやすくするため）。

### 5.6 終了コード

- 問題なし → 0
- 問題あり → 2 (NOT_READY)
- パス不在 / ファイル指定 → 64

## 6. Python 実装規約 (Step 0〜2 確定)

### 6.1 依存

| 種別 | パッケージ | 用途 |
|---|---|---|
| runtime | `jsonschema>=4.20,<5.0` | JSON Schema 検証 |
| dev | `pytest>=8.0` | テスト |
| dev | `ruff>=0.5` | Lint + format |

採用前に要件定義書 §6.6.2 のサプライチェーン調査チェックリストを通している。

### 6.2 Python バージョンと言語機能

- `requires-python = ">=3.10"` (pyproject.toml)
- `from __future__ import annotations` を全モジュールで使用
- 型ヒント: PEP 604 `X | Y` 表記、PEP 585 ジェネリクス (`list[int]` 等)
- `importlib.resources.abc.Traversable` を使用 (Python 3.14 で deprecated になる `importlib.abc` 経由は避ける)

### 6.3 文字コード規約

- ファイル I/O は **常に `encoding="utf-8"` を明示**
- subprocess を起動するテストは `PYTHONIOENCODING=utf-8` + `PYTHONUTF8=1` を環境変数で渡す（Windows CP932 ロケール対策）
- **CLI help テキストと docstring に em-dash (U+2014) などの非 ASCII 文字を使わない**（Windows CP932 ターミナルで `--help` が UnicodeEncodeError で落ちるため、NF-004 可搬性）
- 日本語コメントや日本語ドキュメントは OK（読み込み時 UTF-8 で扱う限り）

### 6.4 パス操作

- `pathlib.Path` を使う（文字列パス連結を避ける）
- リソースアクセスは `importlib.resources.files("qgb").joinpath(...)` 経由
- テストでパス比較するときは `/` 区切り固定の文字列比較を避ける

### 6.5 ruff 設定

`pyproject.toml`:

```toml
[tool.ruff]
line-length = 100
target-version = "py310"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP"]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["B011"]
```

### 6.6 テスト構成

- 単体テスト (in-process `main([...])` 呼び出し): `capsys` で stdout/stderr 検査
- subprocess smoke test: `python -m qgb` を実プロセスで起動、UTF-8 強制
- fixture: `tests/fixtures/schemas/` (Schema 用) と `tests/fixtures/projects/` (`.quality-system/` ツリー用)
- assertion: 「壊れたら落ちる」ではなく「狙った schema path で落ちる」を検証 (Codex 指摘対応)

## 7. テスト規約 (Step 0〜2 確定)

### 7.1 テスト件数の現状

- Step 0: 11 件 (CLI smoke + subprocess)
- Step 1: 51 件追加 (Schema 検証)
- Step 2: 37 件追加 (validate コマンド) → 巻き戻し後 24 件

合計 **99 件、全成功、ruff 警告ゼロ**。

### 7.2 fixture の責務分離

| ディレクトリ | 用途 |
|---|---|
| `tests/fixtures/schemas/` | 各 JSON Schema の success/failure 検証 |
| `tests/fixtures/projects/` | `.quality-system/` ツリー全体の検証 |
| `tests/fixtures/projects/valid/` | 完全に問題なしの基準ツリー |
| `tests/fixtures/projects/schema_violation/` | policy.json に schema 違反 |
| `tests/fixtures/projects/field_mismatch/` | contract に他 type 専有 field 混入 |
| `tests/fixtures/projects/forward_compat_field/` | contract に未知 forward-compatible field |
| `tests/fixtures/projects/invalid_json/` | JSON 構文崩壊 |

Step 6 で `missing_required/` `dangling_ref/` `misplaced_contract/` を復活させる（巻き戻し前にあったもの）。

### 7.3 subprocess テストの規約

```python
def _run_qgb(*args: str) -> subprocess.CompletedProcess[str]:
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
```

Windows CP932 ロケール下で日本語パスを含むケースが UTF-8 reader thread を壊さないために必須。

## 8. 思想憲章との対応マトリクス (Step 0〜2 範囲)

| 思想項目 | 実装での機械化 |
|---|---|
| P1 品質=要求を満たすこと | REQ メタの schema が `req_id` と `stages[]` を必須化 |
| P5 ALLOW/DENY の意味の限定 | gate.schema.json で `decision.meaning` を必須化、if/then で `status` × `decision.result` × `failed_stage` × `stages[].result` の整合性を強制 |
| P7 再現可能な証跡 | gate.schema.json で `runner.name/version`、`timestamp_utc`、`timestamp_rfc3339`、`stages[].contract_ref`、`stages[].log_ref`、`basis[]` を必須化 |
| P8 外部取得コンテンツはプロンプトでない | knowledge.schema.json の `requires_human_review` フィールド |
| P9 単一責任原則 | policy.schema.json で `responsibility` 必須化。CLI コマンド体系でも `validate` / `validate-policy` / `run preflight` の責務分離を維持 (Step 2 巻き戻しの根拠) |
| NF-004 可搬性 | UTF-8 強制 (subprocess test)、非 ASCII を CLI help から除去 |
| NF-007 安全性 | contract.schema.json の `command` を argv 配列限定 |
| NF-010 依存最小化 | jsonschema 以外を runtime 依存に加えない。date-time format checker を `rfc3339-validator` ではなく stdlib (`re` + `datetime`) で自前実装 |

## 9. 未確定 / Step 3 以降で確定する事項

以下は本書時点では未確定。各 Step で確定し、本書を改訂する。

| 項目 | 確定予定 Step |
|---|---|
| `.quality-system/` 初期化時の雛形内容 (config.json / policy.json の初期値) | Step 3 |
| `.gitignore` 自動追記の方針 | Step 3 |
| `examples/generic-minimal/` の段階定義と contract 構造 | Step 4 |
| gate.json 生成ロジック (timestamp 生成、basis 列挙、stages[] 構造) | Step 5 |
| 採用 / 揮発の 2 系統パス分離 (`evidence/` と `artifacts/`) | Step 5 |
| `QGB_KEEP_RUNS` の動作 | Step 5 |
| `qgb run` 実行前の確認プロンプト (`--yes` フラグ) | Step 5 |
| `qgb verify` と `qgb run` の差分 | Step 5 |
| `qgb validate-policy` の実装と `qgb/core/policy_checks.py` 共有モジュール | Step 6 |
| `qgb detect` の対象系推定ロジック | Step 6 |
| `qgb design-stages` 提案フェーズと採用フェーズの分離 | Step 6 |
| `qgb scaffold` の REQ + contract + テスト雛形生成 | Step 6 |
| TDD phase (red / green / refactor / verify) の実装 | Step 7 |
| `manual_check` の Phase 1 NOT_READY 化 | Step 7 |
| `waived` 段階の knowledge.jsonl 記録 | Step 7 |
| 設計例パック 2 例追加 (python-cli-pytest / markdown-docs) | Step 8 |
| knowledge 追加コマンド、導入マニュアル、依存調査ポリシー文書 | Step 9 |

## 10. 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 0.1 | 2026-05-21 | Phase 1 Step 0〜2 確定範囲を初版として記録 |
