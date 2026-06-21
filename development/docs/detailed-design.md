# quality-gate-builder 詳細設計 v0.10 (Phase 1 Step 0〜5 + 補修 4 段確定範囲、Step 5 完結、Codex レビュー反映済み)

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
      init.py                           # qgb init の本体
      loader.py                         # policy/req-meta/contract/config の I/O (Step 5)
      preflight.py                      # qgb run の READY/NOT_READY 判定 (Step 5)
      runner.py                         # file_exists / substring_match 実行 (Step 5)
      decision.py                       # ALLOW/DENY 判定 (Step 5)
      evidence.py                       # gate.json/summary.md/log の 2 系統書き出し (Step 5)
    # adapters/ は Phase 1 Step 6c で base / generic / python の 3 種を実装したが、
    # Phase 3 Step 3.0 (2026-06-21) で対象プロジェクトの分析責務を
    # Phase 5 スキルに移して撤去 (§14)。本書の上流節 (§5.1 / §9 等) で
    # adapter が「現役」と読める箇所は、Phase 1 完結時点の真実を歴史記録
    # として残したもの。
    schemas/                            # バンドルされる JSON Schema 群
      README.md
      config.schema.json
      policy.schema.json
      req-meta.schema.json
      contract.schema.json
      gate.schema.json                  # 採用判定証跡用 (strict)
      gate.runtime.schema.json          # 揮発側 (permissive)
      knowledge.schema.json
    templates/                          # qgb init の雛形 (Step 3 追加)
      config.initial.json
      policy.initial.json
      project-context.initial.md

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
    test_init.py
    test_examples.py
    fixtures/
      schemas/                          # JSON Schema 用 success/failure fixture
      projects/                         # .quality-system/ ツリーの fixture
        valid/
        schema_violation/
        field_mismatch/
        forward_compat_field/
        invalid_json/

  examples/
    generic-minimal/                    # Step 4: 入門用最小サンプル (2 段階、file_exists + substring_match)
      README.md
      design-notes.md
      .gitignore
      target/sample.txt
      .quality-system/
        config.json
        policy.json
        req/REQ-APP-001.{md,meta.json}
        contracts/REQ-APP-001/{S1,S2}.json
        evidence/REQ-APP-001/latest/
          gate.json
          summary.md
          stages/{S1,S2}.log               # log_ref が指す stage 実行ログ
```

`skills/source/`、`tools/`、`dist/skills/` は Phase 5 で追加予定。`examples/` には Step 8 (完結 2026-06-01) で `python-cli-pytest/` と `markdown-docs/` を追加済。これにより Phase 1 の 3 例 (generic-minimal / python-cli-pytest / markdown-docs) が揃い、4 runtime-supported verification_type (file_exists / substring_match / command / json_schema) を網羅する。

## 3. CLI 体系の確定事項

### 3.1 エントリポイント

- 提供入口は `python -m qgb` のみ（Phase 1）
- `[project.scripts]` に `qgb` console script は登録しない（Phase 3+ で検討、CLAUDE.md 整合）

### 3.2 サブコマンド一覧と実装状況

| サブコマンド | Step | 状態 | 役割 |
|---|---|---|---|
| `validate` | 2 | **実装済み** | 個別 JSON 仕様ファイルがスキーマに準拠しているか + §F-005 contract field 混在 |
| `init` | 3 | **実装済み** | `.quality-system/` 初期化、空 stages の policy.json と空 knowledge.jsonl、`.gitignore` 追記 |
| `run` | 5 | **実装済み** | 採用判定 (preflight + ALLOW/DENY 出力 + 採用/揮発 2 系統への証跡書き出し) |
| `detect` | 6 | parser 登録のみ | 対象系の言語/フレームワーク推定 |
| `design-stages` | 6 | parser 登録のみ | 段階設計フェーズ |
| `scaffold` | 6 | parser 登録のみ | REQ + contract + テスト雛形 |
| `validate-policy` | 6a | **実装済み** | 段階設計の品質 + 正本ツリー整合性 |

未実装サブコマンド呼び出しは `_handle_not_implemented` 共通 stub が EXIT_USAGE (=64) を返す。各 subparser に `set_defaults(handler=...)` を仕込んであり、Step ごとに stub を実 handler に差し替える設計。**現時点で `init` / `validate` / `validate-policy` / `run` は stub から実 handler への差し替え済み**で、`detect` / `design-stages` / `scaffold` のみが stub 状態 (上表の「parser 登録のみ」列に対応)。

> `qgb verify` は Phase 1 spec-review で撤回されたため、本表に含めない (思想憲章 P3 との緊張、`stage-design.md` §3.1 参照)。`phase` 値の `verify` は TDD 局面として残るが、これは CLI コマンドとは無関係。

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
| timestamp_utc | `^[0-9]{4}-(0[1-9]\|1[0-2])-(0[1-9]\|[12][0-9]\|3[01])T(0[0-9]\|1[0-9]\|2[0-3])([0-5][0-9]){2}Z$` (wall-clock truth、秒精度) | `2026-05-21T012345Z` |
| timestamp_rfc3339 | `format: date-time` (qgb 独自 RFC3339 shape checker) | `2026-05-21T01:23:45Z` |
| run_id | `^r[0-9a-f]{4}$` かつ `not r0000` (Step 5 三次補修で導入、四次補修で `r0000` 予約。同秒内の衝突を吸収する monotonic counter、`r0001`〜`rffff` の 65,535 slots) | `r0001`, `r0042` |

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

## 6. qgb init の責務 (Step 3 確定)

### 6.1 入力

- `--path <dir>` (default: `.`): プロジェクトルートのディレクトリ
  - 存在しない → exit 64
  - ファイル指定 → exit 64
- `--name <project_name>`: `config.json` の `project.name` に書き込む値 (default: ディレクトリ名)
- `--force`: 既存ファイルを上書き
- `--json`: 機械可読出力

### 6.2 生成するもの

ディレクトリ:

```
<root>/.quality-system/
  req/
  contracts/
  knowledge/
  evidence/
  artifacts/
```

`evidence/` と `artifacts/` は Step 5 の `qgb run` で実際に使われる予約スペース。Step 3 では空ディレクトリとして生成しておく。

ファイル:

| パス | 内容 |
|---|---|
| `.quality-system/config.json` | `{schema_version, project.name, qgb.{core_language, version}, commands: {}}` |
| `.quality-system/policy.json` | `{schema_version, policy_id: "default", stages: []}` |
| `.quality-system/knowledge/knowledge.jsonl` | 空ファイル |
| `.quality-system/knowledge/project-context.md` | 雛形 Markdown |

### 6.3 idempotent / 衝突安全規約

- 既存ファイルは **skipped** (上書きしない)
- `--force` フラグで **overwritten**
- ディレクトリは常に `mkdir(parents=True, exist_ok=True)` で確保 (壊さない)
- 二重実行で副作用なし。`.gitignore` も byte-for-byte 不変
- **パス種別衝突 (例: 期待がディレクトリの場所にファイル / 期待がファイルの場所にディレクトリ)** は `InitError` として記録し、`exit 2 (NOT_READY)` で停止。`--force` でもバイパスしない
- 衝突対象は `.quality-system` 自身、`.quality-system/<subdir>/`、各正本ファイル、`.gitignore`

### 6.4 `.gitignore` 自動追記の規約

- 既存 `.gitignore` があれば追記
- なければ新規作成
- 既に `.quality-system/artifacts/` が含まれていれば何もしない (`already-present`)
- 末尾改行が無い既存ファイルにも安全に追記する

追記される内容:

```text
# qgb volatile artifacts
.quality-system/artifacts/
```

### 6.5 出力

#### text モード (デフォルト)

```
Initialised .quality-system/ at <abspath>
  Ensured N directories.
  + created     <path>
  - skipped     <path> (file already exists)
  * overwritten <path>
  .gitignore: created | appended | already-present | skipped
```

衝突検出時 (NOT_READY):

```
qgb init: refused to corrupt existing tree at <abspath>
  Ensured N directories.
  ...
Initialisation errors (M):
  - [path_is_file_expected_dir] expected directory at ..., but a non-directory entry exists
  - [path_is_dir_expected_file] expected file at ..., but a non-file entry exists
  - [gitignore_not_a_regular_file] ... exists but is not a regular file; qgb init will not modify it
```

#### `--json` モード

```json
{
  "ok": true | false,
  "project_root": "...",
  "dirs_ensured": ["..."],
  "files": [{"path": "...", "action": "created" | "skipped" | "overwritten", "note": ""}],
  "gitignore_action": "created" | "appended" | "already-present" | "skipped" | null,
  "errors": [{"kind": "path_is_file_expected_dir" | "path_is_dir_expected_file" | "gitignore_not_a_regular_file" | "gitignore_unreadable", "path": "...", "message": "..."}],
  "summary": {
    "ok": bool,
    "dirs_ensured": N,
    "files": N,
    "errors": M
  }
}
```

`ok` は問題なし時 true。errors[] に何か入ると false。CLI exit code は ok=true で 0、false で 2 (NOT_READY)。

### 6.6 やらないこと (他コマンドの責務)

- 対象系の言語/フレームワーク推定 → ~~`qgb detect` (Step 6)~~ **Phase 3 Step 3.0 で廃止**。対象プロジェクトの自己定義は `.quality-system/project-context.{md,json}` に人間 + 補佐 Agent が書く運用に移行 (§14)
- 段階設計の中身 → `qgb design-stages` (Step 6d / Phase 2 Step 2.5 Pattern B)
- REQ + contract 雛形 → `qgb scaffold` (Step 6)
- 初期状態の整合性チェック → `qgb validate` (Step 2) と `qgb validate-policy` (Step 6a) で必要に応じて

### 6.7 init → validate ラウンドトリップ保証

`qgb init` 直後の `.quality-system/` ツリーは `qgb validate` で必ず OK 判定 (exit 0) になる。Step 4 の `examples/generic-minimal/` 構築や Step 5 の `qgb run` 前提として、この保証は重要。

テスト `test_init.py::test_init_output_passes_validate` でこのラウンドトリップを毎回検証。

## 7. 設計例パック (Step 4 確定範囲)

### 7.1 examples/generic-minimal/

Phase 1 で初めて整備された設計例 (Issue #19)。**入門用最小サンプル**として位置づけ、実プロジェクトでこのまま流用するのは推奨しない。

#### 構成

- 段階数: 2 (S1: file_exists, S2: substring_match)
- 段階数は推奨レンジ (3-7) **の外** だが、入門用に意図的に縮めている
- 言語非依存 (Generic)、対象は単一テキストファイル

#### 含まれるもの

- `README.md`: サンプルの全体像
- `design-notes.md`: 設計判断メモ
- `.gitignore`: `.quality-system/artifacts/` と `.quality-system/evidence/` を除外
- `target/sample.txt`: 検査対象テキスト
- `.quality-system/{config,policy}.json`: qgb の正本
- `.quality-system/req/REQ-APP-001.{md,meta.json}`: REQ 1 件
- `.quality-system/contracts/REQ-APP-001/{S1,S2}.json`: 各段階の contract
- `evidence-reference/REQ-APP-001/latest/{gate.json, summary.md, stages/{S1,S2}.log}`: **手書き** の期待 ALLOW 出力 (Step 5 補修で `.quality-system/evidence/` から外に退避)

`.quality-system/artifacts/` と `.quality-system/evidence/` は git 管理外 (前者は揮発側 destination、後者は採用側 destination)。両方とも `qgb run` 実行時に動的に生成される。

#### Step 5 への意味と reference 退避 (Step 5 補修)

`evidence-reference/REQ-APP-001/latest/gate.json` は `qgb run` のターゲット仕様。同じパスに `qgb run` の destination (`.quality-system/evidence/`) を置くと、in-repo 実行で手書きリファレンスが上書きされる事故が起きるため、reference は `evidence-reference/` 配下に分離した。テスト (`tests/test_examples.py`) は `evidence-reference/` を読みに行く。

### 7.2 design-notes.md の必須項目 (今後の examples すべてに適用)

Issue #12 議論で確定:

1. 対象系の特徴 (他の例と何が違うか)
2. 段階数の決定根拠 (推奨レンジ外なら理由)
3. 採用した段階と理由
4. **採用しなかった段階と理由 (← 最も価値ある情報、スキルの学習材料)**
5. 思想憲章のどの項目が特に効くか
6. 段階間の依存関係 (DAG 図)
7. 既知の限界

### 7.3 整合性テスト

`tests/test_examples.py` で 5 層の不変条件を保証:

**Layer 1: schema validity**
- `examples/<name>/.quality-system/` が `qgb validate` を通る

**Layer 2: curated gate.json conformance**
- `evidence/.../gate.json` が curated gate schema (strict) を満たす

**Layer 3: cross-file integrity (Step 5 が破ってはならない契約)**
- `req-meta.stages[].stage_id` ⊂ `policy.stages[].id`
- `req-meta.contract_ref` が実在
- 各 contract の `req_id` / `stage_id` / `verification_type` が policy / meta と一致
- contract が policy の `required_contract_fields` をすべて含む
- `gate.stages[]` が REQ メタの段階選択順と同じ
- `gate.stages[].verification_type` が policy と一致
- `gate.stages[].contract_ref` が REQ メタと一致
- `gate.status == gate.decision.result` (ALLOW/DENY 同期)
- ALLOW のとき `failed_stage == ""` かつ全 stage `passed`
- `basis[]` が `REQ-*` + `POLICY-<policy_id>` + 各 `CONTRACT-<REQ>-<stage>` を含む
- `paths.run_dir` の末尾 timestamp が `timestamp_utc` と一致
- `timestamp_utc` (compact) と `timestamp_rfc3339` (`:` あり) が同一時刻
- `paths.curated_latest_dir` が canonical layout
- `stages[].log_ref` が実在ファイル

**Layer 4: contract claims hold on actual target**
- `verification_type: file_exists` の `target` が実在
- `verification_type: substring_match` の `must_contain[]` が target に実際に含まれる

**Layer 5: design-notes.md required content**
- 推奨レンジ言及、採用しなかった段階セクション
- 必須トップレベル見出し: 対象系の特徴 / 段階数の決定根拠 / 採用した段階と理由 / 採用しなかった段階と理由 / 思想憲章のどの項目が特に効くか / 段階間の依存関係 / 既知の限界

これにより設計例の腐敗を CI で検出できる。Layer 3 は Step 5 で qgb run を実装するときに守るべき契約でもある。

### 7.4 gate.json 内 timestamp / run_id 規約 (Step 5 三次補修で導入、四次補修で確定)

| フィールド | 形式 | 用途 |
|---|---|---|
| `timestamp_utc` | `YYYY-MM-DDTHHMMSSZ` (`:` なし、Z 終端) | wall-clock truth (秒精度)、ファイル名互換 |
| `timestamp_rfc3339` | `YYYY-MM-DDTHH:MM:SSZ` (`:` あり) | ツール互換、解析しやすい |
| `run_id` | `r[0-9a-f]{4}` かつ `not r0000` (`r0001`〜`rffff`) | 同秒内の衝突を吸収する monotonic counter |
| `paths.run_dir` (末尾) | `<timestamp_utc>-<run_id>` (schema pattern で形状を強制) | 揮発側 run-dir のディレクトリ名 |

時刻 2 系統は **同一時刻** を表現する。`run_id` は時刻とは独立で、同秒に複数 run が走ったときの差分だけを担う。

- 単一の `datetime.now(timezone.utc)` 呼び出しから両形式を生成 (`evidence.make_timestamps`)
- `paths.run_dir` の末尾は **`<timestamp_utc>-<run_id>`** 形式で、両 schema (`gate.schema.json` / `gate.runtime.schema.json`) の `paths.run_dir.pattern` が形状を強制する (Step 5 四次補修)
- `evidence._reserve_run_dir` が atomic に `mkdir(exist_ok=False)` で予約しながら `run_id` をインクリメントする (`r0001` → `r0002` → ...)。`timestamp_utc` は前進させない (Codex 二次レビュー RR2 への対応、三次補修で実装)
- `r0000` は **予約値** で実装は生成しない。`gate.schema.json` の `not: {const: "r0000"}` で外部生成 gate.json も含めて拒否 (Codex 三次レビュー RRR1 への対応、四次補修)
- 65,535 個 (`rffff`) 全て埋まると `RunDirReservationError` で停止し、silent な schema 違反を防ぐ
- `tests/test_examples.py::test_gate_timestamps_are_mutually_consistent` が CI で `<timestamp_utc>-<run_id>` 整合性を検証

### 7.5 basis[] 規約 (Step 5 への申し送り)

`basis[]` は採用判定の根拠となる文書群の id を列挙する。Phase 1 の最小形式:

- `REQ-<...>`: 採用 REQ id (要件定義書 §F-011 の REQ id 形式)
- `POLICY-<policy_id>`: `policy.json` の `policy_id` (デフォルトは `POLICY-default`)
- `CONTRACT-<REQ>-<stage_id>`: 各採用段階の contract (`req-meta` の `stages[].stage_id` ごとに 1 件)

Step 7 の knowledge 連携 (`waived` 段階の knowledge.jsonl 参照など) ではここに `KNOWLEDGE-<id>` も加わる予定。

## 8. qgb run の責務 (Step 5 確定)

### 8.1 縦串構成 (モジュール分割)

`qgb run` は 5 つの責務を持つモジュールに分割される。各モジュールは P9 (単一責任) を実装側に降ろした単位:

| モジュール | 責務 |
|---|---|
| `qgb/core/loader.py` | `config.json` / `policy.json` / `<REQ>.meta.json` / `<contract>.json` の存在確認 + JSON parse。スキーマ検証は行わない |
| `qgb/core/preflight.py` | READY/NOT_READY 判定。Step 5 三次補修で 5 関数に分割: `validate_schema_sources` (スキーマ違反 + 必須正本欠落) / `inspect_policy_graph` (policy stages の DAG + dangling) / `resolve_adopted_stages` (REQ meta の `stage_id` 解決 + `contract_ref` resolve + `verification_type` 一致 + `depends_on_order_violation`) / `check_runtime_support` (Phase 1 runnable 限定 + `manual_check_required`) / `run_preflight` (上記の薄い orchestrator)。`PreflightIssue.severity` は Phase 1 では全件 `"blocker"`、Step 6 で `"warning"` を validate-policy が初使用予定 |
| `qgb/core/runner.py` | 採用段階を 1 件ずつ実行し `StageResult` を返す。`depends_on` 失敗時は実行スキップ (failed 記録) |
| `qgb/core/decision.py` | 採用段階の結果から `ALLOW` / `DENY` + `failed_stage` (最初の失敗段階) を決定 + phase 別の `decision.meaning` を選択。Phase 1 は全 adopted stage を判定対象とする (`required` は schema で `const: true` に固定、二次補修 MR3) |
| `qgb/core/evidence.py` | `gate.json` + `summary.md` + `stages/<id>.log` を採用側と揮発側の両方へ書き出し。`build_basis()` と `make_timestamps()` を提供。`QGB_KEEP_RUNS` による prune |

CLI (`qgb/cli.py`) はこれらを直列に呼ぶだけのオーケストレータ。各モジュールは互いに直接結合せず、`AdoptedStage` / `StageResult` / `Decision` / `Timestamps` のデータクラスで疎結合する。

### 8.2 入力

```
python -m qgb run <REQ-ID> [--path DIR] [--phase {red,green,refactor,verify}] [--json]
```

- `REQ-ID` 必須位置引数
- `--path` default `.`、存在しない / ファイル指定 → exit 64
- `--phase` default `verify`。Phase 1 では verify 以外も `decision.meaning` のテンプレートだけ切り替わる (実セマンティクスは Step 7 で `red` を本実装)
- `--json` 指定時は機械可読 JSON を stdout、stderr は完全に空

### 8.3 終了コード

| コード | 意味 | 出力 |
|---|---|---|
| 0 | ALLOW | curated + volatile gate.json/summary.md/log を書き出し、stdout に要約 |
| 1 | DENY | 同上 (status=DENY)、stderr に要約 |
| 2 | NOT_READY (preflight rejected) | gate.json を **生成しない**。stderr に preflight issues を列挙 |
| 64 | CLI usage error (path 不在等) | stderr のみ |

NOT_READY が curated を上書きしないことは、Step 5 受入テスト `test_run_returns_not_ready_when_contract_ref_missing` で保証している (例の手書き `gate.json` の `timestamp_utc` が変化しないことを確認)。

### 8.4 preflight 検査内容 (Phase 1 必須)

`qgb run` が走る前に必ず通る。Step 6 `qgb validate-policy` でも同じモジュールを共有することを想定:

1. `qgb.core.validate.run_validate` 実行 (スキーマ違反 + §F-005 contract field 混在)
2. `.quality-system/config.json` / `policy.json` の存在
3. `<REQ-ID>.meta.json` の存在
4. policy.stages の `depends_on` が DAG (dangling reference + cycle 検出)
5. REQ meta の `stage_id` が policy.stages に存在
6. REQ meta の `contract_ref` が実ファイルに resolve (project_root 外への escape は拒否)
7. contract の `verification_type` が policy の同段階と一致
8. `manual_check` を `required: true` で含む REQ は拒否 (P6)
9. Phase 1 runnable: `file_exists` / `substring_match` のみ。他は `unsupported_verification_type` で拒否
10. 採用 required 段階が 1 件以上存在 (P1)

報告は `PreflightIssue.kind` で機械分類:
`schema_violation` / `missing_required_file` / `invalid_json` / `unknown_stage_id` / `missing_contract` / `depends_on_unknown` / `depends_on_cycle` / `unsupported_verification_type` / `manual_check_required` / `no_required_stages` / `verification_type_mismatch`

### 8.5 verification_type 実装

#### file_exists

- `contract.target` を `loader.resolve_project_relative()` で resolve (project_root 配下に限定)
- `Path.is_file()` で判定 (シンボリックリンク先がファイルなら True)
- 結果ログに `resolved:` 絶対パスを記録 (P7 再現可能な証跡)
- project_root 外への path escape は failed として記録 (Step 5 補修 R1)

#### substring_match

- `contract.target` を `loader.resolve_project_relative()` で resolve
- UTF-8 で読み込み
- `contract.must_contain` (list[str]) の各要素について包含確認
- 各 keyword の char offset をログに記録 (`'hello': found at char offset 0` 形式)。`str.index()` が返すのは UTF-16 code unit index (Python の str 内部表現上の位置) なので、Step 6a Commit 3 で "byte offset" 表記から "char offset" 表記に修正。本物の UTF-8 byte offset は Phase 2 以降の richer log の課題
- UTF-8 decode 失敗時は failed
- project_root 外への path escape は failed として記録 (Step 5 補修 R1)

両 type とも `exit_code` は `null` (外部プロセス非起動)。target の root escape チェックは `loader.resolve_project_relative()` を `contract_ref` と共有することで、契約パスと検査対象パスの両方が「project 内部のみ」という不変条件を一箇所で守る (P9 / NF-007)。

二次補修 (MR2): `resolve_project_relative()` は **絶対パスを明示的に拒否**する。docstring と実装の不一致 (旧版は「absolute path も拒否」と書きつつ実装は relative_to() だけで判定) を解消。`contract_ref` (REQ メタ) 中の絶対パスは preflight で NOT_READY に、`contract.target` 中の絶対パスは runner で stage failed として扱う (DENY)。これにより contract が project-rooted relative path だけを受け入れる入力契約が明確になる (P9)。

### 8.6 depends_on の扱い (Phase 1)

- 採用段階を REQ meta 宣言順で実行
- 各段階の実行前に `depends_on` のうち failed なものがあれば、その段階を実行せず `failed` 記録 (log 中に `skipped: predecessor stage <id> failed` と明示)
- これにより gate.schema.json の DENY 制約 (「少なくとも 1 stage が failed」) が自然に満たされる
- DAG 検査は preflight で済んでいるので runner はトポロジカルソート不要 (REQ meta 順 = 設計者の意図順)

### 8.7 timestamp 生成 (詳細)

`qgb.core.evidence.make_timestamps()`:

- 単一の `datetime.now(timezone.utc).replace(microsecond=0)` から両形式を生成
- `compact` = `%Y-%m-%dT%H%M%SZ` (Windows でパス segment に使えるよう `:` を含まない)
- `rfc3339` = `%Y-%m-%dT%H:%M:%SZ` (ツール互換)
- `paths.run_dir` の最末尾サフィックスは必ず `compact` と一致 (`test_examples.py::test_gate_timestamps_are_mutually_consistent` で CI 検証)
- テストでは `monkeypatch.setattr(evidence, "make_timestamps", ...)` で固定値注入が可能

#### 同一秒衝突回避 (Step 5 補修 R2 → 二次補修 RR1 → 三次補修 RR2/MR1 → 四次補修 RRR1/RRR2 で完結)

`evidence._reserve_run_dir(runs_root, timestamps)` が `write_evidence` の前段で動く:

- `mkdir(parents=False, exist_ok=False)` を予約操作として使う **atomic な reservation**。check-then-create race を構造的に排除 (Codex 二次レビュー RR1)
- 衝突時は `timestamp_utc` を進めず、**`run_id` を `r0001` から順にインクリメント**して `<timestamp>-<run_id>` で再予約 (Codex 二次レビュー RR2: synthetic timestamp は実時刻を歪めるため廃止)
- 戻り値は `(予約済 run_dir, 確定 run_id)` のタプル。`Timestamps` は実時刻のまま gate.json に焼かれる
- `r0001`〜`rffff` (65,535 個) を使い切ったら `RunDirReservationError` を投げて停止 (旧版の microsecond サフィックス fallback は curated `timestamp_utc` regex を破るリスクがあったため廃止、Codex 二次レビュー MR1)
- `r0000` は予約値で実装は生成しない。schema 側に `not: {const: "r0000"}` を加えて外部生成 gate も含めて拒否 (Codex 三次レビュー RRR1、四次補修)
- `paths.run_dir` の末尾形状を schema の `pattern` で縛り、`<timestamp_utc>-<run_id>` 以外の任意 payload が curated/runtime のいずれにも紛れ込まないようにした (Codex 三次レビュー RRR2、四次補修)

これにより:

1. 同一プロセスの連続実行・並行プロセスの同秒実行いずれでも、各 run_dir が独立し過去 run の証跡が上書きされない (P7)
2. `timestamp_utc` / `timestamp_rfc3339` は常に wall-clock truth であり、証跡の解釈可能性が保たれる (P7)
3. `paths.run_dir` の末尾は schema レベルで `<timestamp_utc>-<run_id>` 形状を強制、外部生成 gate.json も同一規則に従う必要がある (P9: 入力契約の明確化)
4. `r0000` は schema レベルで予約され、実装の生成範囲と schema の受理範囲が完全に一致 (Codex 二次レビュー追加チェック項目 #1 を完結)

### 8.8 basis[] の生成 (詳細)

`qgb.core.evidence.build_basis(req_id, policy, adopted)`:

```python
[
    req_id,                                          # "REQ-APP-001"
    f"POLICY-{policy.get('policy_id', 'default')}",  # "POLICY-default"
    *(f"CONTRACT-{req_id}-{stage.stage_id}"          # 採用段階順
      for stage in adopted),
]
```

- `policy_id` が無い / 文字列でない場合は `default` フォールバック
- Step 7 で `KNOWLEDGE-<id>` 追加予定 (`waived` 段階で参照した knowledge エントリ)

### 8.9 2 系統出力の規約

| 系統 | パス | 書き手 | コミット対象 |
|---|---|---|---|
| 揮発 | `.quality-system/artifacts/<REQ>/runs/<compact>/` | `qgb run` | **No** (`.gitignore`) |
| 採用 | `.quality-system/evidence/<REQ>/latest/` | `qgb run` のみ | **Yes** |

両系統に書く内容:

- `gate.json` (採用は strict schema、揮発は permissive runtime schema)
- `summary.md` (両者同一内容)
- `stages/<stage_id>.log` (両者同一内容)

Phase 1 では揮発と採用の gate.json は **byte-for-byte 等価**。違いは置く場所だけ。次のステップで揮発側に追加情報 (full environment dump 等) を載せる余地のために schema は permissive。

採用側の `stages/` ディレクトリは **書き出し前に内容を消す**。以前の run で存在し今回採用されなくなった段階のログが取り残されることを防ぐ。

### 8.10 QGB_KEEP_RUNS

- 環境変数で揮発側 `runs/<compact>/` の保持件数を制御
- default: 10
- 不正値 / 未設定 → default、min 1
- `<runs_dir>` を timestamp 名で lexical sort = chronological sort なので、古い順に削除
- 採用側は対象外 (常に最新 1 件)

### 8.11 例: generic-minimal で ALLOW が出る縦串

```text
$ python -m qgb run REQ-APP-001 --path examples/generic-minimal
ALLOW: REQ-APP-001 (phase=verify)
  meaning: Defined checks passed. This is not proof of total correctness.
  run_dir: .quality-system/artifacts/REQ-APP-001/runs/2026-05-21T120000Z
  curated_latest_dir: .quality-system/evidence/REQ-APP-001/latest
  stages:
    - S1 (file_exists): passed
    - S2 (substring_match): passed
```

`examples/generic-minimal/` の手書き `gate.json` は Step 4 で固定された **リファレンス出力**。Step 5 完了時点で生成される `gate.json` は、timestamp 部分を除いて構造的に同等であることを `tests/test_run_generic_minimal.py::test_curated_gate_matches_reference_structure` で検証している。

## 9. Python 実装規約 (Step 0〜2 確定)

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

## 10. テスト規約 (Step 0〜5 確定)

### 10.1 テスト件数の現状

- Step 0: 11 件 (CLI smoke + subprocess)
- Step 1: 51 件追加 (Schema 検証)
- Step 2: 37 件追加 (validate コマンド) → 巻き戻し後 24 件
- Step 3: 20 件追加 (qgb init)
- Step 4: 18 件追加 (examples/generic-minimal 整合性)
- Step 5: 17 件追加 (qgb run 縦串)
- Step 5 補修: 5 件追加 (R1 root escape × 2、R2 同秒衝突 × 2、R3 optional ALLOW × 1)
- Step 5 二次補修: 5 件追加 / 1 件差し替え (RR1 atomic reservation × 2、MR2 absolute path × 2、symlink × 1、MR3 const:true × 2、optional ALLOW テストを required=false NOT_READY に置換)
- Step 5 三次補修: 12 件追加 (run_id regex × 8、run_id required × 1、preflight helpers × 1、severity default × 1、M1 depends_on order × 1)、同秒衝突テスト 3 件を logical-timestamp → run_id 採番方式に書き換え
- Step 5 四次補修: 8 件追加 (r0000 reject × 1 を curated parametric に追加 + runtime r0000 reject × 1、paths.run_dir suffix pattern parametric × 6)

合計 **204 件、全成功、ruff 警告ゼロ**。

### 10.2 fixture の責務分離

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

### 10.3 subprocess テストの規約

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

## 11. 思想憲章との対応マトリクス (Step 0〜5 範囲)

| 思想項目 | 実装での機械化 |
|---|---|
| P1 品質=要求を満たすこと | REQ メタの schema が `req_id` と `stages[]` を必須化。preflight で `no_required_stages` を拒否 |
| P5 ALLOW/DENY の意味の限定 | gate.schema.json で `decision.meaning` を必須化、if/then で `status` × `decision.result` × `failed_stage` × `stages[].result` の整合性を強制。`decision.py` で phase 別の `meaning` テンプレートを限定供給 |
| P6 LLM 単独 ALLOW 禁止 | preflight が `verification_type=manual_check` を required 段階で含む REQ を `manual_check_required` で NOT_READY に落とす (Step 5) |
| P7 再現可能な証跡 | gate.schema.json で `runner.name/version`、`timestamp_utc`、`timestamp_rfc3339`、`stages[].contract_ref`、`stages[].log_ref`、`basis[]` を必須化。`evidence.py` で採用/揮発の 2 系統に書き出し、`make_timestamps` を単一 datetime から両形式生成 |
| P8 外部取得コンテンツはプロンプトでない | knowledge.schema.json の `requires_human_review` フィールド |
| P9 単一責任原則 | policy.schema.json で `responsibility` 必須化。CLI コマンド体系でも `validate` / `validate-policy` / `run preflight` の責務分離を維持 (Step 2 巻き戻しの根拠)。Step 5 で `loader` / `preflight` / `runner` / `decision` / `evidence` の 5 モジュール分割 |
| NF-004 可搬性 | UTF-8 強制 (subprocess test)、非 ASCII を CLI help から除去。`timestamp_utc` を `%H%M%S` で組み立て Windows パス segment 互換 |
| NF-007 安全性 | contract.schema.json の `command` を argv 配列限定。`loader.load_contract` で project_root 外への path escape を拒否 |
| NF-010 依存最小化 | jsonschema 以外を runtime 依存に加えない。date-time format checker を `rfc3339-validator` ではなく stdlib (`re` + `datetime`) で自前実装。Step 5 runner も stdlib のみで実装 |

## 12. 未確定 / Step 6 以降で確定する事項

Step 5 三次補修 (2026-05-23) で C 部分 (timestamp/run_id 責務分離 + REQ meta トポロジカル順検証) と B 部分 (preflight モジュール 5 関数分割 + severity フィールド準備) を前倒した結果、本テーブルは「設計フェーズ系コマンド構築 (Step 6) のスコープに本来属する項目」と「Step 5 補修で扱いきれなかった runner/evidence 系の中小残課題」だけを残す形に整理した。

以下は本書時点では未確定。各 Step で確定し、本書を改訂する。

| 項目 | 確定予定 Step |
|---|---|
| `qgb validate-policy` 本体 + preflight 診断 API + fixture 復活 | Step 6a |
| `qgb run --yes` / runner/evidence 構造化 (atomic / QGB_KEEP_RUNS) + `qgb verify` 撤回 | Step 6b (完結 2026-05-31) |
| ~~`qgb detect` + adapters/python + adapters/generic~~ | Step 6c (完結 2026-05-31) → **Phase 3 Step 3.0 (2026-06-21) で撤去**、§14 参照 |
| `qgb design-stages` 提案・採用 + `qgb scaffold` | Step 6d (完結 2026-05-31) |
| TDD phase=red の expected-failure 本実装 (gate.json で DENY を期待値として扱う) | Step 7 (完結 2026-05-31) |
| `command` verification_type | Step 7 (完結 2026-05-31) |
| `json_schema` verification_type | Step 8 (完結 2026-06-01) |
| `manual_check` を含む REQ への注釈フロー (Phase 2 設計の入口) | Step 7 (完結 2026-05-31) |
| `waived` 段階の knowledge.jsonl 記録 + `basis[]` への `KNOWLEDGE-*` 追加 | Step 7 (完結 2026-05-31) |
| 設計例パック 2 例追加 (python-cli-pytest / markdown-docs) | Step 8 (完結 2026-06-01) |
| knowledge 追加コマンド、導入マニュアル、依存調査ポリシー文書 | Step 9 (完結 2026-06-01) |

### Step 6 サブステップ計画 (Codex 計画レビュー 2026-05-23 採用版)

Step 6 は規模が Step 1〜5 全体に匹敵するため、4 サブステップに分割して進める。各サブステップ完了時に Codex レビュー → 補修サイクル。

着手順は **6a → 6b → 6c → 6d**。理由は「validate-policy が後続全部の検査土台で、API が確定しないと design-stages も書けない」「6a の preflight 既存資産が一番多く新規実装が少ない」。

> 当初の Step 6b には `qgb verify` 実装が含まれ「verify が preflight API の最初の消費者になる」と位置づけていたが、Step 6b 着手時の spec-review で `qgb verify` の撤回が決まった (思想憲章 P3 との緊張、`stage-design.md` §3.1)。Step 6b は `qgb run --yes` / runner・evidence の構造化 (atomic / QGB_KEEP_RUNS) と verify 撤回の spec 反映に絞られる。

#### Step 6a — validate-policy / preflight 診断 API (本体 3 コミット + 補修 1 次 + 補修 2 次完了、**Step 6a 完結**)

**スコープ (本体 3 コミット):**

- `qgb validate-policy` 本体 (stage-design.md §11 の検査表すべて。blocker は exit 2、warning のみは exit 0 + stderr 通知、--json で機械可読出力)
- preflight 診断 API (Commit 1):
  - 主 API は **severity filter 付き iteration** (`report.iter_issues(severity=...)`)
  - 便利メソッドとして `report.blocking_issues()` / `report.warnings()` / `report.has_blockers()`
  - `report.ready_for_run()` は run 用の意味を含むので runner 専用、validate-policy では `has_blockers()` を使う (P9)
  - `ready()` は Step 5 までの後方互換として `ready_for_run()` に委譲
- preflight 新規検査 (Commit 2):
  - `duplicate_stage_id` (blocker, P9): policy.stages の id 重複
  - `misplaced_contract` (blocker, P7): contract_ref が canonical layout (`.quality-system/contracts/<REQ>/<stage>.json`) に従わない
  - `missing_contract_field` (blocker, P9): policy.stages[].required_contract_fields が contract.json に欠落
  - `stage_count_out_of_range` (warning, P9): 段階数が推奨レンジ 3..7 を外れる (Phase 1 初の warning 実コード使用、generic-minimal の 2 段階で実例)
  - `wrong_type` (blocker, Codex L3): LoaderError.wrong_type を missing_contract から分離
- `check_runtime_support(adopted, report, *, mode: Literal["run", "validate_policy"])` (Commit 2):
  - `mode="run"`: `manual_check_required` / `unsupported_verification_type` を blocker
  - `mode="validate_policy"`: 同じ findings を warning ("policy 自体は malformed ではない、Phase 1 runtime が未対応というだけ")
- `validate_policy_preflight(project_root, req_id=None)` 新規 entry point (Commit 2): `run_preflight` と同じ helper を別の short-circuit で組み立てる
- fixture 復活 (Commit 3): `tests/fixtures/validate_policy/{missing_required, dangling_ref, misplaced_contract}/` を **validate-policy の仕様固定装置** として位置づけ。各 fixture が `kind` と `severity` を期待通り返すことを 6a の完了条件として CLI 経由でテスト
- substring_match のログ表記 (Codex L2): "byte offset" → "char offset" に修正 (Python str は code point の列、本物の UTF-8 byte offset は Phase 2 以降)

**補修 1 次 (Codex レビュー反映):**

- **M1** misplaced_contract と wrong_type の優先順位を仕様化: canonical-layout 検査を path 解決より **先** に走らせる設計を `resolve_adopted_stages` の docstring に明記。これにより contract_ref 経由の `wrong_type` は「canonical 文字列に合致したうえで symlink で root を escape する」極めて狭い経路でしか出ない (絶対パスや `..` 相対パスはすべて `misplaced_contract` が先勝ち)。テスト名と docstring でこの spec をロックし、新規に `..`-relative ケースのテストも追加。理由: 文字列マッチによる診断は I/O 不要・ファイルシステム状態に非依存で安定、かつ designer に最小の修正 (rename/move) を指せる (P9: 各エラーは最小の修正を指せ)。**ただしこの順序は本ケース限定の judgment** (Codex 二次レビューの minor 指摘反映): "cheaper diagnostic first" を全検査の一般原則に持ち上げると、安全性・曖昧性・後続診断の信頼性が絡む場面で誤った最適化になりうる。canonical layout 違反は textual に決定的かつ後続診断を汚染しない、という条件が揃ったときの選択肢として扱う。M2 (graph integrity blocker での short-circuit) はむしろ「後続診断を汚染しないために diagnostics を抑制する」逆方向のトレードオフであり、本系統では併存する
- **M2** graph integrity blocker (`duplicate_stage_id` / `depends_on_cycle`) があるとき adopted resolution を short-circuit する `_has_graph_integrity_blockers` ヘルパーを導入。`run_preflight` と `validate_policy_preflight` 両方で `inspect_policy_graph` 直後に呼ぶ。理由: duplicate id があると `policy_stages` map は最初の出現を silent に選ぶ、cycle があると `depends_on_order_violation` 診断は ill-defined。二次診断が一次診断と矛盾しうる状態を作らない (P9 が要求する診断の安定性)。`depends_on_unknown` は意図的にこの集合に **含めない** (一部 dangling でも per-stage 診断は意味を持つため)。**validate-policy にも同じ short-circuit を適用する設計判断** (Codex 二次レビューの major 指摘反映): `qgb validate-policy` は通常「できるだけ多くの設計診断を返す」役割を担うが、それは各診断が単独で正しいときに限る。`duplicate_stage_id` 配下の per-stage 診断は曖昧な stage 定義を指し、`depends_on_cycle` 配下の順序系診断は意味を失う。誤った/不安定な findings を正しい一次 finding に重ねるとフィードバック品質が劣化するため、integrity blocker を先に修正させてから validate-policy を再実行する運用を選ぶ
- **m1** `runner.py` のコメント修正: "UTF-16 code unit" → "Python code point index" (Python の `str` は内部表現に依存しない code point 列、Python が UTF-16 vs UCS-4 を露出させていないことを明記)
- **m3** detailed-design に CLI 出力規約を追記: 機械処理は `--json` + exit code を正とする運用。`warning -> stderr` は advisory の見落としを防ぐが「stderr が出たら失敗」扱いの CI wrapper との衝突を避けるための運用注記

**テスト件数:** 204 (Step 5 完結時) → 234 (Step 6a 本体完了) → **238** (補修 1 次完了)
- Commit 1: +3 件 (preflight API テスト)
- Commit 2: +16 件 (新 issue kind + severity 振り分け)、既存 2 件を warning 混在に追随
- Commit 3: +11 件 (validate-policy CLI + fixture)
- 補修 1 次: +4 件 (dotdot misplaced spec lock + M2 short-circuit 3 件)、既存 absolute-path テストを spec 明記名にリネーム + symlink テスト名を明確化

**CLI 出力規約 (Step 6a 補修 1 次で確定):**

- `validate-policy` / `run` / `validate` / `init` の機械処理は **必ず `--json` を使う**
- 機械判定は **exit code を正とする** (0=OK, 1=DENY, 2=NOT_READY, 64=USAGE)
- text 出力は人間向け diagnostic: blocker は stderr、warning は stderr (advisory の silent 化を防ぐ)、OK は stdout
- 「stderr に何か出たら失敗」扱いの CI wrapper はこの規約と衝突するので、`--json` 経由で `summary.blockers` / `summary.warnings` を見る運用に統一する
- `qgb run` の text 出力で ALLOW を stdout、DENY を stderr に分けているのも同じ理由

#### Step 6b — run 周辺 (verify 撤回後、**完結 2026-05-31**)

**スコープ (実装順、全て完了):**

0. `qgb verify` 撤回の spec 反映 + cli.py stub 削除 — 完了 (`b9029ab` / `fedb106`)
1. `qgb run --yes` (実行前確認プロンプト) — 完了 (`980c733`)
2. `_replace_dir_contents()` の atomic 化 (Codex M4 / M5): `latest.tmp-<run_id>` で書いて rename — 完了 (`e19a8b5`)
3. `QGB_KEEP_RUNS` 不正値の warning (Codex L4) — 完了 (`234177e`)

詳細な作業記録 (Codex 横断レビュー指摘の三分類: 対応 / Phase 2 / docstring out-of-scope) は `journal/phase1-step6b.md`。テスト 238 → 266 件、ruff clean。

> 当初の Step 6b は `qgb verify` を最初に実装し「preflight API の最初の消費者」とする計画だったが、着手時の spec-review で verify 撤回が決まった (P3 との緊張)。これにより Step 6b は run の採用フロー整備 (--yes / atomic / QGB_KEEP_RUNS) と verify 撤回の反映に絞られた。「部分検証は REQ 分割で解く」という設計指針は §3.1 / stage-design §3.1 / 要件 F-008 に明記済み。

#### Step 6c — detect / adapters (**完結 2026-05-31**)

**スコープ (全項目完了):**

- adapters/python, adapters/generic の 2 種で起動 — 完了
- adapter base 規約 (`detect()` の返り値型を含む) — 完了
- `DetectedProjectProfile` 的なデータ境界を固定: `language` / `framework` / `test_runner` / `confidence` / `evidence[]` — 完了
- 補修: `DetectionResult(selected, candidates)`、JSON `schema_version=1`、OSError ガード、`adapter.name` での control flow、unreadable/empty 区別 — 完了
- **重要 (P9 維持):** `validate-policy` は「採用済み policy が妥当か」を見る、`detect` は「候補 stage を提案する材料」を返す。両者のロジックを混ぜない — 維持

詳細な作業記録 (計画 Codex 相談 → 本体 → 横断レビュー 8 件吸収 → 本体 1 コミット) は `journal/phase1-step6c.md`。本体 commit `0a77ca2`。テスト 266 → 327 件、ruff clean。

#### Step 6d — design-stages / scaffold (**完結 2026-05-31**)

**スコープ (全項目完了):**

- `qgb design-stages` 提案フェーズ (Phase 1: ルールベース推定 + ユーザー確認、stage-design.md §10.1) — 完了
- `qgb design-stages --commit` 採用フェーズ (`policy.json` に書き込み + `validate-policy` を内部で呼ぶ) — 完了 (atomic swap)
- `qgb scaffold REQ-APP-001` (REQ + contract + テスト雛形生成) — 完了 (schema-valid placeholder)
- examples は最小 1 件のみ (重い設計例パック化は Step 7 / 8 送り) — 維持 (generic-minimal のみ)
- 既存ファイルがある場合の挙動 (idempotency) を 6d の完了条件に含める — 完了 (refuse + --force)

詳細な作業記録 (計画 Codex 相談 → 本体 → 横断レビュー 9 件のうち中以上 6 件吸収 → 本体 1 コミット) は `journal/phase1-step6d.md`。本体 commit `a1e8cf4`。テスト 327 → 366 件、ruff clean。

**Step 6 全体完結 (2026-05-31):** 6a / 6b / 6c / 6d 全て完了。Phase 1 必須コマンド (init / detect / design-stages / scaffold / validate / validate-policy / run) が全揃い。受け入れ条件§12 のうち 24 件中 14 件達成、残 10 件は Step 7-9 で消化予定。

#### Step 7 — TDD phase=red / command runner / manual_check NOT_READY / waived (**完結 2026-05-31**)

**スコープ (全項目完了):**

- A: TDD phase=red の expected-failure 本実装 (受け入れ条件 14) — 完了
- B: `command` verification_type 実装 — 完了 (`subprocess.run` shell=False, env 全継承, stdin=DEVNULL, 64 KiB tail-truncate, timeout)
- C: `manual_check` を含む REQ → NOT_READY (受け入れ条件 15) — 完了 (Step 6a の preflight が既達、Step 7 でテストロック)
- D: `waived` 段階 + `knowledge.jsonl` + `KNOWLEDGE-*` basis (受け入れ条件 16) — 完了 (preflight / runner / decision / basis / knowledge.jsonl の 5 層整合)

Codex 横断レビューで Phase 1 致命的な漏れ 4 件 (実メモリ cap / TimeoutExpired bytes / 非 UTF-8 decode / knowledge.jsonl 末尾 partial) を本体に吸収。詳細は `journal/phase1-step7.md`。本体 commit `ace1c0e`。テスト 366 → 406 件、ruff clean。

**受け入れ条件§12 進捗:** Step 7 完結時点で 17/24 件達成 (Step 6 完結時 14 件 + Step 7 で 14/15/16 達成、23 は既達確認)。残 6 件 (17/18/19/20/21/24) は Step 8-9 で消化予定。

#### Step 8 — json_schema verification_type + 設計例パック 2 例追加 (**完結 2026-06-01**)

**スコープ (全項目完了):**

- A: `json_schema` verification_type 実装 — 完了 (target / schema を R1 解決、$ref present は failed、format は Phase 1 では強制有効化しない)
- B: examples/python-cli-pytest 構築 — 完了 (3 stages: command + command + substring_match)
- C: examples/markdown-docs 構築 — 完了 (3 stages: file_exists + substring_match + json_schema)

3 example で Phase 1 の 4 runtime-supported verification_type (file_exists / substring_match / command / json_schema) を網羅。manual_check は受け入れ条件 15 で NOT_READY なので example には含めない。

memory review-process 段 1〜5 完走: 観点別 5 subagent → 集約 → Codex 横断 → 補修 → 収束ループ (2 周目で「指摘なし収束」)。

Codex 横断レビュー指摘 (主なもの):
- W1 (resolved path log) / C1 (validator defensive) / C2 (sort key) → 本体補修
- W2 (Windows backslash) / W3 (Windows python argv) / Ph1 (pytest 実時間) → docs 対応 (README / design-notes に明文化)

Codex 段 5 1 周目で新規 finding (C2 再: int/str 混在で TypeError) → 2 周目で `str(p) for p in e.absolute_path` に修正、「指摘なし収束」を受領。

詳細な作業記録は `journal/phase1-step8.md`。本体 commit `dd1f053`。テスト 406 → 448 件、ruff clean。

**受け入れ条件§12 進捗:** Step 8 完結時点で **18/24 件達成** (Step 7 完結時 17 件 + Step 8 で 19 達成)。残 5 件 (17/18/20/21/24) は Step 9 で消化予定 (Step 9 完結で Phase 1 全体達成)。

#### Step 9 — knowledge / requires_human_review / 導入マニュアル / 依存ポリシー / skills/source/ (**完結 2026-06-01、Phase 1 完結**)

**スコープ (全項目完了):**

- A: 受け入れ条件 17 (Project Knowledge Base ユーザー明示情報保存) — 完了 (qgb validate に knowledge.jsonl line-by-line validation を追加、partial-tail tolerant)
- B: 受け入れ条件 18 (requires_human_review) — 完了 (knowledge.schema.json の allOf で `source_type=external → requires_human_review:true` を const enforce、P8 機械化)
- C: 受け入れ条件 20 (導入マニュアル) — 完了 (development/docs/phase1-manual.md、spec §8.1 19 章 + §8.2 PowerShell verbatim block)
- D: 受け入れ条件 21 (依存ポリシー / セキュリティ手順) — 完了 (development/docs/security-dependency-policy.md、§6.6.2 11 項目 + jsonschema 実例 + platform 別 binary)
- E: 受け入れ条件 24 (skills/source/ 構造予約) — 完了 (skills/source/README.md、F-019 中間表現 + Phase 5 計画)

memory review-process 段 1〜5 完走: 観点別 5 subagent → 集約 → Codex 横断 → 補修 → 収束ループ 2 周で「指摘なし収束 + Phase 1 完結」を受領。

Codex 横断レビュー指摘 8 件 (blocker 0、major 2、minor 4、clean 2 観点):
- S1 (spec §8.2 verbatim block) / W3 (venv aliasing) / C1 (BOM) / W4 (platform binary) → 本体補修
- W1 (CRLF/BOM docstring) → 実装無変更で docstring
- W2 → 対応不要

詳細は `journal/phase1-step9.md` (Phase 1 全体振り返り付き)。本体 commit `9d7196f`。テスト 448 → 470 件、ruff clean。

**受け入れ条件§12 進捗:** Step 9 完結時点で **24/24 件達成 → Phase 1 全体完結**。

#### 規模感 (Step 5 を 1.0 とした相対値、Codex 計画レビュー反映後)

| サブステップ | 規模 | コミット予想 |
|---|---|---|
| 6a 検査強化 | 0.9〜1.1 | 本体 + 補修 1〜2 |
| 6b 実行系小修正 | 0.5〜0.7 | 本体 + 補修 1 |
| 6c 検出系 | 0.6〜0.8 | 本体 + 補修 1 |
| 6d 生成系 | **0.9〜1.2** | 本体 + 補修 1〜2 |

6d は生成系の「出力仕様の納得感」「既存 docs との整合」「idempotency」「既存ファイルがある場合の挙動」で補修が出やすいため、Claude 当初見積もり (0.7) より厚めに見る。

## 13. Phase 2 計画 (Codex 計画レビュー 2026-06-01 採用版)

Phase 2 の主軸は **「編集を安全にする」**。Phase 1 で確立した検証装置 (validate / validate-policy / run / decision / evidence) の上に、修正手段の構造化を載せる。adapter 量産 (Phase 3) と provider integration (Phase 4) には踏み込まない。

Codex 計画レビュー (2026-06-01) で 7 サブステップに分解。規模感は Phase 1 Step 5 を 1.0 として **6.2〜10.0** (Phase 1 全体と同等以上)。Phase 1 で確立した「観点別レビュー → 集約 → Codex 横断 → 補修 → 収束ループ」サイクルを各サブステップで再利用する。

### 13.1 着手前確定の設計境界 5 件

実装に入る前に Phase 2 全体を貫く設計境界を固定し、各サブステップで判断が揺れないようにする。

1. **Pattern B の LLM 境界** (Phase 2 全体に適用): qgb 本体は LLM を直接呼ばない。context export + proposal/patch import + validate + atomic apply の構造化 interface に徹する。LLM 側は Claude Code / Codex CLI / Gemini CLI / Phase 5 skill が担当する。
    - 理由: 依存ライブラリ追加回避 (NF-010)、秘密情報を qgb 設定に持たせない、プロバイダ差を抽象化しない、テスト困難性を本体に持ち込まない、思想 P2 (AI は探索装置) / P6 (LLM 単独 ALLOW 禁止) の境界を実装段階で曖昧化させない
    - 命名規約: `--interactive` のような自然言語匂いの UI を qgb 本体に持ち込まない。`propose-context` / `adopt` のような API 寄り命名にする
2. **JSON Patch subset**: Step 2.2 で実装する patch は `add` / `replace` / `remove` / `test` の 4 op のみ。`move` / `copy` は Phase 3 送り
3. **`qgb check` / `qgb dev` の証跡境界**: tmp artifacts は出すが (デバッグ可能性のため必須)、curated `evidence/latest/` は更新しない。tmp は `.quality-system/artifacts/<REQ>/checks/<ts>-<runid>/` に書く (Step 2.4 着手前確定 2026-06-11: 当初例示の `.qgb/tmp/check/` は「init が `.qgb/` を .gitignore 予約済み」という事実誤認に基づいていた。実際の init 予約は `.quality-system/artifacts/` のみ。check 出力は run の揮発出力と同種の「REQ に対する検証機構の出力」であり tool-private キャッシュではないため、既予約の揮発木に同居させる。境界の本質 = **curated 不変 + 揮発出力** は不変、パス字面のみ改訂)
4. **schema strict mode**: 段階的導入。Step 2.1 で format assertion + `$ref` allowlist を強制、`additionalProperties: false` は `--strict` フラグで独立 (Step 2.7 で全面適用判断)
5. **waiver 削除**: Phase 2 では `add-waiver` のみ。削除 / revoke / supersede モデルは Phase 3 送り

### 13.2 サブステップ計画

着手順は **2.1 → 2.2 → 2.3 → 2.4 → 2.5 → 2.6 → 2.7**。理由は「2.2 (JSON Patch) が 2.1 (schema strictness) の上に成り立つ」「2.5 (Pattern B) は最も設計が重く、2.1〜2.4 を踏まえてから着手する方が安全」。

#### Step 2.1 — schema baseline (**完結 2026-06-05**)

**スコープ (全項目完了):**

- format assertion **opt-in** 強制 — 完了 (Codex 計画レビュー指摘で「全面強制でなく contract.enforce_format=true で opt-in」に変更、後方互換を保護)
- `$ref` allowlist — 完了 (contract.allow_internal_ref=true のとき `#` または `#/...` の internal JSON Pointer のみ accept、anchor/絶対URI/相対URI/file URI/http URI/sibling-file は引き続き reject)
- 後方互換監査 — 完了 (既存 example 3 例 + 全 fixture が新 schema で無変更通過、既存 12 テスト全緑)
- `qgb validate-policy --strict` skeleton — **Step 2.1 では先出ししない判断** (Codex 計画レビュー指摘 5 採用、Step 2.7 で実体と同時公開)

**完了条件 (全達成):**

- format violation が runner で `enforce_format=true` のとき blocker — 達成
- `$ref` allowlist 違反が事前収集経路で reject (`jsonschema` resolver は呼ばれない) — 達成
- 既存 example / fixture が無変更で通る — 達成 (487 件全緑、Phase 1 = 470 + Step 2.1 +17)

詳細な作業記録 (Codex 計画レビュー 8 指摘吸収 → 本体 → 段 1 観点別 5 subagent (reject → memory 改定 → 再投入で完走) → 段 3 Codex 横断 → A1-A4 補修 → 段 5 Codex 2 周目「指摘なし収束」) は `journal/phase2-step2-1.md`。テスト 470 → 487 件、ruff clean。

**Step 2.2 / 2.5 / 2.7 への申し送り:**

- Step 2.2 (patch substrate): patch 適用後の validate-policy で Step 2.1 `_collect_dollar_refs` / `_is_internal_pointer_ref` 経路が走ることを確認
- Step 2.5 (Pattern B): proposal schema (`qgb/schemas/proposal.schema.json`) は Step 2.1 で確立した format / `$ref` allowlist を継承
- Step 2.7 (strictness review): `formats_checked` / `formats_ignored` の strict mode 必須化、unknown format の warning/failure 昇格、`$id` / base URI と internal-only `$ref` の関係明文化 (Codex 横断レビュー Minor 指摘)、log アサーション規約整備、`*_when_flag_default` / `*_even_when_flag_true` 命名統一、`qgb validate-policy --strict` 実体実装

**規模感:** 0.8 (Phase 1 Step 5 = 1.0 基準) で着地、Codex 計画レビューの見立て通り

#### Step 2.2 — patch substrate (**完結 2026-06-05**)

**スコープ (全項目完了):**

- JSON Patch subset (`add` / `replace` / `remove` / `test`) の実装 — 完了 (stdlib のみ、`qgb/core/patch.py` + `qgb/core/json_pointer.py`)
- atomic apply 基盤 — 完了 (Phase 1 Step 6d / Step 7 で確立した sibling tmp + `os.replace` pattern を継承、`qgb/core/patch_apply.py`)
- validate-policy integration — 完了 (**案 X**: `validate_policy_preflight` に in-memory override seam (`policy_override` / `req_meta_override` / `contract_overrides`) を追加、disk 痕跡ゼロで検査)
- `qgb patch <target> <patch.json>` CLI — 完了 (`--dry-run` あり、`--force` なし、`--json` 構造化出力、PatchApplyError reason code 9 種)

**完了条件 (全達成):**

- 4 op の patch がそれぞれテストされる — 達成 (`apply_patch` 単体 46 件 + apply_patch_to_target 18 件 + CLI 9 件)
- apply 前 validate で reject されたら原本は touch されない — 達成 (atomic 保証、patch schema reject / target schema reject / validate-policy blocker のすべての経路で `_snapshot_dir` テスト)
- patch 適用後に validate-policy が通ることを自動検査 — 達成 (override seam 経由)

詳細な作業記録 (Codex 計画レビュー 18 指摘 + 5 着手前修正要件 → prejournal で案 X 採用判断 → 本体 → 段 1 観点別 5 subagent → 段 3 Codex 横断 → A1-A6 補修 → 段 5 Codex 2 周目「指摘なし収束」) は `journal/phase2-step2-2.md`。テスト 487 → 614 件、ruff clean。

**規模感:** prejournal 見積 1.7 (1.2 + 案 X 上振れ 0.5) → 実績 2.0 (補修込み)。Step 2.3/2.4/2.5 で前借り回収する設計。

**Step 2.3 / 2.4 / 2.5 への申し送り:**

- Step 2.3 (`add-waiver` / `add-knowledge`): 内部で patch_apply.apply_patch_to_target を呼ぶ設計、knowledge.jsonl は append-only として patch substrate 対象外で別経路実装
- Step 2.4 (`qgb check` / `qgb dev`): override seam を最大限活用、`apply_patch_to_target(dry_run=True)` を内部で呼ぶ
- Step 2.5 (Pattern B `propose-context` / `adopt`): `contract_overrides` の key は **canonical `contract_ref` 文字列に統一** (Codex 横断レビュー追加申し送り)、複数 document 変更時は **全 override を同一 world として渡す規約** (同上)

**Phase 3 送り (Step 2.2 では実装しない):**

- `move` / `copy` op
- patch の reverse (rollback)
- multi-file lock / multi-file rollback (quality-system 全体 transaction)

#### Step 2.3 — domain edit commands (**完結 2026-06-10**)

**スコープ (全項目完了):**

- `qgb add-waiver <REQ> <stage-id> --reason "..."` — 完了 (req-meta は patch substrate 経由 + knowledge.jsonl へ即時 evidence 記録 [F-007]、`--decided-by` / `--force` / `--dry-run` / `--json`)
- `qgb add-knowledge <file>` — 完了 (object/array 両対応、all-or-nothing schema 検証、既存 id skip、created_at 補完なし、`--force` なし [append-only と意味論衝突のため意図的に非搭載、spec の「--force 有り」は add-waiver で充足])
- knowledge orphan check — 完了 (`validate_policy_preflight` に `knowledge_orphan` kind で統合。waiver/REQ 不在 = blocker、waiver/stage 不在 = blocker、非 waiver = warning。**run_preflight には統合しない** — P9: REQ-A の orphan が `qgb run REQ-B` を塞がない)
- patch substrate 消費 — 完了 (`apply_patch_doc_to_target` を内部 API として切り出し、add-waiver が in-memory patch を直接流す)

**完了条件 (全達成):**

- atomic / idempotent / `--force` — 達成 (atomicity は「file 単位の保証 + idempotent recovery」と定義: req-meta は atomic swap、knowledge は append-only + partial-tail tolerant。meta / knowledge を独立判定して欠けている方だけ埋める収束動作)
- orphan check が validate-policy 経由で blocker — 達成 (`add-waiver` → REQ 削除 → `qgb validate-policy` exit 2 を CLI レベルでテスト)

詳細な作業記録 (Codex 計画レビュー 10 観点 → 着手前 3 仕様確定 → 本体 → 段 1 [hook 注入初実地、reject ゼロ] → 補修 A1-A3 → Codex 横断 → 補修 B1-B3 → 2 周目「指摘なし収束」) は `journal/phase2-step2-3.md`。テスト 614 → 666 件、ruff clean。

**規模感:** 0.9 で着地 (計画通り、Step 2.2 前借り効果が発現)

**Step 2.4 / 2.5 / 2.7 への申し送り:**

- Step 2.4: unrelated orphan blocker が patch 経由 edit を止める挙動の設計確認、`qgb check` は `add_waiver(dry_run=True)` / `apply_patch_doc_to_target(dry_run=True)` の組合せで実装可
- Step 2.5: knowledge.jsonl は JSON Patch 対象外を維持 (`qgb.core.knowledge` 経由限定)、`EditError.reason` / `PatchApplyError.reason` を安定 API として扱う
- Step 2.7: helper 重複整理 (A4)、複数回 force 時の warning 文言明確化 (Codex 2 周目軽微注記)

**Phase 3 送り:**

- waiver の削除 / revoke / supersede (--force の正式な reason 改訂もここ)
- knowledge entry の削除

#### Step 2.4 — daily verification channel (**完結 2026-06-12**)

**スコープ (全項目完了。Codex 計画レビュー 2026-06-11 反映、着手前判断は `journal/phase2-step2-4-prejournal.md`):**

- `qgb check REQ-ID` — **official run rehearsal**: `run_preflight` (run と同一関数) → `run_stages` → `decide` を共有し、`write_evidence` は呼ばず check 専用 writer で `.quality-system/artifacts/<REQ>/checks/<ts>-<runid>/` にのみ揮発出力 (境界 3 改訂版)。knowledge orphan scan は advisory 表示 (exit code を支配しない — unrelated orphan blocker が daily check を止めない、Step 2.3 申し送りの解)
- `qgb check` (REQ 省略) — project-wide `validate_policy_preflight(req_id=None)` 診断のみ (verification なし、揮発出力なし、exit は blocker 有無で 0/2)
- `qgb dev [REQ-ID]` — `qgb check` への thin alias (watch mode は Phase 3、help に「currently equivalent to check」明記)
- 出力形式: text human-readable + `--json`、exit code は `qgb run` と同じ (0=OK, 1=DENY, 2=NOT_READY)。ただし表示は「would ALLOW / would DENY」(rehearsal であることの明示)
- gate.json は schema 共用で `mode: "check"` を追加 (専用 schema は作らない)。decision.meaning に「not an official gate; curated evidence was not updated」を明記 (C-002 整合)
- check は command stage も実行する (リハーサルの価値)。**"read-only" とは呼ばない** (NF-010)。F-008 確認プロンプトは check では出さない (daily channel の摩擦回避)、help に「verification commands may run」明記
- check tmp の prune: `QGB_KEEP_RUNS` を流用 (専用 env は Phase 3)

**完了条件 (全達成):**

- `qgb check` が curated `evidence/latest/` / `knowledge.jsonl` / `artifacts/<REQ>/runs/` を一切 touch しない — 達成 (snapshot を bytes + dir 記録に強化した machine-verify、waived REQ [run と check が分岐する唯一の世界状態] 含む)
- tmp artifacts は init が既に .gitignore 予約済みの `.quality-system/artifacts/` 配下 — 達成 (追加の gitignore 手当て不要)
- `qgb run` と `qgb check` の preflight 経路が同じ関数を共有 (DRY、P9) — 達成 (run_preflight / run_stages / decide を共有、公式 run 出力は byte 不変)

詳細な作業記録 (計画 Codex レビュー → 案 A 着手前判断 → 本体 → 段 1 [Explore type 事故 → default 再投入 + テンプレ/許可恒久対応] → 補修 A1-A7 → backward-compat 再投入 → 補修 B1-B3 [U+FFFD loud 化等] → Codex 横断 → 実コード同梱 2 周目「指摘なし収束」) は `journal/phase2-step2-4.md`。テスト 666 → 698 件、ruff clean。

**規模感:** 1.0 で着地 (計画通り)

**Step 2.5 / 2.7 への申し送り:**

- Step 2.5: check は override seam を使わず disk world を検査する設計。「adopt 前検証 = override seam / adopt 後検証 = qgb check」の分担で足りるかを propose/adopt 設計の最初に確認 (Codex 横断注記: 仮想 overlay で check したくなったら別 seam)
- Step 2.7: `mode` を予約済み discriminator として扱う、curated/runtime 両 schema の意味論二重保守の解消可否、snapshot helper 統合 (test_patch_apply の str 版と conftest bytes 版)

**Phase 3 送り:**

- `qgb dev` の changed-files 絞り込み (P3 緊張、REQ ↔ source の依存マッピングが必要)
- watch mode (filesystem 監視)
- 全 REQ 一括 check、check 専用 keep env (`QGB_KEEP_CHECKS`)、check 専用 schema
- 書込中 check dir の prune 競合 / req_id 形式検証 / stage_id の filesystem-unsafe 文字 (いずれも run と同根の既存クラス、journal 記録のみ)

#### Step 2.5 — Pattern B external-LLM interface (**完結 2026-06-13**)

**スコープ (Codex 計画レビュー 2 周 + 実運用シミュレーション反映):**

- `qgb design-stages propose-context [--out <file>]` — detect 結果 + 現 policy (verbatim) + REQ 一覧 + 制約サマリの構造化 JSON (外部 LLM への入力素材)。P8 は機械可読メタデータで表現 (`document_kind` / `intended_use` / `contains_executable_instructions: false`)。`--out` は UTF-8 明示のファイル出力 (PowerShell 5.1 の stdout cp932 化けを迂回する file-based handoff、NF-004)。contracts 本文 / knowledge / project-context.md は含めない
- `qgb design-stages adopt <proposal.json>` — proposal schema 検証 → 新 policy 組み立て → **project-wide + 既存全 REQ の same-world per-REQ 検証** (`policy_override` を全 REQ に適用、1 blocker でも reject) → sibling-tmp atomic swap。`AdoptError` 固定 reason enum (検証順 = 安定 API)。成功 `--json` に `proposal_sha256` / `policy_before_sha256` / `policy_after_sha256` / `applied_at` / `source_metadata` (証跡は git + hash、knowledge 記録なし)。`--dry-run` あり / `--force` なし / 確認プロンプトなし (patch と対称)
- `qgb/schemas/proposal.schema.json` — `proposal_type: "policy_stages"` + `stages[]` 宣言的全量置換 + `source_metadata`。req-meta / contract を混ぜる余地を schema レベルで閉じる (P9)。Step 2.1 の format / `$ref` allowlist を継承
- **`qgb patch` POLICY 経路に同じ全 REQ same-world 検証を適用** — Step 2.2 の盲点 (project-wide のみで「adopt/patch 成功直後に既存 REQ が unknown_stage_id で壊れる」) を同時に塞ぐ安全側の挙動変更。`qgb patch policy` alias は追加しない (path 形 `qgb patch .quality-system/policy.json` が canonical、NF-010)
- **破壊的 rename の正規手順 = 3 段移行** (additive 追加 adopt → REQ meta を patch で移行 → 削除 adopt) を docs に明記。one-shot rename は Phase 3 multi-doc transaction 送り
- 既存 `qgb design-stages [--commit] [--json]` (rule-based) は完全温存、明示 subcommand のときだけ分岐

**完了条件 (全達成):**

- qgb 本体に LLM SDK 依存が増えない (`pip list` で確認可能) — 達成
- proposal を input にした end-to-end テストが通る (sample proposal.json は `tests/fixtures/` に `source_metadata.generator: "fixture"` で配置) — 達成
- 検証 (schema / 全 REQ same-world preflight) を通らない proposal は reject、原本は touch されない — 達成
- 稼働中 REQ を壊す policy patch / proposal が reject される (シミュレーション Flow 2 の再現テスト) — 達成

詳細な作業記録 (Codex 計画レビュー 2 周 + 実運用シミュレーション Flow 2 矛盾発見 → 着手前確定 13 件 → 本体 → 段 1 観点別 5 subagent [backward-compat モデルエラー → 再走] → A 系列 5 件補修 [9/9 reason テスト / dedupe テスト / BOM utf-8-sig / cp932 fallback / RecursionError guard] → Codex 横断「指摘なし収束」)。テスト 698 → 726 件、ruff clean。

**規模感:** 1.5 で着地 (計画通り)

**将来規約 (Step 2.5 では propose-context のみ実装):** machine-readable handoff JSON を stdout に出すコマンドは、将来 `--out <file>` (UTF-8 明示) を提供する方針

**Step 2.6 / 2.7 への申し送り:**

- BOM (utf-8-sig) 対応: loader.py / validate.py / patch_apply.py / proposal.py の主要 read path は対応済み。残りの read path (runner.py / scaffold.py / design_stages.py / edit_commands.py / knowledge.py) は Step 2.7 strictness review で網羅判断
- --path 重複: ds_p と pc_p/adopt_p の両方に --path がある (argparse namespace 上書き)。実用上の問題は「qgb design-stages --path X propose-context」で子の default が勝つこと。ジャーナル記録のみ (子パーサー側で --path を書けば正常動作)
- collect_same_world_blockers の dedupe は (kind, where, message) の 3-tuple。scope が異なる同一 finding の初出が scope を決める — project-wide report が常に先なので「<project>」scope で統一される設計意図
- AdoptError 9 reason は文字列固定、追加は versioned API change として扱う (Codex 横断レビュー確認)

**Phase 3 / 5 送り:**

- skill 側で context → proposal を生成するロジック (qgb 外、Phase 5)
- proposal の human-in-the-loop diff UI (qgb 外、Phase 5)
- multi-doc transaction (one-shot rename)、validate_schema_sources の cache 最適化、--out の全コマンド展開 (Phase 3)

#### Step 2.6 — example packs (**完結 2026-06-13**)

**スコープ (3 サブサブステップ、全完了):**

- **Step 2.6a — examples/python-fastapi-pytest/**: pytest + httpx TestClient (FastAPI 起動なし) + file_exists + substring_match
- **Step 2.6b — examples/go-cli/**: `go test` + `go vet` + substring_match
- **Step 2.6c — examples/node-cli-vitest/**: vitest + file_exists + substring_match (計画の Next.js → Node CLI + vitest に変更: npm install の重さ回避)

**完了条件 (全達成):**

- design-notes.md (7 セクション) + README + 整合性テスト — 達成 (6 例すべて)
- Phase 1 で確立した「対象系に近い例から始める」運用が成立 — 達成

詳細な作業記録は `journal/phase2-step2-6.md`。テスト 726 → 731 件。レビュー省略 (差分は example 生成のみ、新コード < 50 行)。

**規模感:** 0.5 で着地 (計画 1.5 から下振れ: パターン確立後の例生成は軽い)

#### Step 2.7 — strictness review (**完結 2026-06-13**)

**スコープ (全項目完了):**

- `additionalProperties: false` の判断 — **部分適用 (現状維持)**: gate.schema.json / proposal.schema.json は strict (Phase 1/2 で確立済み)、他は true 維持 (Phase 3 adapter 拡張のため)。`--strict` 実体は Phase 3 送り
- migration notes — 完了 (`docs/migration-phase1-to-phase2.md`)
- Phase 2 完結ジャーナル — 完了 (`journal/phase2-step2-5.md` 〜 `phase2-step2-7.md` + `phase2-summary.md`)
- Phase 3 申し送り項目 — 17 項目を `journal/phase2-step2-7.md` に列挙

**完了条件 (全達成):**

- 全 spec / docs が Phase 2 反映済 — 達成
- Phase 3 申し送り項目が明確化されている — 達成 (17 項目)

**規模感:** 0.3 で着地 (計画 0.5)

### 13.3 規模感サマリ

| サブステップ | 計画 | 実績 | 主要リスク |
|---|---|---|---|
| 2.1 schema baseline | 0.8 | 0.8 | 後方互換破壊 |
| 2.2 patch substrate | 1.2 | 2.0 | atomic 保証 (案 X 上振れ) |
| 2.3 domain edit commands | 1.0 | 0.9 | knowledge orphan の判定基準 |
| 2.4 daily verification channel | 1.0 | 1.0 | curated 不変の machine-verify |
| 2.5 Pattern B external-LLM | 1.5 | 1.5 | proposal schema 設計、命名 |
| 2.6 example packs | 1.5 | 0.5 | パターン確立後は軽い |
| 2.7 strictness review | 0.5 | 0.3 | 判断のみ |
| **合計** | **7.5** | **7.0** | |

### 13.4 Phase 1 で確立したパターンの再利用

- **観点別 5 subagent 並列 → 集約 → Codex 横断 → 補修 → 収束ループ** (memory `review-process`)
- **計画 Codex 相談 → 着手前構造修正 → 実装 → 統合レビュー** (Step 6 全体で確立、Step 7-9 で安定運用)
- **本体 + 補修を 1 コミットにまとめる** (Step 6c から定着)
- **Codex sandbox 起動失敗時の Claude 実コード証明 → 2 周目で収束宣言** (Step 6+7 / 8 / 9 で繰り返し成功)
- **memory への永続化判断**: 設計境界に関わる判断 (Pattern B など) は memory に独立記録

### 13.5 Phase 2 完了時の繰越判定パート (Step 2.7 完了後の必須プロセス)

Phase 2 では Codex 計画レビュー (2026-06-01) で次の項目が **Phase 3 送り** として確定した:

- JSON Patch `move` / `copy` op (Step 2.2 で 4 op 限定)
- waiver の削除 / revoke / supersede モデル (Step 2.3 で `add-waiver` のみ)
- `qgb dev` の changed-files 絞り込み (Step 2.4 で `--all` 経路のみ、P3 緊張のため REQ ↔ source の依存マッピングが必要)
- `additionalProperties: false` の全面適用 (Step 2.7 で Step 2.1〜2.6 の運用結果を見て判断)
- Phase 1 から繰越された負債: Popen / process tree kill (Windows Job Objects / Unix process groups)、`.bat` argument escaping、`command` runner の真の memory cap、fsync / power-loss durability、bare `qgb` entry point、CI 依存 audit / SBOM 生成

加えて Phase 2 の各 Step 完了時に発見される新規 Phase 3 送り (各 Step の journal に「申し送り」セクションで列挙される) も累積する。

**Step 2.7 完了直後に user と相談する必須パート** を設定する。具体的な相談項目:

1. **Phase 2 繰越項目の Phase 3 への流し込み**: 上記 Phase 3 送り項目を Phase 3 (adapter 拡張 + Phase 2 繰越 + Phase 1 負債) のスコープにそのまま入れるか、一部の項目を Phase 4 (CI 連携) や Phase 5 (Skill Creator 化) に再配置するか、いくつかの項目を「将来の Phase」(Phase 6 以降) に降格して当面の負債整理を絞るか
2. **Phase 2 中に新規発生した負債の重要度判定**: Phase 1 が「`qgb verify` 撤回」のような **着手前構造修正** で負債を未然に防いだ事例があったように、Phase 2 で新規発生した負債のうち「Phase 3 着手前に解決すべき」ものと「Phase 3 と並行で良い」ものを区別する
3. **`additionalProperties: false` の判断**: Step 2.7 strictness review の結果 (全面 / 部分 / 見送り) を踏まえて、Phase 3 で `--strict` フラグを実体化するか、Phase 4 以降に送るかを判断
4. **Phase 3 規模感の再確認**: Phase 1 / Phase 2 はそれぞれ Step 5 = 1.0 基準で 7〜8 規模だったが、Phase 3 は adapter 量産 6 言語 (Go / Rust / .NET / Java / PHP / Markdown) + Phase 2 繰越 5 件 + Phase 1 負債 6 件 = 17 項目で、規模感が Phase 1 / Phase 2 の倍以上になる可能性。Phase 3 を 3a (adapter 量産) と 3b (繰越 + 負債) に分割する案を user と相談
5. **Phase 2 完結ジャーナル + 全体振り返り**: Phase 1 完結時に作成した `journal/phase1-step9.md` の Phase 1 全体振り返りパートと同じ粒度で、Phase 2 全体の思想軸 / プロセス軸 / 技術軸の振り返りを `journal/phase2-summary.md` (Step 2.7 で作成) にまとめる

**相談の媒体:**

- Step 2.7 の commit + journal 作成時に user に提示
- `/ask-codex-with-context` skill 経由で Codex のセカンドオピニオンも取得 (Phase 2 規律の継続)
- user 判断後、`requirements_and_development.md` §13 (Phase 3 / 4 / 5) を相応に改訂し、新規 commit にする

このパートは Step 2.7 完了の **必須プロセス**として detailed-design.md に明記しておく (Step 2.7 完了 = Phase 2 完結ではない、user 相談を経て初めて Phase 2 完結とする)。

## 14. Phase 3 計画 (2026-06-21 全面再構築、Codex セカンドオピニオン 2026-06-20 / 2026-06-21 反映)

Phase 2 完結後の user 指摘で次が確定した:

1. **adapter (言語判定) 廃止**: 対象プロジェクトの広がり (Markdown / プロンプト集 / 設定群 / 法務テンプレ等) に adapter 抽象が追いつかない、検出結果は ALLOW/DENY 判定の根拠でない、残存すると Phase 5 スキルへの悪い few-shot 教材になる、の 3 点が決定打。Claude が前段で 2 回ラインを引き間違えた事実 (adapter 廃止 → P7 のため復活 → user 指摘で再廃止) の記録は journal phase3-step3-0-prejournal.md に残す
2. **Phase 4 (CI 連携) 廃止**: 当初項目は別の場所に吸収または WONTFIX。qgb 自身の CI は Phase 3 Step 3.1 で最小構成 (qgb の P6 を qgb 自身に適用)
3. **Phase 3 を「機械責務側の最終整備」に再定義**: Phase 5 (Skill Creator 化) 提供の前提条件を揃える Phase。規模 3.4〜4.3 (Phase 1 / Phase 2 と比べて軽量)

### 14.1 ライン引きの最終形

| ドメイン | 担い手 | 形式 |
|---|---|---|
| プロジェクトの自己定義 (何を作りたいか、何を保証したいか) | **人間** | `.quality-system/knowledge/project-context.md` |
| md → json 構造化 | **補佐 Agent (利用者環境の LLM)** | `.quality-system/project-context.json` |
| json の schema 検証 | **qgb (機械)** | `qgb validate` |
| json + .quality-system/ 現状を構造化して export | **qgb (機械)** | `qgb design-stages propose-context` |
| 段階設計の生成 | **本番 LLM (Phase 5 スキル)** | `proposal.json` |
| proposal の schema + 整合性検証 + 適用 | **qgb (機械)** | `qgb design-stages adopt` |
| contract の検査実行 | **qgb (機械)** | `qgb run` |
| ALLOW/DENY 判定 | **qgb (機械)** | `gate.json` |

ライン引きの本義: 「設計と監査の境界」「人間の意思を機械可読に固定する境界」「qgb は何を信用して何を検証するか」を明確にする。

### 14.2 サブステップ計画

#### Step 3.0 — detect 廃止 + project-context 導入 (規模 2.0〜2.5)

**スコープ:**

- `qgb detect` CLI コマンド削除 / `qgb/core/detect.py` 削除 / `qgb/adapters/` 削除 (base / generic / python)
- `qgb/core/proposal.py` から detect 参照削除、`project_context` 読み込み追加 (propose-context 出力構造の更新)
- `qgb/core/design_stages.py` から detect 参照削除 (legacy rule-based 経路の整理)
- `qgb/cli.py` から detect コマンド削除
- `qgb/schemas/project-context.schema.json` 新設
- `qgb/core/init.py` で `project-context.json` 雛形生成 (`human_reviewed: false` 初期値)
- `qgb/core/loader.py` に `load_project_context` 追加
- `qgb/core/validate.py` に `project-context.json` 検査追加
- `propose-context` が `human_reviewed: false` の `project_context` を含むとき warning 出力経路
- Phase 1 で蓄積した Python adapter 観察知見の転記 (Codex 指摘): `examples/python-cli-pytest/project-context.{md,json}` を記入例として整備、design-notes.md に「Python プロジェクト観察観点」を転記
- 関連テスト削除 + 新規 (project_context 周辺、human_reviewed 経路、warning 経路)
- spec / docs 改訂 (requirements_and_development.md / detailed-design.md / framework-shape.md)

**`project-context.schema.json` 設計指針 (Codex 指摘反映):**

- root に `human_reviewed: bool` フィールド (人間承認状態を別立てで持つ、P8 利用者の明示指示の境界)
- `constraints.language` のような言語中心字段を避け、`technologies` / `artifact_kinds` (array) のような広い語彙にする (Codex 指摘: 言語中心モデルを再誘発しない)
- `source_metadata.generated_by`: `"human"` / `"agent-assisted"` で生成経路を区別
- `source_metadata.source_md_sha256`: md が更新されたのに json が古いままという状態を機械的に検出可能にする (Phase 3 以降で `qgb validate-policy` の追加 kind として `project_context_stale` を入れる選択肢あり)

**Pattern B 境界の更新:**

- Before: 「qgb は対象プロジェクトを**機械的に観察した結果 (detect)** と .quality-system/ の現状を構造化して LLM に渡す」
- After: 「qgb は **.quality-system/ の現状のみ** (project-context.json を含む) を構造化して LLM に渡す。対象プロジェクトの観察は LLM 責務」
- Pattern B の **構造 (2 interface + schema + 検証 + 適用)** は無変更、**境界がより正確に縮約**

**完了条件:**

- detect / adapter 関連コード / テストが残らない (grep でゼロ確認)
- `qgb validate` が `project-context.json` の schema 検証を含む
- `qgb design-stages propose-context` 出力に `project_context` フィールドが含まれる
- `qgb init` が `project-context.json` 雛形を生成
- `examples/python-cli-pytest/` が新形式 (project-context.{md,json}) で動作
- 既存テストが全 green (削除されたものを除く)

**Phase 3 Step 3.1 への申し送り:** runner.py の `_run_command` 切り出し設計 (`qgb/core/command.py` 新設) の準備

#### Step 3.1 — command runner 強化 + CI 雛形 (規模 1.5〜2.0)

**スコープ:**

- `qgb/core/runner.py` の `_run_command` を `qgb/core/command.py` に切り出し (P9 単一責任)
- Popen + process tree kill:
  - Windows: `ctypes` 経由で Job Objects (CreateJobObject + AssignProcessToJobObject + TerminateJobObject)、最小境界明示、失敗時 fallback (TerminateProcess + 子孫 leak のログ警告)
  - POSIX: `os.setsid()` で新規 process group → `killpg(SIGTERM)` → 猶予後 `killpg(SIGKILL)`
- `.bat` / `.cmd` argument escaping:
  - `cmd.exe` メタ文字 (& | < > ^ % " 等) の escaping ヘルパー (別扱い)
  - C++ argv parsing 規則 (CommandLineToArgvW 互換) のヘルパー (別扱い)
  - Popen 呼び出し時に argv[0] が `.bat` / `.cmd` だったら両方適用
- ストリーム読み取り 16 MiB 上限 (RSS cap は WONTFIX、stdout/stderr 合算 / 個別かは prejournal で確定)
- 実 temporary `.bat`/`.cmd` fixture で argument escaping を検証 (Codex 指摘)
- CI 雛形 `.github/workflows/test.yml`:
  - pytest only (Windows + Ubuntu matrix)
  - `actions/checkout` + `actions/setup-python` のみ、commit SHA pin
  - `permissions: contents: read`
  - third-party action ゼロ、secrets 不使用、Dependabot/Renovate なし
  - POSIX 経路は CI で機械的判定 (論証で済ますことは qgb の P6 違反になるため)

**スコープ外 (WONTFIX):**

- RSS 監視 (psutil 等の依存追加なし、output stream cap として Step 3.1 で処理)
- OS 別 memory cgroup / Job Object メモリ制限

**完了条件:**

- 既存 731 件 + Step 3.1 追加分のテストが Windows + Ubuntu の両 CI で green
- 実 `.bat`/`.cmd` fixture で argument escaping が機能
- 16 MiB 超過ストリームで process tree kill 発火
- POSIX 経路が CI で実証される

#### Step 3.2 — 依存解決固定 (規模 0.5〜0.8)

**スコープ:**

- `pip-tools` (`pip-compile`) 等で lock/hash
- CI で `pip-compile --generate-hashes` の出力を artifact として残す
- 当初 Phase 4 の「依存 audit / SBOM」をここで吸収

**理由:** Phase 5 スキル提供時に「ユーザーが pip install qgb した結果が再現可能」であることが supply-chain 信頼の前提。jsonschema の推移依存が複数あり pip freeze だけでは P7 不足 (Codex 指摘 2026-06-13 で WONTFIX 撤回した経緯)

#### Step 3.3 — Phase 2 繰越の実需回収 (任意、規模 0.5〜1.0)

**候補 (Phase 5 で必要が判明したものに限定、先回りで全部やらない):**

- `--strict` 実体実装 (Step 2.7 で先送り判定済)
- waiver 削除 / revoke / supersede モデル
- JSON Patch `move` / `copy` op
- multi-doc transaction (one-shot rename)
- `qgb dev` の changed-files 絞り込み
- 全 REQ 一括 check

### 14.3 Phase 4 廃止に伴う各項目の処理

| 当初項目 | 処理 |
|---|---|
| GitHub Actions / GitLab CI 例 | Phase 5 のスキル生成テンプレに含める (利用者プロジェクト向け) |
| JUnit XML 出力 | **WONTFIX** (P11 ALLOW 比較不可能性違反リスク) |
| PR コメント連動 | **WONTFIX** (利用者運用、qgb 責務外) |
| 採用判定のレビュー連動 | **WONTFIX** (利用者運用、branch protection で実現) |
| 依存 audit / SBOM | Step 3.2 で吸収 |
| qgb 自身の CI | Step 3.1 で最小構成 |

### 14.4 Phase 5 への影響 (adapter なし設計)

- adapter 量産は Phase 5 でも実施しない
- スキルが対象プロジェクトを Read で読んで分析 (LLM 責務)
- ALLOW/DENY は qgb の contract 実行結果で決まる (Codex 指摘: 「対象判定を全て LLM に委ねる」でなく「対象理解は LLM、ALLOW/DENY は qgb の contract 実行結果」)
- 利用者プロジェクトに CI テンプレ (GitHub Actions 等) を生成する機能はスキルに含める (当初 Phase 4 項目を吸収)
- examples/ の追加は言語別ではなくドメイン別 (prompt-collection / terraform-modules / sql-schemas / legal-templates / mixed-devops 等)、Phase 3 で先回りせず Phase 5 で必要に応じて追加

## 15. 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 0.1 | 2026-05-21 | Phase 1 Step 0〜2 確定範囲を初版として記録 |
| 0.2 | 2026-05-21 | Phase 1 Step 3 (qgb init) を反映。§6 を新設 |
| 0.3 | 2026-05-21 | Step 3 補修 (Codex レビュー反映): InitError / NOT_READY 化 / 構造化 JSON 置換 / .gitignore 端処理を §6.3, §6.5 に反映 |
| 0.4 | 2026-05-21 | Phase 1 Step 4 (examples/generic-minimal/) を反映。§7 を新設、§2 リポジトリ構造に examples/ を追加 |
| 0.5 | 2026-05-21 | Step 4 補修 (Codex レビュー反映): log_ref 実体追加 / REQ-design-notes 矛盾解消 / 整合性テスト 5 層化 / §7.4 timestamp 規約と §7.5 basis 規約を Step 5 申し送りとして明文化 |
| 0.6 | 2026-05-21 | Phase 1 Step 5 (qgb run 縦串) を反映。§8 を新設し loader/preflight/runner/decision/evidence の 5 モジュール責務、preflight 検査、verification_type 実装、timestamp/basis 生成、2 系統出力、QGB_KEEP_RUNS を確定。§10 テスト件数 173 件に更新、§11 思想憲章マトリクスに P6 機械化を追加 |
| 0.7 | 2026-05-22 | Step 5 補修 (Codex レビュー反映): R1 contract.target の root escape 防止 (loader.resolve_project_relative を共通化)、R2 同一秒 run_dir 衝突回避、R3 optional stage と ALLOW schema の矛盾解消 (全 adopted stage を判定対象に)、reference gate.json の `evidence-reference/` 退避、§12 に Step 6 申し送り (preflight 再分割 / severity / topological order / atomic write / byte offset / loader error / QGB_KEEP_RUNS warning) を追加 |
| 0.8 | 2026-05-23 | Step 5 二次補修 (Codex 二次レビュー反映): RR1 run_dir 予約を atomic 化 (mkdir(exist_ok=False) ループ + 60 秒 fallback を廃止)、MR2 resolve_project_relative() で absolute path を明示拒否、MR3 req-meta.schema.json の `required` を `const: true` で固定 (Phase 1 では false を schema レベルでブロック)、symlink escape テスト追加。§12 Step 6 申し送りに「timestamp と run_id の責務分離」(RR2 + MR1) を追加。テスト 184 件 |
| 0.9 | 2026-05-23 | Step 5 三次補修 (Step 6 スコープ整理 + Codex 三次レビュー前準備): C 部分 (gate schema に `run_id` 導入、`timestamp_*` を wall-clock truth に、`paths.run_dir` を `<compact>-<run_id>` に、REQ meta トポロジカル順検証 M1) を完全前倒し。B 部分 (preflight の 5 関数分割: validate_schema_sources / inspect_policy_graph / resolve_adopted_stages / check_runtime_support / run_preflight、`PreflightIssue.severity` フィールド追加で Phase 1 は全件 blocker) も型・構造のみ前倒し。§4.2 識別子規約、§7.4 timestamp/run_id 規約、§8.1 モジュール責務、§8.7 同秒衝突回避を新仕様に。§12 Step 6 申し送りから完了項目を削除し validate-policy 視点の残課題のみ残す。テスト 196 件 |
| 0.10 | 2026-05-23 | Step 5 四次補修 (Codex 三次レビュー反映、Step 5 完結): RRR1 `r0000` を予約値として schema レベルで拒否 (`gate.schema.json` / `gate.runtime.schema.json` 両方に `not: {const: "r0000"}` 追加、`_RUN_ID_MIN = 1` と一致)、RRR2 `paths.run_dir` の末尾形状を schema `pattern` で `<timestamp_utc>-<run_id>` に固定 (任意外部 payload の防衛線を一段強化)。§4.2 run_id 説明、§7.4 規約表、§8.7 同秒衝突回避を四次補修反映に更新。テスト 204 件。**Step 5 系は本版で完結** (Codex 三次レビュー判定: 残課題 atomic write / byte offset / loader error / QGB_KEEP_RUNS warning は Step 6 と一緒に扱う) |
| 0.11 | 2026-05-23 | Step 6 計画確定 (Codex 計画レビュー反映): §12 を 4 サブステップ (6a 検査強化 / 6b 実行系小修正 / 6c 検出系 / 6d 生成系) に再編。preflight 診断 API を `iter_issues(severity)` を主 API として確定、`ready_for_run()` を runner 専用に限定し validate-policy では `has_blockers()` を使う方針を明文化 (P9)。Step 5 残課題を性質別に分散 (loader_error / byte offset → 6a、atomic write / QGB_KEEP_RUNS → 6b)。fixture 復活を「validate-policy の仕様固定装置」として 6a 完了条件化。`qgb verify` を 6b の最初に実装 (preflight API の最初の消費者として 6a の過不足を早期に見る)。adapters/ は 6c で `DetectedProjectProfile` データ境界を固定し validate-policy 経路と混ざらないようにする (P9)。6d 規模見積もりを 0.7 → 0.9〜1.2 に上方修正 (生成系の出力仕様整合・idempotency で補修が出やすいため) |
| 0.12 | 2026-05-23 | Step 6a 本体 3 コミット完了 (Codex レビュー待ち): Commit 1 で `PreflightReport` 診断 API (`iter_issues(severity)` / `blocking_issues` / `warnings` / `has_blockers` / `ready_for_run`) を整理。Commit 2 で 5 つの新 issue kind (`duplicate_stage_id` / `misplaced_contract` / `missing_contract_field` / `stage_count_out_of_range` warning / `wrong_type`) と `check_runtime_support(mode="run"|"validate_policy")` を追加、`validate_policy_preflight()` 新規 entry point。Codex L2 (substring_match の "byte offset" → "char offset" 表記) と L3 (LoaderError.wrong_type の preflight 側分類) を同時に解消。Commit 3 で `qgb validate-policy [REQ-ID]` CLI を実装 (exit code: blocker→2 / warning のみ→0 stderr / clean→0 stdout、`--json` 対応)。tests/fixtures/validate_policy/{missing_required, dangling_ref, misplaced_contract}/ を「validate-policy の仕様固定装置」として作成。テスト 204 → 234 件 (+30)、ruff clean |
| 0.13 | 2026-05-25 | Step 6a 補修 1 次 (Codex レビュー反映): **M1** misplaced_contract と wrong_type の優先順位を仕様化 (`resolve_adopted_stages` docstring に明記、テスト名も spec lock 名に変更)。canonical-layout 検査が path 解決より先に走る設計を確定し、contract_ref 経由の wrong_type は「canonical 文字列に合致したうえで symlink で root を escape する」狭い経路でしか出ないことを明記。**M2** graph integrity blocker (`duplicate_stage_id` / `depends_on_cycle`) があるとき adopted resolution を short-circuit する `_has_graph_integrity_blockers` ヘルパーを導入し、run_preflight と validate_policy_preflight 両方で適用 (`depends_on_unknown` は意図的に対象外)。**m1** runner.py の char offset コメントを「Python code point index」に修正 (旧記述「UTF-16 code unit」は内部表現露出の誤解)。**m3** detailed-design に CLI 出力規約節を新設 (機械処理は `--json` + exit code を正とする、stderr に warning を出すのは advisory の silent 化を防ぐためで「stderr=失敗」扱いの CI wrapper との衝突は --json で回避)。テスト 234 → 238 件 (+4)、ruff clean |
| 0.14 | 2026-05-28 | Step 6a 補修 2 次 (Codex 二次レビュー反映、**Step 6a 完結**): docs-only の小修正。Codex 二次レビューの major 指摘 (validate-policy の short-circuit は設計意図を明文化すべき) と minor 指摘 ("cheaper diagnostic first" を一般原則にしすぎない) の 2 件を反映。`_has_graph_integrity_blockers` コメントに「validate-policy でも止める理由」を追記 (誤った/不安定な findings を正しい一次 finding に重ねるとフィードバック品質が劣化するため、integrity blocker を先に修正させてから再実行する運用)。`resolve_adopted_stages` docstring の "cheaper diagnostic first" 説明を「本ケース限定の judgment」に書き換え、M2 が逆方向のトレードオフを採用していることに言及して両者の共存を明確化。§12 Step 6a 同じ趣旨で更新。コード変更なし、テスト件数 238 件のまま、ruff clean。**Codex 二次レビュー判定: blocker なし、Step 6b へ進んでよい** |
| 0.15 | 2026-06-02 | Phase 2 計画確定 (Codex 計画レビュー 2026-06-01 反映、Phase 1 完結後の初版改訂): §13 を新設し Phase 2 を 7 サブステップ (2.1 schema baseline / 2.2 patch substrate / 2.3 domain edit commands / 2.4 daily verification channel / 2.5 Pattern B external-LLM / 2.6 example packs / 2.7 strictness review) に分解。着手前確定の設計境界 5 件を §13.1 に明文化 (Pattern B の LLM 境界 / JSON Patch subset / check 証跡境界 / schema strict mode / waiver 削除 Phase 3 送り)。規模感 6.2〜10.0 (Phase 1 全体と同等以上)。requirements_and_development.md §13 を同時改訂し Phase 2 主軸を「編集を安全にする」、Phase 3 を「adapter 拡張 + Phase 2 繰越 + Phase 1 負債」に再編。journal/phase1-step9.md の Phase 2 引き継ぎ段落も Codex 計画レビュー反映後の正しい主軸に修正。memory に `qgb-llm-boundary` を独立記録 (Phase 2 Pattern B / Phase 5 skill の核心境界)。コード変更なし。**Step 2.1 着手準備完了** |
| 0.16 | 2026-06-05 | **Phase 2 Step 2.1 完結**: schema baseline (Codex 計画レビュー 8 指摘吸収後 → 本体 → 観点別 5 subagent → Codex 横断 → A1-A4 補修 → Codex 2 周目「指摘なし収束」)。`contract.enforce_format` (default false) で format checker opt-in、`contract.allow_internal_ref` (default false) で `#` / `#/...` の internal JSON Pointer のみ accept (anchor / 絶対 URI / 相対 URI / file / http / sibling-file は引き続き reject)、`build_qgb_format_checker()` を public 化 (P9)、`_collect_dollar_refs` / `_is_internal_pointer_ref` / `_collect_format_names` 新設、`formats_seen` / `formats_checked` / `formats_ignored` ログ粒度で typo'd format 名を audit 可能に。`--strict` skeleton は Codex 指摘 5 採用で Step 2.7 へ送り。Phase 1 挙動は default false 経路で完全保存 (既存 example 3 例 + fixture 9 個 + 既存 12 テスト無変更通過)。memory 改定: `parallel-strategy` に subagent prompt 冒頭テンプレ v3 必須を昇格 (Bash 完全禁止 + 許可が通る経路の例示 + 論証で詰める指針 + 退路)、`codex-context-files` に skill 経路と wrapper 経路の使い分け併記。詳細は `journal/phase2-step2-1.md`。テスト 470 → 487 件 (+17)、ruff clean |
| 0.17 | 2026-06-05 | §13.5 Phase 2 完了時の繰越判定パート新設: Phase 3 送り項目 (JSON Patch move/copy、waiver 削除、changed-files 絞り込み、additionalProperties: false 全面適用、Phase 1 負債 6 件) を Step 2.7 完了直後に user と相談して Phase 3 / 4 / 5 / Phase 6 以降への流し込みを判断する **必須プロセス** として明文化。相談項目 5 点 (繰越流し込み / 新規負債重要度 / additionalProperties 判断 / Phase 3 規模再確認 / Phase 2 全体振り返り `journal/phase2-summary.md`)。`/ask-codex-with-context` skill 経由 Codex セカンドオピニオン併用。Step 2.7 完了 = Phase 2 完結ではなく、user 相談を経て初めて Phase 2 完結とする規律。コード変更なし。**Step 2.2 着手前 spec 改訂** |
| 0.18 | 2026-06-05 | **Phase 2 Step 2.2 着手前判断確定** (`journal/phase2-step2-2-prejournal.md` で詳細記録): Codex 計画レビュー (skill 経由) で 18 指摘 + 5 着手前修正要件を受領後、最大の構造リスク (validate-policy が file 読込前提で in-memory doc を受け取れない) について案 X (preflight に override seam) と案 Y (sibling tmp で実 file 入れ替え) を検討。思想憲章 P3 (コード不変仮定の禁止) / P7 (再現可能証跡) / P9 (単一責任の本質) / NF-004 (Windows first-class) で **案 X が全面的に有利**、Phase 1 Step 6a の `iter_issues(severity)` 先払いと同型と判断、user により案 X 採用確定。規模感は Step 2.2 単独で 1.2 → 1.7 に上振れだが、Step 2.3 / 2.4 / 2.5 で同 seam を再利用できるため Phase 2 全体では 7.5 → 7.4 でほぼ不変 (前借り回収)。Step 2.2 着手前確定事項 5 件 (override seam / json_pointer.py 分離 / patch.schema.json 厳密化 / PatchError reason code / `--force` 撤回 + `--dry-run` 完全実行)。コード変更なし、prejournal 作成のみ。**Step 2.2 実装着手準備完了** |
| 0.19 | 2026-06-05 | **Phase 2 Step 2.2 完結**: patch substrate (Codex 計画レビュー 18 指摘 + 5 着手前修正要件 → prejournal で案 X 採用判断 → 本体実装 → 段 1 観点別 5 subagent → 段 3 Codex 横断 → A1-A6 補修 → 段 5 Codex 2 周目「指摘なし収束」)。`qgb/core/json_pointer.py` (encode/decode/parse_array_index、ASCII digit 限定 [A1])、`qgb/core/patch.py` (4 op、PatchError 8 reason)、`qgb/schemas/patch.schema.json` (op 別 required/forbidden、remove で value 完全禁止 [A3])、`qgb/core/preflight.py` の override seam 追加 (案 X、default 経路 Phase 1 完全互換)、`qgb/core/patch_apply.py` (target classify [A2 segment 厳密チェック]、atomic swap [A4 suffix 明示]、PatchApplyError 9 reason)、`qgb/cli.py` の `qgb patch` (`--dry-run` 完全実行、`--force` なし)、`tests/conftest.py` 集約 [A5]。Codex 横断レビュー追加申し送り 2 件 (contract_overrides key 統一 / 複数 doc 同一 world 規約) を Step 2.5 規約として journal に明文化。Phase 1 挙動は default 経路で完全保存、既存 example 3 例 + fixture すべて無変更通過。詳細は `journal/phase2-step2-2.md`。テスト 487 → 614 件 (+127)、ruff clean。**Step 2.3 着手準備完了** |
| 0.20 | 2026-06-10 | **Phase 2 Step 2.3 完結**: domain edit commands (Codex 計画レビュー 10 観点 → 着手前 3 仕様確定 [--force は req-meta のみ更新 + knowledge 歴史保持 / atomicity = file 単位保証 + idempotent recovery / add-knowledge は補完なし・--force なし・all-or-nothing] → 本体 → 段 1 観点別 5 subagent [PreToolUse hook によるテンプレ自動注入の初実地、reject ゼロ] → 補修 A1-A3 [dry-run would-be 値 / OSError→EditError(io_error) / テスト 6 件] → Codex 横断 → 補修 B1-B3 [force+knowledge 欠落の warning 真実性 / 生成 entry の schema validate / append 保証境界の文言+実装] → 2 周目「指摘なし収束」)。`qgb/core/knowledge.py` (store 層: append_knowledge_entries / build_waiver_knowledge_entry / waiver_knowledge_id 正本移管 / check_knowledge_orphans) + `qgb/core/edit_commands.py` (orchestration 層: add_waiver / add_knowledge / EditError reason enum) の 2 module 構成。`apply_patch_doc_to_target` を patch substrate の内部 API として切り出し。`knowledge_orphan` kind を validate_policy_preflight に統合 (run_preflight には入れない、P9)。実装中に waiver id 形式の不一致 (`KNOWLEDGE-WAIVER-` vs 正本 `WAIVER-`) を自己検出し knowledge.py を正本に一元化。詳細は `journal/phase2-step2-3.md`。テスト 614 → 666 件 (+52)、ruff clean。**Step 2.4 着手準備完了** |
| 0.21 | 2026-06-11 | **Phase 2 Step 2.4 着手前判断確定** (`journal/phase2-step2-4-prejournal.md` で詳細記録): Codex 計画レビューで方向性承認 + 中程度以上 5 指摘 (per-REQ check は unrelated orphan blocker で止めない / tmp パス変更は境界 3 の明示承認必須 / mode:"check" の機械可読誤認対策 / "read-only" と呼ばない / check tmp の prune 必須) を受領。最大の判断点 = 揮発出力先について、init の .gitignore 予約が `.quality-system/artifacts/` のみで `.qgb/` 未予約という事実誤認を発見し、案 A (`artifacts/<REQ>/checks/<ts>-<runid>/`、既予約木に同居) を理念照合 4 点 (P7 同種同所 / tool-private でないものを `.qgb/` に置くのは分類の誤り / NF-010 表面積最小化 / 境界 3 の正本は curated 不変でありパスは例示) で user 確定。§13.1 境界 3 と §13.2 Step 2.4 スコープを改訂。コード変更なし。**Step 2.4 実装着手準備完了** |
| 0.22 | 2026-06-12 | **Phase 2 Step 2.4 完結**: daily verification channel (`qgb check` / `qgb dev`)。`qgb/core/check.py` 新設 (run_check = run_preflight/run_stages/decide を run と共有する official run rehearsal、check 専用 writer は `artifacts/<REQ>/checks/<ts>-<runid>/` のみ出力、curated swap / knowledge append / runs prune を意図的に不実行)。gate schema 共用 + `mode: "check"` (公式 gate は mode 不在で byte 不変、mode=check で curated_latest_dir 禁止の allOf 条件)。orphan は per-REQ で advisory / REQ-less で blocker (P9)。補修 A1-A7 (U+2014 ASCII 化 [cp932 リダイレクト障害]、byte-torn tail 耐性、**gate.runtime.schema.json の Step 7 waived drift 解消**、snapshot fixture の bytes+dir 化、waived REQ テスト群) + B1-B3 (U+FFFD を終端行で loud に / README / dir marker sentinel)。段 1 で Explore subagent 事故 (PowerShell・cd 連結・パス手打ちミスで申請多発) → default agent + テンプレ強化 + 「要実機確認タグ」出口 + 非破壊傘 2 件追加で恒久対応、再投入は申請ゼロ。Codex 横断 1 周目「cross-seam finding なし」(sandbox エラーで提示ベース) → 実コード同梱 2 周目「**指摘なし収束**」。詳細は `journal/phase2-step2-4.md`。テスト 666 → 698 件 (+32)、ruff clean。**Step 2.5 着手準備完了** |
| 0.23 | 2026-06-12 | **Phase 2 Step 2.5 着手前判断確定** (`journal/phase2-step2-5-prejournal.md`): Codex 計画レビュー 1 周目で構造確定 (proposal_type: "policy_stages" 宣言形 / AdoptError 固定 enum 9 種 [検証順 = 安定 API] / 証跡 = knowledge 記録なし + result JSON に sha256 hash 3 種 / P8 は機械可読メタデータ / design-stages 後方互換 / `qgb patch policy` alias なし / fixture は tests/)。user 依頼の**実運用フローシミュレーションで矛盾 1 件発見**: adopt/patch (POLICY) の検証が project-wide のみのため「成功直後に既存 REQ が unknown_stage_id で壊れ waiver も orphan 化する」— Step 2.2 patch の既存盲点も grep で確認。追加確定 3 件 (adopt = project-wide + 全 REQ same-world per-REQ 検証 / 同検証を patch POLICY 経路へ適用 [安全側挙動変更] / propose-context --out [cp932 迂回の file handoff、NF-004])。破壊的 rename の正規手順 = 3 段移行 (additive adopt → REQ meta patch 移行 → 削除 adopt)、one-shot rename は Phase 3 multi-doc transaction 送り。Codex 2 周目で影響確認 (per-REQ 失敗詳細の機械可読化 / 壊れた既存 meta は reject / 計算量は許容・cache は Phase 3 / 規模 1.5 内)。§13.2 Step 2.5 スコープを確定形に改訂。コード変更なし。**Step 2.5 実装着手準備完了** |
| 0.24 | 2026-06-13 | **Phase 2 Step 2.5 完結 + Step 2.6 完結 + Step 2.7 完結 + Phase 2 全体完結**: Pattern B external-LLM interface (propose-context / adopt / same-world validation) + example packs 3 例 (python-fastapi-pytest / go-cli / node-cli-vitest) + strictness review (additionalProperties: 部分適用 = gate/proposal は strict、他は true 維持) + migration notes (`docs/migration-phase1-to-phase2.md`) + Phase 2 全体ジャーナル (`journal/phase2-summary.md`)。テスト 698 → 731 件 (+33)。Phase 3 申し送り 17 項目を `journal/phase2-step2-7.md` に列挙、user 相談に向けた繰越判定パートを §13.5 で必須プロセス化 |
| 0.25 | 2026-06-13 | **繰越リスト理念再精査**: BOM 残り read path を即修正 (NF-004 の徹底、中途半端な対応は違反)、WONTFIX 3 件 (JSON Patch move/copy / snapshot helper 統合 / SBOM 等) で繰越 17 → 13 件に整理。Codex セカンドオピニオン後、SBOM WONTFIX を撤回 (jsonschema 推移依存複数のため pip freeze だけでは P7 不足、依存 lock/hash を Phase 3 backlog に) |
| 0.26 | 2026-06-21 | **Phase 3 計画全面再構築 (本版)**: Phase 2 完結後の user 指摘で adapter 量産 (Go/Rust/.NET/Java/PHP/Markdown adapter) と Phase 4 (CI 連携) を廃止、Phase 3 を「機械責務側の最終整備」に再定義。Codex セカンドオピニオン 2 周 (2026-06-20 Phase 3 着手順 / 2026-06-21 横断レビュー) で承認。§14 Phase 3 計画を新設 (Step 3.0 detect 廃止 + project-context 導入 / Step 3.1 command runner 強化 + CI 雛形 / Step 3.2 依存解決固定 / Step 3.3 Phase 2 繰越実需回収)、§14.1 ライン引きの最終形、§14.3 Phase 4 廃止に伴う各項目の処理、§14.4 Phase 5 adapter なし設計の影響を明文化。Claude が前段で 2 回ラインを引き間違えた事実 (adapter 廃止 → P7 のため復活 → user 指摘で再廃止) は journal phase3-step3-0-prejournal.md に記録予定。コード変更なし、本 commit は spec 改訂のみ |
