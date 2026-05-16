# quality-gate-builder 要件定義書・基本設計書 v0.2

## 1. 文書概要

### 1.1 文書名

quality-gate-builder 要件定義書・基本設計書 v0.2

### 1.2 目的

本書は、任意の対象プロジェクトに対して、要求・契約・テスト・証跡・判定ゲートからなる品質確認系を生成するための `quality-gate-builder` について、要件および基本設計を定義する。

本システムは、LLMによる生成物や評価を無条件に信頼するのではなく、要求、機械的契約、自動テスト、証跡、ユーザー判断を組み合わせることで、成果物の採用可否を説明可能にすることを目的とする。

### 1.3 v0.2での主な更新点

本版では、以下の論点を統合した。

- Phase 1の範囲を「Pythonバックエンド + 導入マニュアル付きMVP」として明確化
- 対象プロジェクトの言語と、品質ゲート基盤の実装言語を分離
- Phase 1の実装コアはPythonを前提とする方針を追加
- JSONを機械正本とする方針を追加
- Project Knowledge Baseを追加
- ユーザー裁量によるテスト段階の対象外・免除設計を追加
- TDD modeを追加
- 依存ライブラリ選定時のサプライチェーンリスク調査要件を追加
- PyPI等のパッケージレジストリもリスクを持つ前提で扱う方針を追加

### 1.4 対象読者

- quality-gate-builderを設計・実装する開発者
- AI支援開発環境を構築する技術者
- LLMを用いてソフトウェア開発・検証を行うユーザー
- 要件定義、テスト設計、レビュー、監査に関与する担当者

### 1.5 本書の位置づけ

本書は、quality-gate-builderの正本となる要件定義・基本設計書である。

補足メモや議論ログが存在する場合も、実装判断においては本書を優先する。

---

## 2. 背景と課題

### 2.1 背景

LLMを用いた開発支援では、コード生成、設計補助、テスト生成、レビュー、リファクタリングなどを高速化できる。

一方で、LLMの出力や評価は確率的に揺れる。複数回評価して中央値を取る方法もあるが、その評価値が正規分布に従う保証はない。また、各試行が独立同分布である保証もない。

したがって、LLMの主観評価をそのまま品質保証の根拠とすることは危険である。

品質判断には、外部化された要求、検査可能な契約、自動テスト、実行証跡、明示的な採否判断が必要である。

### 2.2 解決すべき課題

本システムは、以下の課題を解決する。

1. LLM生成物の採用可否を、LLMの主観評価だけに依存せず判定したい。
2. 要求・契約・テスト・証跡・判定をリポジトリ内に明示したい。
3. 対象プロジェクトの言語・フレームワークに依存しない品質ゲート系を構築したい。
4. 既存プロジェクトへの後付け導入だけでなく、TDD開始時点からの導入にも対応したい。
5. ユーザーが提示した前提、外部調査情報、設計判断を根拠として保持したい。
6. テスト段階の必須・任意・対象外・免除をユーザー裁量で制御したい。
7. 判定結果とその根拠を証跡として残したい。
8. 依存ライブラリ自体のサプライチェーンリスクを管理したい。

---

## 3. システム概要

### 3.1 システム名

- リポジトリ名: `quality-gate-builder`
- 表示名: Quality Gate Builder
- 短縮名: `qgb`

### 3.2 基本方針

1. LLM評価を単独の合格根拠にしない。
2. ALLOWは「定義済み検査に通過した」ことのみを意味する。
3. 未定義・未設定・判断不足は、原則としてREVIEWとする。
4. ユーザーが明示的に対象外または免除を定義した場合は、その理由を証跡化したうえで判定対象から除外できる。
5. 対象プロジェクトの言語と、qgb本体の実装言語は分離する。
6. Phase 1では、qgb本体をPythonで実装する。
7. 機械正本はJSONとする。
8. REQ本文や人間向け要約はMarkdownとする。
9. 外部調査情報やユーザー判断はProject Knowledge Baseに保持する。
10. 依存ライブラリは最小限とし、採用時にはセキュリティ調査を行う。

### 3.3 対象プロジェクト

対象プロジェクトは、特定のプログラミング言語に限定しない。

想定対象は以下である。

- Pythonプロジェクト
- TypeScript / Node.jsプロジェクト
- Goプロジェクト
- Rustプロジェクト
- .NETプロジェクト
- Javaプロジェクト
- PHPプロジェクト
- CLIツール
- バッチ処理
- Web UI
- HTTP API
- ドキュメント群
- 設定ファイル群
- プロンプト集
- ワークフロー定義
- その他、機械的検査や証跡化が可能な成果物

### 3.4 qgb本体の実装言語

Phase 1では、qgb本体をPythonで実装する。

理由は以下である。

- Windows、macOS、Linuxで動作させやすい
- JSON、Markdown、ファイル操作、サブプロセス実行との相性がよい
- CLI実装が容易
- テンプレート生成と証跡生成が容易
- LLMユーザーがローカルで扱いやすい
- MVPの開発速度が高い

対象プロジェクトがPython以外であっても、qgb本体はPythonで動作し、対象プロジェクト固有の処理はアダプタ経由で実行する。

### 3.5 システム構成

```text
quality-gate-builder/
  qgb/
    __main__.py
    cli.py
    core/
    adapters/
    schemas/
    templates/
  docs/
  examples/
  skills/
  tests/
  pyproject.toml
```

### 3.6 生成される対象プロジェクト側構造

```text
project-root/
  .quality-system/
    config.json
    policy.json
    req/
      REQ-APP-001.md
      REQ-APP-001.meta.json
    contracts/
      REQ-APP-001/
        contract.json
    knowledge/
      knowledge.jsonl
      source-index.json
      project-context.md
    evidence/
      REQ-APP-001/
        latest/
          gate.json
          summary.md
          command.log

  tests/
    quality/
      L1_behavior/
      L2_state/
      L3_boundary/
      L4_flow/
      L5_contract/
      L6_experience/

  scripts/
    quality-gate.ps1
```

対象プロジェクトの慣習により、`tests/quality` や `scripts` の配置は変更可能とする。

---

## 4. 用語定義

| 用語 | 意味 |
|---|---|
| REQ | Requirement。成立すべき要求を記述した正本。 |
| CONTRACT | 機械的に検査可能な契約。UI、API、CLI、ファイル、DB状態などを対象とする。 |
| TEST | 要求や契約を検証する自動テスト。 |
| EVIDENCE | 実行結果、ログ、JUnit XML、スクリーンショット、判定結果などの証跡。 |
| GATE | REQ単位で検査を実行し、ALLOW / DENY / REVIEWを返す判定機構。 |
| ADAPTER | 言語、フレームワーク、テストランナーごとの差分を吸収する接続層。 |
| Project Knowledge Base | 対象プロジェクトの前提情報、外部調査情報、ユーザー判断を保持する根拠ストア。 |
| ALLOW | 定義済みの必須検査に通過した状態。完全な正しさは保証しない。 |
| DENY | 定義済みの必須検査に失敗した状態。 |
| REVIEW | 機械判定では不足し、人間確認または追加定義が必要な状態。 |
| out_of_scope | 当該REQまたはプロジェクトでは対象外と明示された状態。 |
| waived | 本来は必要だが、理由つきで免除された状態。 |
| TDD mode | テストを先に生成し、Red → Green → Refactorを証跡化するモード。 |

---

## 5. 要件定義

## 5.1 業務要件

### B-001: AI生成物の採用可否判定構造を提供する

AIが生成したコード、設計、テスト、設定ファイルなどを、そのまま採用するのではなく、要求、契約、テスト、証跡に基づいて採用可否を判定できる構造を提供する。

### B-002: 処理系非依存の品質ゲート思想を提供する

対象プロジェクトの言語やフレームワークにかかわらず、REQ、CONTRACT、TEST、EVIDENCE、GATEの共通構造を適用できること。

### B-003: qgb本体は対象プロジェクトから独立して動作する

qgb本体は、対象プロジェクトの言語とは独立したPython製CLIとして実装する。

対象プロジェクト固有の検査は、アダプタおよび設定されたコマンドを通じて実行する。

### B-004: 既存リポジトリへ最小侵襲で導入できること

既存コードへの影響を最小化し、原則として `.quality-system`、`tests/quality`、`scripts` などの追加によって導入できること。

### B-005: TDD開始時点から導入できること

既存プロジェクトへの後付けだけでなく、新規開発においてREQ、contract、失敗する初期テスト、gateを先に生成できること。

### B-006: 監査可能な証跡を残せること

REQ単位で、実行コマンド、検査結果、テスト結果、判定結果、参照した根拠を証跡として保存できること。

### B-007: ユーザー裁量を反映できること

テスト段階の必須・任意・対象外・免除を、ユーザーまたはプロジェクト方針により制御できること。

### B-008: LLMユーザーが導入可能であること

Phase 1では、PyPI公開や完全自動インストーラを必須とせず、導入マニュアルに従ってLLMユーザーがローカル実行できることを目標とする。

---

## 5.2 機能要件

### F-001: リポジトリ構成検出

対象リポジトリを読み取り、以下を推定する。

- 使用言語
- フレームワーク
- パッケージマネージャ
- テストランナー
- Lintツール
- 型検査ツール
- E2Eテストツール
- 実行コマンド候補

検出対象ファイルの例を以下に示す。

```text
package.json
pnpm-lock.yaml
yarn.lock
package-lock.json
pyproject.toml
requirements.txt
uv.lock
Pipfile
Cargo.toml
go.mod
pom.xml
build.gradle
*.csproj
*.sln
composer.json
Makefile
Dockerfile
```

### F-002: config.json生成

検出結果を `.quality-system/config.json` に保存する。

例：

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "sample-project"
  },
  "runtime": {
    "target_language": "typescript",
    "framework": "nextjs",
    "package_manager": "pnpm",
    "test_runner": "vitest",
    "e2e_runner": "playwright"
  },
  "qgb": {
    "core_language": "python",
    "version": "0.1.0"
  },
  "commands": {
    "unit_test": "pnpm vitest run",
    "e2e_test": "pnpm exec playwright test",
    "lint": "pnpm lint",
    "typecheck": "pnpm tsc --noEmit"
  }
}
```

### F-003: policy.json生成

品質ゲートの判定方針を `.quality-system/policy.json` に保存する。

例：

```json
{
  "schema_version": "1.0",
  "default_required_levels": ["L1", "L5"],
  "level_policy": {
    "L1": { "required": true },
    "L2": { "required": false, "default_if_missing": "review" },
    "L3": { "required": false, "default_if_missing": "review" },
    "L4": { "required": false, "default_if_missing": "review" },
    "L5": { "required": true },
    "L6": { "required": false, "default_if_missing": "review" }
  },
  "llm_review": {
    "enabled": false,
    "can_allow": false
  }
}
```

### F-004: REQ生成

REQ本文はMarkdownで生成する。

REQの機械可読メタデータは、JSON sidecarとして保存する。

```text
.quality-system/req/REQ-APP-001.md
.quality-system/req/REQ-APP-001.meta.json
```

REQ本文には以下を含める。

- 目的
- 成立条件
- 非目標
- 入力
- 出力または状態
- 境界条件
- 契約
- 対応テスト
- 採用条件

### F-005: contract.json生成

対象システムの種類に応じて、契約ファイルを生成する。

契約種別は以下を想定する。

- Web UI契約
- HTTP API契約
- CLI契約
- バッチ処理契約
- ファイル入出力契約
- DB状態契約
- ログ契約
- 文書契約

### F-006: テスト階層生成

以下のテスト階層を生成できること。

```text
L1_behavior
L2_state
L3_boundary
L4_flow
L5_contract
L6_experience
```

Phase 1では、L1およびL5を中心とする。

### F-007: テスト段階ポリシー制御

各検査段階は、以下の状態を持てること。

| 状態 | 意味 | 判定への影響 |
|---|---|---|
| required | 必須 | 未設定または失敗でDENY/REVIEW |
| optional | 任意 | 失敗時の扱いはpolicyに従う |
| not_configured | 未設定 | 原則REVIEW |
| out_of_scope | 対象外 | 理由があれば判定対象外 |
| waived | 理由つき免除 | 証跡必須、判定対象外またはREVIEW |

ユーザーが明示的に対象外または免除を指定した場合、その判断を証跡に残す。

### F-008: 品質ゲートランナー生成

Phase 1では、Python製qgb CLIが品質ゲートを実行する。

必要に応じて対象プロジェクト側にPowerShellラッパーを生成する。

例：

```powershell
python -m qgb run REQ-APP-001
```

または、ラッパー経由で以下を実行する。

```powershell
.\scripts\quality-gate.ps1 REQ-APP-001
```

### F-009: 契約検証

contract.jsonを読み取り、機械的に検査する。

Phase 1の検査対象は以下とする。

- ファイル存在
- 文字列包含
- JSON構文
- JSON Schema検証
- コマンド終了コード
- 標準出力形式
- 生成ファイル存在

### F-010: 証跡出力

品質ゲート実行時、以下を保存する。

```text
.quality-system/evidence/<REQ-ID>/latest/
  gate.json
  summary.md
  command.log
```

拡張時には以下を追加できる。

```text
junit.xml
screenshots/
coverage/
trace/
raw/
llm-review.md
```

### F-011: gate.json生成

品質ゲートの判定結果を `gate.json` に保存する。

必須項目は以下とする。

- schema_version
- req_id
- mode
- phase
- status
- generated_at
- runtime
- checks
- evidence_dir
- decision
- basis

例：

```json
{
  "schema_version": "1.0",
  "req_id": "REQ-APP-001",
  "mode": "retrofit",
  "phase": "verify",
  "status": "ALLOW",
  "generated_at": "2026-05-15T00:00:00+09:00",
  "checks": [
    {
      "name": "contract",
      "level": "L5",
      "status": "passed",
      "command": "python -m qgb verify-contract REQ-APP-001",
      "exit_code": 0
    }
  ],
  "evidence_dir": ".quality-system/evidence/REQ-APP-001/latest",
  "decision": {
    "result": "ALLOW",
    "meaning": "Defined checks passed. This is not proof of total correctness."
  },
  "basis": [
    "REQ-APP-001",
    "CONTRACT-REQ-APP-001",
    "POLICY-DEFAULT"
  ]
}
```

### F-012: summary.md生成

人間が読みやすい判定要約を生成する。

内容には以下を含める。

- REQ ID
- 判定結果
- 実行日時
- 実行モード
- 通過した検査
- 失敗した検査
- REVIEW理由
- 対象外・免除判断
- 次に確認すべき点

### F-013: Project Knowledge Base

対象プロジェクトの前提情報を保持する。

保持対象は以下とする。

- ユーザー明示情報
- リポジトリから抽出した情報
- 外部調査で得た情報
- 推定情報
- 免除・対象外判断
- 未確認事項

保存形式はPhase 1では以下を想定する。

```text
.quality-system/knowledge/
  knowledge.jsonl
  source-index.json
  project-context.md
```

各情報には以下を持たせる。

- id
- kind
- title
- contentまたはsummary
- source
- source_type
- confidence
- priority
- applies_to
- created_at
- retrieved_at
- review_after

### F-014: 外部調査情報の保持

ユーザーが検索や外部調査を指示した場合、得られた情報はProject Knowledge Baseに保持できること。

外部情報は、出典、取得日、適用バージョン、確度を明示する。

古くなり得る情報には `review_after` を設定できること。

### F-015: LLMレビュー補助

LLMレビューは任意機能とする。

LLMレビューは以下に利用できる。

- 要求の曖昧性指摘
- テスト不足候補の抽出
- UX・文言の違和感検出
- 境界条件候補の提示

ただし、LLMレビュー単独でALLOWを出してはならない。

### F-016: TDD mode

TDD modeでは、以下を生成する。

- REQ
- contract.json
- 失敗する初期テスト
- gate設定
- Red段階の証跡
- Green段階の証跡

TDD modeでは、初期のDENYは期待される状態として扱える。

例：

```json
{
  "req_id": "REQ-APP-001",
  "mode": "tdd",
  "phase": "red",
  "status": "DENY",
  "decision": {
    "result": "DENY",
    "meaning": "The required test fails as expected before implementation."
  }
}
```

### F-017: JSON Patchまたは専用CLIによる編集

Phase 1では、JSONファイルの直接編集を許容するが、編集後のvalidateを必須とする。

将来的には、LLMによる全文書き換えではなく、JSON Patchまたは専用CLIによる変更を推奨する。

想定コマンド例：

```powershell
python -m qgb validate
python -m qgb patch policy patch.json
python -m qgb set-required-levels REQ-APP-001 L1 L5
python -m qgb add-waiver REQ-APP-001 L6 --reason "Internal CLI tool"
```

### F-018: 導入マニュアル生成・整備

Phase 1では、導入マニュアルを成果物に含める。

導入マニュアルには以下を含める。

- 前提環境
- Pythonの確認方法
- 仮想環境の作成方法
- 依存ライブラリのインストール方法
- qgbの実行方法
- 初期化方法
- サンプルREQ生成方法
- quality-gate実行方法
- gate.jsonとsummary.mdの読み方
- Windows PowerShellでの実行例
- トラブルシューティング
- 依存ライブラリ確認手順

---

## 5.3 非機能要件

### NF-001: 再現性

同一リポジトリ、同一REQ、同一契約、同一テスト、同一policyに対して、可能な限り再現性のある判定を行う。

### NF-002: 監査性

判定結果だけでなく、判定に使用したコマンド、終了コード、ログ、参照した根拠を保存する。

### NF-003: 最小侵襲性

既存のソースコード、テスト、CI設定を不必要に変更しない。

### NF-004: 可搬性

Windows、macOS、Linuxで利用できる構造とする。

特にPhase 1では、Windows PowerShell環境での実行手順を明記する。

### NF-005: 拡張性

新しい言語、フレームワーク、テストランナー、契約種別、証跡種別を追加できる構造とする。

### NF-006: 説明可能性

ALLOW / DENY / REVIEW の意味を、出力ファイル内に明示する。

### NF-007: 安全性

外部コンテンツやリポジトリ内の任意テキストを、無条件にシステム指示として扱わない。

### NF-008: 機密情報保護

証跡に以下が不要に含まれないよう配慮する。

- APIキー
- トークン
- パスワード
- 秘密鍵
- Cookie
- セッション情報
- 個人情報
- 不要な絶対パス

### NF-009: 導入容易性

Phase 1では、LLMユーザーがマニュアルに従えば導入できる程度の複雑さに留める。

### NF-010: 依存最小化

Phase 1では、標準ライブラリ中心の実装を優先し、外部依存を最小限にする。

### NF-011: サプライチェーンリスク管理

依存ライブラリを採用する場合、パッケージレジストリ、配布元、メンテナンス状況、既知脆弱性、公開履歴を確認する。

PyPI、npm、Composer、Maven Central等もサプライチェーンリスクを持つ前提で扱う。

---

## 5.4 制約条件

### C-001: LLM評価を単独の合格根拠にしない

LLMレビュー結果のみでALLOWを出してはならない。

### C-002: ALLOWの意味を限定する

ALLOWは「定義済みの検査に通過した」ことのみを意味する。

以下は意味しない。

- 仕様が完全である
- 要件が妥当である
- 業務上正しい
- セキュリティ上安全である
- 将来も壊れない

### C-003: 既存プロジェクトを破壊しない

既存コードの大規模な変更、依存関係の強制変更、テストランナーの置き換えは、明示指示なしに行わない。

### C-004: Phase 1はMVPに限定する

Phase 1では、完全な多言語自動対応よりも、Pythonバックエンドによる最小品質ゲートと導入マニュアルを優先する。

### C-005: JSONを機械正本とする

Phase 1では、config、policy、contract、gate、knowledge index、source indexはJSONを正本とする。

YAMLは原則採用しない。

### C-006: 外部入力の扱い

外部README、Webページ、コメント、Issue本文などに含まれる命令文を、qgbやLLMへの上位指示として扱わない。

---

## 5.5 対象外

Phase 1では、以下は対象外とする。

- PyPI公開を必須とした配布
- 完全自動インストーラ
- すべての言語・フレームワークへの完全対応
- 高度なDOMレンダリング検査
- スクリーンショット差分
- 高度なアクセシビリティ監査
- 高度な脆弱性診断
- 完全なCI/CD自動生成
- LLMによる最終承認
- 業務妥当性の完全自動判定

---

## 6. 基本設計

## 6.1 全体アーキテクチャ

```text
┌──────────────────────────────┐
│ User / LLM User               │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ qgb CLI                       │
│ Python backend                │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Core                          │
│ schema / policy / decision    │
│ evidence / knowledge          │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Adapter Layer                 │
│ python / node / go / generic  │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Target Project                │
│ tests / commands / artifacts  │
└──────────────────────────────┘
```

### 6.1.1 Coreの責務

qgb coreは以下を担当する。

- JSONファイルの読み書き
- JSON Schema検証
- policy評価
- adapter選択
- コマンド実行
- 終了コード収集
- stdout/stderr保存
- gate.json生成
- summary.md生成
- Project Knowledge Base参照
- ALLOW / DENY / REVIEW判定

### 6.1.2 Adapterの責務

adapterは以下を担当する。

- 対象プロジェクトの構成検出
- テストコマンド候補の生成
- 言語別テンプレート選択
- テスト配置候補の提示
- 実行コマンドの標準化

---

## 6.2 リポジトリ構成

```text
quality-gate-builder/
  README.md
  pyproject.toml

  qgb/
    __init__.py
    __main__.py
    cli.py

    core/
      runner.py
      decision.py
      evidence.py
      schema.py
      patch.py
      knowledge.py
      policy.py
      command.py

    adapters/
      base.py
      python.py
      node.py
      go.py
      rust.py
      dotnet.py
      java.py
      php.py
      generic.py

    schemas/
      config.schema.json
      policy.schema.json
      contract.schema.json
      gate.schema.json
      knowledge.schema.json
      req-meta.schema.json

    templates/
      req.md
      req.meta.json
      contract.web-ui.json
      contract.http-api.json
      contract.cli.json
      contract.file.json
      summary.md
      quality-gate.ps1

  docs/
    installation.md
    phase1-manual.md
    security-dependency-policy.md
    decision-semantics.md
    knowledge-base.md
    tdd-mode.md

  examples/
    python-cli-pytest/
    python-fastapi-pytest/
    node-cli-vitest/
    generic-powershell/

  skills/
    skill-creator-plus/
    generated-skill-template/

  tests/
```

---

## 6.3 CLI設計

### 6.3.1 Phase 1必須コマンド

```powershell
python -m qgb init
python -m qgb detect
python -m qgb scaffold REQ-APP-001
python -m qgb validate
python -m qgb run REQ-APP-001
```

### 6.3.2 Phase 1任意コマンド

```powershell
python -m qgb verify-contract REQ-APP-001
python -m qgb add-knowledge knowledge.json
python -m qgb add-waiver REQ-APP-001 L6 --reason "Internal CLI tool"
python -m qgb tdd-init REQ-APP-001
```

### 6.3.3 将来コマンド

```powershell
qgb init
qgb run REQ-APP-001
qgb patch policy patch.json
qgb set-required-levels REQ-APP-001 L1 L5
qgb create-skill
```

---

## 6.4 判定設計

### 6.4.1 判定値

| 判定 | 意味 | 採用可否 |
|---|---|---|
| ALLOW | 定義済み必須検査を通過した | 条件付き採用可 |
| DENY | 定義済み必須検査に失敗した | 採用不可 |
| REVIEW | 機械判定では不足 | 人間確認または追加定義が必要 |

### 6.4.2 判定フロー

```text
REQなし
  → REVIEW

contractなし
  → REVIEW

policy上必須の検査が未設定
  → REVIEW

contract検証失敗
  → DENY

必須テスト失敗
  → DENY

証跡生成失敗
  → REVIEW

対象外・免除が理由つきで定義済み
  → 判定対象から除外可能

全必須検査成功
  → ALLOW
```

### 6.4.3 out_of_scope / waivedの扱い

`out_of_scope` は、当該REQまたはプロジェクトにおいて対象外であることを意味する。

`waived` は、本来は必要だが理由つきで免除されたことを意味する。

いずれも、以下を必須とする。

- req_id
- level
- status
- reason
- decided_by
- created_at

---

## 6.5 L1〜L6設計

| レベル | 名称 | 目的 | 例 |
|---|---|---|---|
| L1 | 表層動作検査 | ユーザーから見える基本動作を確認する | HTTP 200、CLI終了コード0 |
| L2 | 状態生成検査 | DB、ファイル、セッション等の状態変化を確認する | レコード作成、ファイル出力 |
| L3 | 境界条件検査 | 異常系、空値、権限なし、重複を確認する | 400、403、バリデーションエラー |
| L4 | 流れ検査 | 複数手順の業務フローを確認する | ログイン→登録→確認 |
| L5 | 契約検査 | 機械的契約を満たすか確認する | JSON Schema、DOM属性、OpenAPI |
| L6 | 体験・非機能検査 | UX、文言、性能、監査性を確認する | 表示文言、アクセシビリティ、ログ |

Phase 1では、L1とL5を中心に扱う。

---

## 6.6 TDD mode設計

### 6.6.1 目的

TDD modeは、プロジェクト開始時点または新機能開発開始時点で、REQ、contract、失敗する初期テスト、gateを先に生成するためのモードである。

### 6.6.2 フロー

```text
1. ユーザーが目的・要求・受け入れ条件を提示する
2. qgbがREQを生成する
3. qgbがcontract.jsonを生成する
4. qgbが失敗する初期テストを生成する
5. qgb runを実行し、Red段階のDENYを証跡化する
6. ユーザーまたはLLMが実装する
7. qgb runを再実行し、Green段階のALLOWを目指す
8. 必要に応じてRefactor後の証跡を残す
```

### 6.6.3 TDD modeの判定解釈

TDD modeのRed段階では、DENYは期待される結果である。

ただし、期待される失敗であることを `phase` と `meaning` に明示する。

---

## 6.7 Project Knowledge Base設計

### 6.7.1 目的

Project Knowledge Baseは、品質ゲート生成や判定に用いる前提情報を保持する根拠ストアである。

### 6.7.2 保持する情報

| 種別 | 例 | 優先度 |
|---|---|---|
| user_instruction | ユーザーが明示した方針 | 高 |
| repository_fact | リポジトリから抽出した事実 | 高 |
| external_reference | 公式ドキュメントや外部調査情報 | 中〜高 |
| inferred_fact | qgbまたはLLMが推定した情報 | 低〜中 |
| waiver | 免除判断 | 高 |
| open_question | 未確認事項 | REVIEW要因 |

### 6.7.3 保存形式

Phase 1では、JSON Lines形式を採用する。

```json
{"id":"CTX-USER-001","kind":"user_instruction","title":"Target mode","content":"Use TDD mode for this feature.","source":"user","confidence":"explicit","priority":"high","created_at":"2026-05-15T00:00:00+09:00"}
```

### 6.7.4 外部調査情報

外部調査情報には、少なくとも以下を付与する。

- source_type
- retrieved_at
- applies_to
- confidence
- review_after

外部情報は、古くなる可能性があるため、必要に応じて再確認対象とする。

---

## 6.8 ファイル形式設計

### 6.8.1 方針

Phase 1では、以下の方針とする。

```text
JSON = 機械正本
Markdown = 人間向け文書
text/log = 実行ログ
XML = JUnit等の互換出力が必要な場合のみ
YAML = 原則使用しない
```

### 6.8.2 JSON正本

以下はJSONを正本とする。

- config.json
- policy.json
- contract.json
- gate.json
- req meta json
- source-index.json
- knowledge schema

### 6.8.3 Markdown文書

以下はMarkdownとする。

- REQ本文
- summary.md
- project-context.md
- 導入マニュアル
- LLMレビュー結果

### 6.8.4 LLMによる編集方針

Phase 1ではJSON直接編集を許容するが、編集後に必ずvalidateする。

将来的には、JSON Patchまたは専用CLIによる変更へ寄せる。

---

## 6.9 依存ライブラリ・サプライチェーン設計

### 6.9.1 基本方針

Phase 1では、外部依存を最小限にする。

可能な限りPython標準ライブラリで実装する。

外部依存を採用する場合は、セキュリティ調査を要件とする。

### 6.9.2 調査項目

ライブラリ採用時には、以下を確認する。

- 公式リポジトリ
- パッケージレジストリ上の配布元
- メンテナンス状況
- リリース履歴
- ライセンス
- 既知脆弱性
- 直近のセキュリティ報告
- 不審なメンテナ交代
- 依存ツリーの大きさ
- postinstall等の危険な仕組みの有無
- ネットワーク通信の有無
- バイナリ配布の有無

### 6.9.3 PyPIに関する方針

PyPIもサプライチェーンリスクを持つ前提で扱う。

Phase 1では、PyPIからの導入を必須にしない。

初期利用者は、リポジトリを取得し、導入マニュアルに従ってローカル実行できればよい。

### 6.9.4 依存候補

Phase 1で外部依存を使う場合の候補は最小限とする。

例：

- JSON Schema検証ライブラリ

ただし、採用前にセキュリティ確認を行い、標準ライブラリ実装で代替可能な場合は標準ライブラリを優先する。

---

## 7. Phase 1 MVP定義

## 7.1 Phase 1の目的

Phase 1では、完全な多言語品質ゲート生成基盤ではなく、Pythonバックエンドで動作する最小構成と、LLMユーザーが導入できるマニュアルを提供する。

### 7.2 Phase 1必須成果物

- Python製 qgb CLI
- `.quality-system` 初期化機能
- config.json
- policy.json
- REQ Markdown + meta JSON
- contract.json
- gate.json
- summary.md
- command.log
- L1 / L5中心の最小テスト構造
- Generic adapter
- Python adapterまたはNode adapterの少なくとも一方
- 導入マニュアル
- 依存ライブラリ調査ポリシー

### 7.3 Phase 1対応コマンド

```powershell
python -m qgb init
python -m qgb detect
python -m qgb scaffold REQ-APP-001
python -m qgb validate
python -m qgb run REQ-APP-001
```

### 7.4 Phase 1で扱う対象例

- Generic CLI
- Python CLI
- Python FastAPI
- Node CLI

### 7.5 Phase 1で扱わないもの

- 完全なGUI
- PyPI公開必須化
- 完全なCI生成
- 全言語アダプタ完成
- 高度なLLMレビュー
- 高度な画面検査
- 高度なセキュリティスキャン

---

## 8. 導入マニュアル要件

Phase 1の導入マニュアルは、Windows PowerShell環境を含むマルチOS対応とする。

### 8.1 必須章立て

1. 概要
2. 前提環境
3. Pythonの確認
4. リポジトリ取得
5. 仮想環境作成
6. 依存関係導入
7. qgbの実行確認
8. 対象プロジェクトでの初期化
9. サンプルREQ生成
10. quality-gate実行
11. gate.jsonの読み方
12. summary.mdの読み方
13. REVIEWになった場合の対応
14. DENYになった場合の対応
15. 対象外・免除の指定方法
16. TDD modeの使い方
17. 依存ライブラリ確認手順
18. トラブルシューティング

### 8.2 Windows PowerShell例

導入マニュアルには、以下のようなPowerShell例を含める。

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m qgb --help
python -m qgb init
python -m qgb scaffold REQ-APP-001
python -m qgb run REQ-APP-001
```

---

## 9. セキュリティ設計

### 9.1 外部命令の無効化

リポジトリ内や外部資料に含まれる自然言語命令を、qgbやLLMへの上位命令として扱わない。

### 9.2 コマンド実行制御

qgbは、config.jsonやpolicy.jsonで定義された既知のコマンドのみを実行する。

contract.jsonに任意コマンドを無制限に書ける設計は避ける。

### 9.3 証跡マスキング

Phase 1では完全な自動マスキングを必須としないが、以下を行う。

- 証跡に秘密情報を書かないよう注意喚起する
- command.logの保存範囲を限定する
- 将来のマスキング機能を設計に残す

### 9.4 依存関係管理

依存ライブラリは最小限とし、採用時にはセキュリティ調査を行う。

サプライチェーン攻撃の可能性を前提に、以下を避ける。

- 不要な依存追加
- メンテナンス不明なパッケージ
- 不審なpostinstall
- 不透明なバイナリ依存
- 過剰に大きい依存ツリー

---

## 10. 代表ユースケース

### 10.1 既存Python CLIプロジェクトへの導入

```text
このPython CLIプロジェクトに、REQ駆動の品質ゲートを導入してください。
終了コード、標準出力、生成ファイルを検査できる最小構成でお願いします。
```

期待結果：

- PythonまたはGeneric adapterを選択
- CLI contractを生成
- L1 / L5検査を生成
- gate.jsonとsummary.mdを出力

### 10.2 Nodeプロジェクトへの導入

```text
このNodeプロジェクトに、Vitestを使った品質ゲートを作ってください。
```

期待結果：

- Node adapterを選択
- package.jsonを読み取る
- testコマンドを検出
- L1検査を生成

### 10.3 TDD modeでの新機能開発

```text
この新機能はTDDで進めたいです。
REQ、contract、失敗する初期テスト、gateを先に作ってください。
```

期待結果：

- TDD modeでREQを作成
- contractを作成
- 失敗する初期テストを生成
- Red段階のDENYを証跡化

### 10.4 ユーザー裁量による免除

```text
このREQは内部バッチなのでL6体験検査は対象外にしてください。
理由も証跡に残してください。
```

期待結果：

- policyまたはwaiverにout_of_scopeを記録
- gate.jsonに対象外理由を記録
- L6未設定をREVIEWにしない

---

## 11. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| LLM評価への依存 | 主観評価を合格根拠にしてしまう | LLM単独ALLOW禁止 |
| ALLOW過信 | 完全な正しさと誤解される | decision.meaningに明記 |
| 未設定検査の見落とし | SKIPが合格扱いされる | 原則REVIEW、対象外・免除は理由必須 |
| JSON編集ミス | LLMがJSONを壊す | validate必須、将来JSON Patch化 |
| 依存ライブラリリスク | PyPI等経由のサプライチェーン攻撃 | 依存最小化、採用前調査 |
| 証跡への機密混入 | ログに秘密情報が残る | 保存範囲制御、将来マスキング |
| 導入が重い | ユーザーが使わない | Phase 1はPython CLI + マニュアルに限定 |
| 多言語対応の複雑化 | adapterが肥大化する | Coreとadapterを分離 |
| 外部情報の劣化 | 古い仕様を根拠にする | retrieved_at / review_afterを保持 |

---

## 12. 受け入れ条件

Phase 1は、以下を満たした場合に受け入れ可能とする。

1. Pythonでqgb CLIを起動できる。
2. `python -m qgb init` で `.quality-system` を生成できる。
3. config.json、policy.json、REQ、contract.jsonを生成できる。
4. `python -m qgb validate` でJSON正本を検証できる。
5. `python -m qgb run REQ-APP-001` でgateを実行できる。
6. gate.json、summary.md、command.logを出力できる。
7. 検査成功時にALLOWを出せる。
8. 検査失敗時にDENYを出せる。
9. 未設定または不足時にREVIEWを出せる。
10. out_of_scopeまたはwaivedを理由つきで記録できる。
11. TDD modeでRed段階のDENYを期待結果として証跡化できる。
12. Project Knowledge Baseにユーザー明示情報を保存できる。
13. 導入マニュアルが存在する。
14. 依存ライブラリ採用方針とセキュリティ確認手順が文書化されている。
15. LLMレビュー単独でALLOWを出さない方針が明示されている。

---

## 13. 開発フェーズ

### Phase 1: Python CLI MVP + 導入マニュアル

- Python製qgb CLI
- JSON正本
- validate
- init
- scaffold
- run
- Generic adapter
- 最小Python/Node adapter
- 導入マニュアル
- 依存関係セキュリティ方針

### Phase 2: 編集安全化

- JSON Patch対応
- 専用CLIによるpolicy編集
- waiver追加コマンド
- knowledge追加コマンド
- schema強化

### Phase 3: adapter拡張

- Go adapter
- Rust adapter
- .NET adapter
- Java adapter
- PHP adapter

### Phase 4: CI連携

- GitHub Actions例
- GitLab CI例
- JUnit XML出力
- PRコメント用summary

### Phase 5: Skill Creator化

- 対象プロジェクト専用スキル生成
- skill-creator-plus
- 主要言語ごとの生成例パック
- LLM向け運用ガイド

---

## 14. 結論

quality-gate-builderは、LLMの生成能力を活用しつつ、その評価の揺らぎを外部化された構造で抑えるための品質ゲート生成基盤である。

本システムの中核は、以下の分離にある。

```text
要求
契約
テスト
証跡
判定
根拠情報
```

Phase 1では、対象プロジェクトの言語に依存しないPython製CLIとして最小実装し、JSONを機械正本、Markdownを人間向け文書として扱う。

また、依存ライブラリ自体もサプライチェーンリスクを持つ前提で、標準ライブラリ中心・依存最小化・採用前調査を基本方針とする。

最も重要な原則は以下である。

```text
LLMは候補生成と補助レビューには使える。
しかし、LLMの主観評価だけでALLOWを出してはならない。
ALLOWは、定義済みの契約と検査に通過したことのみを意味する。
未設定や判断不足はREVIEWとする。
ただし、ユーザーが明示的に対象外または免除を定義した場合は、その理由を証跡に残したうえで判定へ反映できる。
```

この原則により、AI生成物を無批判に採用するのではなく、採用可能性を検査・説明・改善できる開発系を構築する。

