# qgb JSON Schemas

このディレクトリには qgb の機械正本 JSON のスキーマを置く。

## ファイル

| ファイル | 役割 | additionalProperties |
|---|---|---|
| `config.schema.json` | `.quality-system/config.json` の構造 | true |
| `policy.schema.json` | `.quality-system/policy.json` の構造（段階定義） | true |
| `req-meta.schema.json` | `.quality-system/req/<REQ>.meta.json` の構造（REQ ごとの段階選択） | true |
| `contract.schema.json` | `.quality-system/contracts/<REQ>/<stage>.json` の構造 | true |
| `gate.schema.json` | `evidence/<REQ>/latest/gate.json` の構造（**採用判定証跡、厳格**） | **false** |
| `gate.runtime.schema.json` | `artifacts/<REQ>/runs/<ts>/gate.json` と `artifacts/<REQ>/checks/<ts>-<runid>/gate.json` の構造（揮発、拡張可） | true |
| `knowledge.schema.json` | `knowledge.jsonl` の各行の構造 | true |
| `proposal.schema.json` | `qgb design-stages adopt` が受け取る外部 proposal (Pattern B)。`proposal_type: "policy_stages"` = policy.json#stages の宣言的全量置換 | **false** (外部入力境界、NF-007) |

## 厳格性の使い分け

採用判定証跡（コミット対象）はスキーマレベルで厳格に固定する。揮発側や設定系は将来拡張のため緩く取る。これは `yaoyorozu-system/core` の `mihashira-gate.schema.json` の方針に倣っている。

## verification_type の列挙値

Phase 1 で対応:

- `command` — argv 配列で外部コマンドを実行、終了コードと出力を検査
- `file_exists` — ファイル存在
- `substring_match` — テキスト内文字列包含
- `json_schema` — JSON Schema 検証
- `manual_check` — 人間判断（思想 P6 により ALLOW 単独根拠不可、Phase 1 では NOT_READY を返す）

`contract.schema.json` は base 構造を定義し、`verification_type` ごとに `if/then` で必須フィールドを切り替える。

## 設計判断のポイント

- **段階 id は自由命名**: policy.schema.json は `id` の重複や DAG を schema では検査せず、ランタイム (`qgb validate-policy`, #21) で検査する。
- **`responsibility` は単一文を要求**: minLength: 1 にとどめ、複数センテンスかどうかは validate-policy 側で警告する。
- **REQ id 形式**: `^REQ-[A-Z0-9]+-[0-9]{3,}$` (core 互換)。
- **timestamp 二系統**: `YYYY-MM-DDTHHMMSSZ` (履歴・ファイルパス互換) と RFC3339 (ツール互換) を両方記録。
- **gate.json の `if/then` 制約**: `status: ALLOW` のとき `failed_stage` は空文字、`decision.result` は `ALLOW`、全ての非 waived `stages[].result` は `passed` かつ passed が 1 件以上。`status: DENY` のとき `decision.result` は `DENY` で、(a) `failed_stage` 非空 + 少なくとも 1 つの `failed`、または (b) 全 stage が `waived` (判定材料なし、Step 7) のいずれか。Phase 2 Step 2.4 補修 A3 で揮発側 (`gate.runtime.schema.json`) も同じ意味論に揃えた (旧版は `waived` 非対応のまま乖離していた)。
- **`mode` フィールド (Phase 2 Step 2.4)**: `qgb check` のリハーサル gate のみ `mode: "check"` を持つ。**公式 `qgb run` の gate は `mode` を持たない (不在 = 公式)**。`mode: "check"` のとき `paths.curated_latest_dir` は禁止 (curated は更新されていないため)、不在のとき必須。注意: mode=check の文書も厳格 schema (`gate.schema.json`) を通過するので、「schema valid = 公式 gate」とは読めない — 機械消費者は `mode` の不在を公式の印として確認すること。
- **`exit_code` は null 許容、ただし必須**: `file_exists` や `json_schema` など外部プロセスを起動しない stage では null を入れる（フィールド自体は必須）。
- **採用判定証跡の stage は contract_ref / log_ref / exit_code が必須**: 思想 P7（再現可能な証跡）を schema レベルで強制。揮発側 (`gate.runtime.schema.json`) では緩い。
- **`format: date-time` は qgb 独自 format checker で強制**: jsonschema の built-in には date-time 検査が含まれないため、`qgb.core.schema` で stdlib 経由の RFC3339 チェッカーを追加登録（NF-010 依存最小化）。

## 思想憲章との対応

| スキーマ要素 | 対応する思想項目 |
|---|---|
| `gate.schema.json` の `decision.meaning` 必須化 | P5（ALLOW/DENY の意味の限定） |
| `gate.schema.json` の `basis[]` 必須化 | P7（再現可能な証跡だけが採用根拠） |
| `policy.schema.json` の `responsibility` 必須化 | P9（単一責任原則） |
| `knowledge.schema.json` の `requires_human_review` | P8（外部取得コンテンツはプロンプトではない） |
| `contract.schema.json` の `command` を argv 配列に限定 | NF-007（安全性、shell 文字列禁止） |

## fixture とテスト

各スキーマには `tests/fixtures/schemas/<name>.success.json` と `<name>.failure.json` が用意されている（例外的に schema 自身が緩い場合、success のみ）。`tests/test_schemas.py` で：

1. スキーマ自身が JSON Schema として有効
2. success fixture が合格
3. failure fixture が不合格

を検証する。
