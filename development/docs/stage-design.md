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
[1] qgb init                          — .quality-system/ 初期化
                                        (project-context.json 雛形 + knowledge/project-context.md を生成)
[2] 対象プロジェクトの自己定義         — 人間が project-context.md に書き、
                                        補佐 Agent が project-context.json に構造化
                                        (旧 [2] qgb detect は Phase 3 Step 3.0 で廃止)
[3] qgb design-stages                  — 段階設計フェーズ（本書）
       ├ 旧 (Phase 1〜2): rule-based proposer (`--commit` で適用)
       └ Phase 2 Step 2.5 以降: Pattern B
           ├ `qgb design-stages propose-context [--out FILE]` — 外部 LLM への入力素材
           └ `qgb design-stages adopt <proposal.json>`        — 外部 LLM の出力を検証 + 適用
       ↓ 確定
[4] qgb scaffold REQ   — REQ と契約と段階選択を生成
[5] qgb validate       — JSON 正本の検証 (project-context.json の schema 検査を含む)
[6] qgb validate-policy — 段階設計の品質検査 (knowledge orphan scan を含む)
[7] qgb run REQ        — 採用判定（evidence/latest/ 更新、全 stage を実行）
   + qgb check REQ     — 採用判定リハーサル (curated を書かない、Step 2.4)
   + qgb patch / add-waiver / add-knowledge  — 構造化編集 (Step 2.2 / 2.3)
```

`[3] qgb design-stages` は **対象プロジェクトの自己定義 (`.quality-system/project-context.{md,json}`)** と **設計例パック (`examples/`)** を主な入力源とし、`[4] qgb scaffold` の前提となる。旧版では `[2] qgb detect` の機械的検出結果も入力に含めていたが、Phase 3 Step 3.0 (2026-06-21) で detect を廃止し、対象プロジェクトの種別判定は LLM (Phase 5 スキル または補佐 Agent) の責務に統合した。理由: (a) 対象プロジェクトの広がり (ドキュメント群 / プロンプト集 / 設定群 / 法務テンプレ等) に adapter 抽象が追いつかなかった、(b) 検出結果が ALLOW/DENY 判定の根拠にならない、(c) 残置が Phase 5 スキルへの悪い few-shot 教材になる。詳細は `requirements_and_development.md` §6.2.2 / §14、`detailed-design.md` §14 を参照。

### 3.1 「軽量入口 (verify)」を持たない理由 — 部分検証は REQ 分割で解く

qgb は「検査範囲を絞って実行する軽量入口」(参考実装の八百万 `verify-req` 相当) を**持たない**。`qgb run` は常に対象 REQ の**全 stage を実行**し、証跡を残す。

理由は思想憲章 **P3 (保証対象の転換)** にある。qgb が保証するのはコードの同一性ではなく成立すべき状態であり、「コードが変わっていないこと」を前提にできない。LLM によるコード編集は全文が LLM を通るため、要修正部分以外が改変されない保証がない。したがって「特定の検証条件だけ追試し、触っていない部分は前回の合格が有効」という部分追試は、P3 に反するリスク (既に合格していた観点が知らぬ間に壊れる) を抱える。

**「対象を絞って検証したい」というニーズは、実行時に検査範囲を絞るのではなく、設計時に REQ を分割して満たす:**

- 大規模プロジェクトで部分部分が個別開発されるなら、**各部分を独立した REQ として切る**。各 REQ は自分の全 stage を `qgb run` で実行し、証跡を残す (P9: 各段階は独立して再実行可能)
- 部分だけ再検証したいときは、**その REQ だけを run する**。REQ 単位なら「全 stage を回す」ので、部分追試の危険な仮定 (触っていない部分は不変) が不要
- 結合を検証したいなら、**結合用の REQ を別途立て、その stage を設計する** (P1: 結合という要求を外部化する)。「部分 REQ が全部 ALLOW だから結合も大丈夫」という暗黙の合成はしない

この設計により、検査範囲が絞られても、それは「設計された独立 REQ」であり、P3 違反の仮定を置かずに済む。問題を解く層が「実行時の省略」から「設計時の責務分割」に移る。`qgb run` は実行時点の対象 REQ に対して**全 stage を同時点で再評価**するため、未実行 stage の過去結果が現在の判定に混ざることもない。

**設計上の含意:** REQ をどう切るかが品質設計の中心になる。粗すぎる REQ (1 つに多責務) は部分検証を不可能にし、責務の境界も曖昧にする。これは `qgb validate-policy` の検査対象 (推奨段階数 3〜7、単一責任、§9, §11) として機械的に効く。

> 補足: 八百万システムの参考実装には `ci-l1` / `verify-req` といった軽量入口があるが、その「軽さ」の本質は「検査範囲を絞る (一部の層だけ実行)」ことであり、八百万の階層化品質保証自体が「限定化した各検証を e2e レイヤまで含めて全部走らせる前提」で設計されている (原作者見解)。qgb が verify を持たないのは八百万思想からの逸脱ではなく、むしろその前提に忠実であろうとした結果である。詳細は `yaoyorozu-entry-points-investigation.md` を参照。

## 4. 入出力

### 入力

- 対象プロジェクトの構造（`.quality-system/project-context.json` の `technologies` / `artifact_kinds` / `platform`、および LLM が対象を Read で読んで得る理解。旧版の `qgb detect` 出力は Phase 3 Step 3.0 で廃止）
- 対象プロジェクトの目的（`.quality-system/project-context.json` の `purpose`、`.quality-system/knowledge/project-context.md` の自然言語記述）。Web UI / HTTP API / CLI / バッチ / 文書群 / プロンプト集 / ワークフロー定義 / 法務テンプレ など、プログラミング言語のソースに限らない
- ユーザーの明示指示
- Project Knowledge Base の既存情報 (`knowledge.jsonl`)
- 設計例パック (`examples/`) からの類似事例 (Phase 5 スキルが few-shot として参照)

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

3〜7 段階を推奨。**本レンジの正本は本書である** (憲章 v2.0 で P10 適用から移管。レンジは不易ではなく、運用知見に応じて本書の改訂だけで調整できる推奨設計)。

- 1〜2 段階：階層化の意味が薄い。qgb を使う価値も低い
- 3〜7 段階：実用的なレンジ
- 8 段階以上：単一責任原則の破綻サイン。責任を細かく切りすぎている可能性

`qgb validate-policy` はレンジ外を **警告** として通知する（エラーではない）。

入門用の `examples/generic-minimal/` のように意図的に 2 段階に絞る例は許容するが、`design-notes.md` で理由を明示する。

## 10. 設計プロセス

### 10.1 Phase 1: パターン A — ルールベース推定 + ユーザー確認 (legacy)

```text
$ qgb design-stages
Recommended template: examples/generic-minimal

Proposed stages:
  S1: コマンド成立    (depends_on: [])
  S2: 出力契約        (depends_on: [S1])
  S3: 異常系          (depends_on: [S1])

Adopt? [y/N/edit/select-different-template]
```

- Phase 1〜2 は `examples/generic-minimal` をデフォルトテンプレートとして提案する rule-based proposer (`qgb design-stages [--commit]`)
- 旧版では `qgb detect` の言語判定でテンプレートを切り替える設計だったが、Phase 1 完結時点ですでに「Python / Markdown 検出も generic-minimal にフォールバック」と決まっており detect 結果は banner にしか反映されなかった (Codex 計画レビュー 2026-05-31)。Phase 3 Step 3.0 で detect 自体を撤去
- Phase 2 Step 2.5 以降は **パターン B (Pattern B external-LLM interface) を推奨**: `qgb design-stages propose-context` + `adopt` で外部 LLM (Phase 5 スキル) が proposal を生成する。詳細は §10.2 を参照
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

思想憲章の制約を機械的に強制する。`qgb validate` (個別 JSON 仕様ファイルがスキーマに従っているか) とは別の責務として、正本ツリー全体の整合性と設計品質を見る。

### Phase 1 必須検査項目

| 検査 | 種別 | 思想根拠 |
|---|---|---|
| 必須正本ファイル `.quality-system/config.json` が存在する | error | P7 |
| 必須正本ファイル `.quality-system/policy.json` が存在する | error | P7 |
| stage id の重複なし | error | P9 |
| `depends_on` が DAG（循環なし） | error | P9 |
| `depends_on` の参照先がすべて定義済み stage id | error | P9 |
| 各 stage に `responsibility` が存在し、空文字でない | error | P9 |
| 各 stage に `verification_type` が定義済み列挙値 | error | P9 |
| REQ メタの `stage_id` が policy.json に存在する | error | P9 |
| REQ メタの `contract_ref` が指す contract が存在する | error | P7 |
| contract が canonical layout (`contracts/<REQ>/<stage>.json`) に従う | error | P7 |
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

NOT_READY 状態の REQ に対する `qgb run` は **gate.json を生成しない**。CLI exit code 2 + stderr にエラーメッセージを返す。

これは思想 P5（DENY の意味）を保護するための分離である。DENY は「揺らぎを安全に受け止めた結果」であり、構成ミスを含めるべきではない。

## 13. `manual_check` の Phase 1 仕様

Phase 1 では `manual_check` を以下のように扱う：

- `verification_type: manual_check` を policy で宣言することは可能
- ただし `manual_check` を含む段階を `required: true` で参照する REQ の `qgb run` は **NOT_READY エラー**
- 人間確認済みの結果を evidence として取り込む仕組みは Phase 1 では提供しない
- Phase 2 以降で `human_attestation` 型を別途設計する（再現性を担保する署名・タイムスタンプ・確認者 ID などを含む）

これは思想 P6（LLM 単独 ALLOW 禁止）の機械化であり、思想 P7（再現可能な証跡）と整合する。憲章 v2.0 の P12 により位置づけが明確化された: `manual_check` が NOT_READY であるのは評価者が人間だからではなく、評価が外部化された経路を通らないからである。`human_attestation` 型は、人間検査員の評価を機械検証可能な attestation として経路に渡す P12 の適用例として設計する。

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
