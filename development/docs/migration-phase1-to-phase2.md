# Migration Notes: Phase 1 → Phase 2

Phase 2 (「編集を安全にする」) で導入された変更のうち、既存の `.quality-system/` 構造に影響するものを列挙する。

## Schema 変更

### gate.schema.json / gate.runtime.schema.json

- **`mode` フィールド追加** (Step 2.4): `qgb check` のリハーサル gate に `mode: "check"` が付与される。公式 `qgb run` の gate は `mode` を持たない (不在 = 公式)。schema 消費者は `mode` の不在を公式の印として確認すること。
- **`stages[].result` に `"waived"` 追加** (Step 2.4 補修 A3): Step 7 で導入された waived stage が揮発側 schema でも正式に enum に追加。
- **`paths.curated_latest_dir` の条件化** (Step 2.4): `mode: "check"` のとき禁止、不在のとき必須 (allOf 条件)。

### proposal.schema.json (新設, Step 2.5)

- 外部 LLM ツールの出力を受け取る新 schema。`additionalProperties: false` (外部入力境界 NF-007)。
- `proposal_type: "policy_stages"` のみ Phase 2 でサポート。

## 新しい CLI コマンド

| コマンド | Step | 概要 |
|----------|------|------|
| `qgb patch <target> <patch.json>` | 2.2 | JSON Patch (4 op) + atomic swap |
| `qgb add-waiver <REQ> <stage> --reason "..."` | 2.3 | waiver 登録 + knowledge 記録 |
| `qgb add-knowledge <file>` | 2.3 | knowledge.jsonl への append |
| `qgb check [REQ]` | 2.4 | official run rehearsal |
| `qgb dev [REQ]` | 2.4 | check の alias (Phase 3 で watch mode) |
| `qgb design-stages propose-context` | 2.5 | context export for external LLM |
| `qgb design-stages adopt <proposal.json>` | 2.5 | proposal import + validate + apply |

## 既存コマンドへの影響

- `qgb validate` / `qgb validate-policy` / `qgb run` / `qgb scaffold` / `qgb init` / `qgb detect`: **変更なし**。
- `qgb design-stages [--json] [--commit]`: **変更なし** (legacy flag-form は完全温存、subcommand 併存)。

## .quality-system/ ディレクトリ構造の変更

- `artifacts/<REQ>/checks/` が `qgb check` の揮発出力先として追加 (Step 2.4)。`artifacts/` は init が .gitignore に予約済みのため追加の gitignore 手当て不要。
- `knowledge/knowledge.jsonl` への append が `add-waiver` / `add-knowledge` から実行される (Step 2.3)。

## BOM 耐性 (Step 2.5 補修)

PowerShell 5.1 の `Out-File` が書き込む UTF-8 BOM 付きファイルを、以下の読み込みパスで tolerate するよう変更:
- `loader.py` (`_read_json`)
- `validate.py` (`_load_json`)
- `patch_apply.py` (`_load_json_file`)
- `proposal.py` (proposal 読み込み / current policy 読み込み)

残り read path (runner.py / scaffold.py / design_stages.py / edit_commands.py / knowledge.py) は Phase 3 で網羅判断。

## additionalProperties 方針

Phase 2 完了時点の判断:

| Schema | Root | 理由 |
|--------|------|------|
| gate.schema.json | **false** | 採用判定証跡は厳格固定 |
| proposal.schema.json | **false** | 外部入力境界 (NF-007) |
| 上記以外 (policy/req-meta/contract/config/knowledge/runtime) | true | Phase 3 adapter 拡張で言語固有フィールド追加が必要 |

`--strict` フラグの実体実装は Phase 3 送り。
