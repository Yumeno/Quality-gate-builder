# quality-gate-builder 詳細設計 v0.7 (Phase 1 Step 0〜5 + 補修確定範囲、Codex レビュー反映済み)

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

`skills/source/`、`tools/`、`dist/skills/` は Phase 5 で追加予定。`examples/` には Step 8 で `python-cli-pytest/` と `markdown-docs/` を追加する。

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
| `validate-policy` | 6 | parser 登録のみ | 段階設計の品質 + 正本ツリー整合性 |
| `verify` | 6 | parser 登録のみ | 軽量チェック (揮発側のみ) |

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

- 対象系の言語/フレームワーク推定 → `qgb detect` (Step 6)
- 段階設計の中身 → `qgb design-stages` (Step 6)
- REQ + contract 雛形 → `qgb scaffold` (Step 6)
- 初期状態の整合性チェック → `qgb validate` (Step 2) と `qgb validate-policy` (Step 6) で必要に応じて

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

### 7.4 gate.json 内 timestamp 規約 (Step 5 への申し送り)

| フィールド | 形式 | 用途 |
|---|---|---|
| `timestamp_utc` | `YYYY-MM-DDTHHMMSSZ` (`:` なし、Z 終端) | `paths.run_dir` パスのサフィックス、ファイル名互換 |
| `timestamp_rfc3339` | `YYYY-MM-DDTHH:MM:SSZ` (`:` あり) | ツール互換、解析しやすい |

両者は **同一時刻** を表現する。Step 5 の実装では：

- 単一の `datetime.now(timezone.utc)` 呼び出しから両形式を生成
- `paths.run_dir` のサフィックスは `timestamp_utc` と必ず一致
- `tests/test_examples.py::test_gate_timestamps_are_mutually_consistent` が CI で検証

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
| `qgb/core/preflight.py` | READY/NOT_READY 判定。スキーマ違反 (validate を内部呼び出し) + 必須正本欠落 + `stage_id` 解決 + `contract_ref` 解決 + `verification_type` の一致 + `depends_on` DAG + `manual_check` の required 段階拒否 + Phase 1 で runnable な type 限定 |
| `qgb/core/runner.py` | 採用段階を 1 件ずつ実行し `StageResult` を返す。`depends_on` 失敗時は実行スキップ (failed 記録) |
| `qgb/core/decision.py` | 採用段階の結果から `ALLOW` / `DENY` + `failed_stage` (最初の失敗 required 段階) を決定 + phase 別の `decision.meaning` を選択 |
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
- 各 keyword の char offset をログに記録 (`hello: found at byte offset 0` 形式、※将来的に正確な byte offset 表記に修正予定)
- UTF-8 decode 失敗時は failed
- project_root 外への path escape は failed として記録 (Step 5 補修 R1)

両 type とも `exit_code` は `null` (外部プロセス非起動)。target の root escape チェックは `loader.resolve_project_relative()` を `contract_ref` と共有することで、契約パスと検査対象パスの両方が「project 内部のみ」という不変条件を一箇所で守る (P9 / NF-007)。

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

#### 同一秒衝突回避 (Step 5 補修 R2)

`evidence._resolve_run_dir(runs_root, timestamps)` が `write_evidence` の前段で動く:

- `runs_root/<compact>/` が既存なら 1 秒ずつ進めた synthetic timestamp に切り替え (最大 60 秒前進)
- 戻り値は `(確定 run_dir, 確定 Timestamps)` のタプルで、gate.json には確定後の値が焼き込まれる
- 60 秒連続で衝突が続いた場合は `microsecond` をサフィックスにしたフォールバック (compact pattern からは外れるが、揮発側 schema は permissive なので OK)

これにより同一プロセスから 3 回連続で `qgb run` を叩いても、各 run_dir が独立し過去 run の証跡が上書きされない (P7)。`timestamp_utc` と `paths.run_dir` のサフィックス一致は維持される。

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
| 揮発 | `.quality-system/artifacts/<REQ>/runs/<compact>/` | `qgb run` / `qgb verify` (Step 6) | **No** (`.gitignore`) |
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

合計 **178 件、全成功、ruff 警告ゼロ**。

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

以下は本書時点では未確定。各 Step で確定し、本書を改訂する。

| 項目 | 確定予定 Step |
|---|---|
| `qgb run --yes` フラグ (実行前確認プロンプト) | Step 6 |
| `qgb verify` (揮発側のみで gate.json を更新しない軽量チェック) | Step 6 |
| `qgb validate-policy` の実装と preflight モジュール分割 (下記) | Step 6 |
| `qgb detect` の対象系推定ロジック | Step 6 |
| `qgb design-stages` 提案フェーズと採用フェーズの分離 | Step 6 |
| `qgb scaffold` の REQ + contract + テスト雛形生成 | Step 6 |
| TDD phase=red の expected-failure 本実装 (gate.json で DENY を期待値として扱う) | Step 7 |
| `command` / `json_schema` verification_type | Step 7 / 8 |
| `manual_check` を含む REQ への注釈フロー (Phase 2 設計の入口) | Step 7 |
| `waived` 段階の knowledge.jsonl 記録 + `basis[]` への `KNOWLEDGE-*` 追加 | Step 7 |
| 設計例パック 2 例追加 (python-cli-pytest / markdown-docs) | Step 8 |
| knowledge 追加コマンド、導入マニュアル、依存調査ポリシー文書 | Step 9 |

### Step 6 への申し送り (Codex Step 5 レビュー由来)

#### preflight モジュールの再分割

`qgb run` の preflight をそのまま validate-policy の中核にすると責務が混ざる。validate-policy は「設計品質と整合性を診断する」コマンドであり、`manual_check_required` / `unsupported_verification_type` は run 側 blocker だが validate-policy 側では「Phase 1 runtime 未対応」という別ランクの診断に過ぎない。Step 6 で次のように分割する想定:

```python
validate_schema_sources(project_root)        # 既存 run_validate
inspect_policy_graph(policy)                  # DAG / dangling / topological order
resolve_adopted_stages(root, req, policy, meta)  # REQ 固有
check_runtime_support(adopted)                # qgb run 固有 (manual_check / unsupported)
run_preflight()                               # 上記を組み合わせる薄い orchestration
```

加えて `PreflightIssue.severity` を導入し、`blockers` と `warnings` を分けて validate-policy の警告 (推奨段階数レンジ外など) を載せられる構造にする。

#### Step 5 補修で扱いきれなかった残課題

- **REQ meta 実行順がトポロジカル順を満たすか未検証** (Codex M1): `[S2, S1]` の順で書かれた場合に S2 が S1 未実行で走るリスク。`resolve_adopted_stages` の責務として Step 6 で実装
- **`_replace_dir_contents()` が非 atomic** (Codex M4 / M5): `gate.json` と `stages/` の不整合や stale log 残存。`latest.tmp-<ts>` で書いて rename する方式が望ましい
- **byte offset 表記** (Codex L2): substring_match のログは現状 code point index。`char offset` 表記に変えるか、UTF-8 byte offset を計算する
- **`LoaderError.wrong_type` の preflight 側分類**: `invalid_json` 扱いに混ざる箇所がある (Codex L3)
- **`QGB_KEEP_RUNS` 不正値の silent default** (Codex L4): stderr warning か JSON report に warning を出す

## 13. 改訂履歴

| 版 | 日付 | 内容 |
|---|---|---|
| 0.1 | 2026-05-21 | Phase 1 Step 0〜2 確定範囲を初版として記録 |
| 0.2 | 2026-05-21 | Phase 1 Step 3 (qgb init) を反映。§6 を新設 |
| 0.3 | 2026-05-21 | Step 3 補修 (Codex レビュー反映): InitError / NOT_READY 化 / 構造化 JSON 置換 / .gitignore 端処理を §6.3, §6.5 に反映 |
| 0.4 | 2026-05-21 | Phase 1 Step 4 (examples/generic-minimal/) を反映。§7 を新設、§2 リポジトリ構造に examples/ を追加 |
| 0.5 | 2026-05-21 | Step 4 補修 (Codex レビュー反映): log_ref 実体追加 / REQ-design-notes 矛盾解消 / 整合性テスト 5 層化 / §7.4 timestamp 規約と §7.5 basis 規約を Step 5 申し送りとして明文化 |
| 0.6 | 2026-05-21 | Phase 1 Step 5 (qgb run 縦串) を反映。§8 を新設し loader/preflight/runner/decision/evidence の 5 モジュール責務、preflight 検査、verification_type 実装、timestamp/basis 生成、2 系統出力、QGB_KEEP_RUNS を確定。§10 テスト件数 173 件に更新、§11 思想憲章マトリクスに P6 機械化を追加 |
| 0.7 | 2026-05-22 | Step 5 補修 (Codex レビュー反映): R1 contract.target の root escape 防止 (loader.resolve_project_relative を共通化)、R2 同一秒 run_dir 衝突回避、R3 optional stage と ALLOW schema の矛盾解消 (全 adopted stage を判定対象に)、reference gate.json の `evidence-reference/` 退避、§12 に Step 6 申し送り (preflight 再分割 / severity / topological order / atomic write / byte offset / loader error / QGB_KEEP_RUNS warning) を追加 |
