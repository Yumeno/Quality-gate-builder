# 段階設計フェーズ仕様 v1.0

## 1. 本書の位置づけ

本書は、qgb における「対象プロジェクトを見て適切な検証段階を設計するフェーズ」の仕様を定める。

本書は思想憲章 (`philosophy.md`) のうち、特に P9（単一責任原則）、P10（段階の可変性）、P6（LLM 単独 ALLOW 禁止）の機械化を担当する。

## 2. 目的

qgb は固定の段階体系（L1〜L6 など）を持たない。各プロジェクトは自プロジェクトの目的・構造・対象系に合わせて段階を設計する。

本フェーズは以下を実現する：

- 対象プロジェクトの構造分析に基づく段階の提案
- 思想憲章由来の制約の機械的強制
- ユーザー確認を経た段階の確定
- 確定した段階を `policy.json` に焼き込み

## 3. qgb ワークフロー上の位置

```text
[1] qgb init           — .quality-system/ 初期化
[2] qgb detect         — 対象系の言語/フレームワーク推定
[3] qgb design-stages  — 段階設計フェーズ（本書）
       ↓ 確定
[4] qgb scaffold REQ   — REQ と契約と段階選択を生成
[5] qgb validate       — JSON 正本の検証
[6] qgb verify REQ     — 軽量チェック（揮発側のみ）
[7] qgb run REQ        — 採用判定（evidence/latest/ 更新）
```

`[3] qgb design-stages` は `[2] qgb detect` の出力を入力とし、`[4] qgb scaffold` の前提となる。

## 4. 入出力

### 入力

- 対象プロジェクトの構造（`qgb detect` の出力：言語、フレームワーク、テストランナー、ディレクトリ構成）
- 対象プロジェクトの目的（Web UI / HTTP API / CLI / バッチ / 文書群 / プロンプト集 / ワークフロー定義 など）
- ユーザーの明示指示
- Project Knowledge Base の既存情報
- 設計例パック (`examples/`) からの類似事例

### 出力

- `policy.json` の `stages[]` フィールド（段階の定義）
- 段階間の依存関係（DAG）
- 各段階の検査種別と必要な契約フィールド

## 5. 段階記述の二段構造

qgb は段階を 2 つのレイヤで管理する：

| レイヤ | 場所 | 役割 |
|---|---|---|
| 段階の定義 | `policy.json` の `stages[]` | プロジェクト全体で共有する段階体系 |
| 段階の選択 | REQ メタの `stages[]` | 各 REQ が依拠する段階のサブセット |

これにより：

- プロジェクト全体の段階体系を `policy.json` 一箇所で把握できる
- REQ ごとに必要な段階を自由に選べる（宣言外は判定対象外）
- 段階定義の変更は `policy.json` 一点修正で済む

## 6. policy.json の段階記述スキーマ

### 必須フィールド

```json
{
  "schema_version": "1.0",
  "policy_id": "default",
  "stages": [
    {
      "id": "S1",
      "name": "コマンド成立",
      "responsibility": "CLI コマンドが終了コード 0 で完了する",
      "depends_on": [],
      "verification_type": "command",
      "required_contract_fields": ["command", "expected_exit_code"]
    },
    {
      "id": "S2",
      "name": "出力契約",
      "responsibility": "出力ファイルが JSON Schema を満たす",
      "depends_on": ["S1"],
      "verification_type": "json_schema",
      "required_contract_fields": ["target", "schema"]
    }
  ]
}
```

### 各フィールドの仕様

| フィールド | 必須 | 説明 |
|---|---|---|
| `id` | 必須 | 段階の識別子。自由命名（`S1`, `L1`, `cmd` などすべて可）。プロジェクト内で一意 |
| `name` | 必須 | 段階の表示名 |
| `responsibility` | 必須 | この段階が見る単一の責務（一文）。複数センテンスは警告 |
| `depends_on` | 必須（空配列可） | 依存する段階 id のリスト。DAG（循環禁止） |
| `verification_type` | 必須 | 検査種別の列挙値（後述） |
| `required_contract_fields` | 必須 | 各 REQ で contract.json に書くべきフィールド名のリスト |

### 検査種別 (`verification_type`) の列挙値

Phase 1 で必須サポート：

- `command` — 外部コマンドを実行し、終了コードとログを検査
- `file_exists` — ファイルの存在を検査
- `substring_match` — テキストファイル内の文字列包含を検査
- `json_schema` — JSON ファイルが JSON Schema を満たすかを検査
- `manual_check` — 人間判断が必要（採用判定の根拠にできない）

Phase 2 以降の拡張余地：

- `http_response` — HTTP エンドポイントの応答検査
- `regex_match` — 正規表現マッチ
- `link_integrity` — Markdown 内部リンクの健全性
- `glossary_consistency` — 用語表に基づく表記統一

`manual_check` の扱いは思想 P6 と P1 を守る：`manual_check` を含む段階を必須宣言した REQ の `qgb run` は NOT_READY エラーとする（後述）。

## 7. REQ メタの段階選択

各 REQ は `policy.json` で定義された段階のサブセットを宣言する：

```json
{
  "req_id": "REQ-APP-001",
  "stages": [
    {
      "stage_id": "S1",
      "contract_ref": ".quality-system/contracts/REQ-APP-001/S1.json",
      "required": true
    },
    {
      "stage_id": "S2",
      "contract_ref": ".quality-system/contracts/REQ-APP-001/S2.json",
      "required": true
    }
  ]
}
```

- 宣言外の段階は判定対象外（出現しない）
- `required: true` の段階のいずれかが failed のとき DENY
- `required: false` は将来の拡張用（任意段階、Phase 1 では全段階を実質 required として扱う）
- `contract_ref` の指す contract.json には、`policy.json` の `required_contract_fields` が含まれていなければならない

## 8. 段階間の依存関係（DAG）

### 採用するモデル

線形ではなく DAG。

理由：

- 「段階 A と B は独立、ただし C は両方に依存」のようなケースが対象系次第で出現
- 線形（全段階が前段に依存）は DAG の特殊ケース
- core の `bin/mihashira` の実行順（L2→L3→L4→L5→L6→L1）も実質的に DAG

### 制約

- `depends_on` の参照先はすべて同一 `policy.json` 内に定義済みの id
- 循環禁止
- `qgb validate-policy` で機械検査する

## 9. 段階数の推奨レンジ

3〜7 段階を推奨。

- 1〜2 段階：階層化の意味が薄い。qgb を使う価値も低い
- 3〜7 段階：実用的なレンジ
- 8 段階以上：単一責任原則の破綻サイン。責任を細かく切りすぎている可能性

`qgb validate-policy` はレンジ外を **警告** として通知する（エラーではない）。

入門用の `examples/generic-minimal/` のように意図的に 2 段階に絞る例は許容するが、`design-notes.md` で理由を明示する。

## 10. 設計プロセス

### 10.1 Phase 1: パターン A — ルールベース推定 + ユーザー確認

```text
$ qgb design-stages
Detected: Python CLI (argparse-based)
Recommended template: examples/python-cli-pytest

Proposed stages:
  S1: コマンド成立    (depends_on: [])
  S2: 出力契約        (depends_on: [S1])
  S3: 異常系          (depends_on: [S1])

Adopt? [y/N/edit/select-different-template]
```

- `qgb detect` の出力から類似テンプレートを `examples/` から選ぶ
- テンプレートを起点に段階を提案
- ユーザーが y / n / edit / select-different-template から選択

### 10.2 設計フェーズの 2 段階化

提案フェーズと採用フェーズを分ける：

```text
qgb design-stages              # 提案フェーズ（policy.json は書かない）
   ↓ ユーザー確認
qgb design-stages --commit     # 採用フェーズ（policy.json に書き込み）
   ↓ 自動実行
qgb validate-policy            # 設計品質検査
```

採用フェーズは `qgb validate-policy` をパスしないと完了しない。これにより、スキルや LLM が甘い段階を提案しても、検査器が止める構造になる。

### 10.3 Phase 2-3: パターン B — 対話的設計

```text
$ qgb design-stages --interactive
このプロジェクトで何を保証したいですか?
  > データ変換が正しく行われること、不正入力が安全に拒否されること

それを階層化すると次のように分けられます:
  S1: 入力スキーマ妥当性
  S2: 変換成立（コマンド exit code）
  S3: 出力スキーマ妥当性
  S4: 異常系（不正入力の安全な拒否）

Adopt? [y/N/edit]
```

自然言語入力からの段階分解は LLM が担う。

### 10.4 Phase 5: スキル本体の責務

スキルは段階設計の自律実行者ではなく、設計補助者として動く：

1. 対象プロジェクトを Read / Grep で分析
2. `examples/` から近い例を 1〜3 個選ぶ
3. design-notes.md を読んで設計判断を学ぶ
4. 対象プロジェクトに合わせて段階案を提示
5. **ユーザーと対話して確定**（必須ステップ）
6. `policy.json` / REQ メタ / contract 雛形を書く
7. `qgb validate-policy` で機械検査

最終的な採用は `policy.json` に外部化され、`qgb validate-policy` が検査する。思想 P2「AI は決定装置ではなく探索装置」をスキル自身にも適用する。

### 10.5 設計フェーズの再実行

段階を見直したいとき：

```text
$ qgb design-stages --revise
```

- 既存の `policy.json` を読み込み、差分を提案
- 段階の `id` を変えると既存 REQ メタの `stage_id` 参照が壊れるため、`id` 変更は警告 + 連動更新オプション
- 段階の追加・削除は柔軟に許す。REQ メタは「宣言外段階は対象外」なので自動的に整合する

## 11. policy 設計検査器（`qgb validate-policy`）

思想憲章の制約を機械的に強制する。

### Phase 1 必須検査項目

| 検査 | 種別 | 思想根拠 |
|---|---|---|
| stage id の重複なし | error | P9 |
| `depends_on` が DAG（循環なし） | error | P9 |
| `depends_on` の参照先がすべて定義済み stage id | error | P9 |
| 各 stage に `responsibility` が存在し、空文字でない | error | P9 |
| 各 stage に `verification_type` が定義済み列挙値 | error | P9 |
| REQ メタの `stage_id` が policy.json に存在する | error | P9 |
| REQ メタの `contract_ref` が指す contract が存在する | error | P7 |
| contract.json に `required_contract_fields` がすべて含まれる | error | P9 |
| `required: true` の stage 集合が空でない REQ | error | P1 |
| `manual_check` のみで構成される REQ は警告 | warning | P6 |
| 段階数が推奨レンジ（3〜7）に収まる | warning | P9 |

### Phase 2 以降の拡張検査

- `responsibility` が一文か（複数センテンスは単一責任原則違反のサイン、警告）
- 検査種別の偏り（全 stage が `file_exists` だけなど、警告）
- 段階の名前と responsibility の整合性（LLM 補助）

## 12. NOT_READY の生成

`qgb validate-policy` が error を検出した状態、または以下に該当する状態を NOT_READY とする：

- `qgb validate` が失敗する状態（policy/REQ/contract のスキーマ違反）
- `contract_ref` の指す contract.json が存在しない
- REQ メタの `stage_id` が `policy.json` の stages に未定義
- 必須段階に対応する実行可能 contract が無い
- 段階の depends_on に未定義の id が含まれる、または DAG でない（循環）
- declared stages が空の REQ
- `manual_check` を含む REQ の `qgb run`（Phase 1 仕様）

NOT_READY 状態の REQ に対する `qgb run` および `qgb verify` は **gate.json を生成しない**。CLI exit code 2 + stderr にエラーメッセージを返す。

これは思想 P5（DENY の意味）を保護するための分離である。DENY は「揺らぎを安全に受け止めた結果」であり、構成ミスを含めるべきではない。

## 13. `manual_check` の Phase 1 仕様

Phase 1 では `manual_check` を以下のように扱う：

- `verification_type: manual_check` を policy で宣言することは可能
- ただし `manual_check` を含む段階を `required: true` で参照する REQ の `qgb run` は **NOT_READY エラー**
- 人間確認済みの結果を evidence として取り込む仕組みは Phase 1 では提供しない
- Phase 2 以降で `human_attestation` 型を別途設計する（再現性を担保する署名・タイムスタンプ・確認者 ID などを含む）

これは思想 P6（LLM 単独 ALLOW 禁止）の機械化であり、思想 P7（再現可能な証跡）と整合する。

## 14. 既存スペックとの差分

本仕様は要件定義書 v0.3 に統合される。v0.2 からの主要な差分：

- §6.5「L1〜L6 設計」を本書に置換（固定段階体系の削除）
- §F-006「テスト階層生成」を本書に置換（段階設計フェーズへの転換）
- §F-007「テスト段階ポリシー制御」を簡素化（`required/optional/not_configured/out_of_scope/waived` を整理）
- §6.3 CLI 仕様に `qgb design-stages` と `qgb validate-policy` を追加
- §F-016 TDD mode の `mode` 概念削除、`phase` のみで条件分岐

## 15. 関連文書

- `philosophy.md` — 思想憲章（本書の上位制約）
- `requirements_and_development.md` — 要件定義書
- `framework-shape.md` — フレームワーク境界
- `examples/` — 設計例パック（本書の具体例）
