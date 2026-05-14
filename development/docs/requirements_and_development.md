# 多言語対応・証跡駆動品質ゲート生成スキルセット 要件定義書・基本設計書

## 1. 文書概要

### 1.1 文書名

多言語対応・証跡駆動品質ゲート生成スキルセット 要件定義書・基本設計書

### 1.2 目的

本書は、任意のソフトウェアリポジトリに対して、処理系・フレームワーク・テストランナーを判定し、要求・契約・テスト・証跡・判定ゲートからなる品質確認系を生成するためのスキルセットについて、要件および基本設計を定義する。

本スキルセットは、LLMによる主観的評価を最終的な品質保証の根拠とせず、要求、機械的検査、自動テスト、証跡、明示された採否判定を組み合わせることで、AI生成物を採用可能な状態へ近づけるための構造を提供する。

### 1.3 対象読者

- 本スキルセットを設計・実装する開発者
- AI支援開発環境を構築する技術者
- 開発プロセスに品質ゲートを導入する管理者
- 要求定義、設計、テスト、レビュー、監査に関与する担当者

### 1.4 本書の位置づけ

本書は、以下を対象とする。

- スキルセット全体の要件定義
- スキルセットの基本設計
- 生成される品質ゲート系の基本構造
- 言語別アダプタの設計方針
- 証跡・判定・レビュー方針

詳細設計、個別言語ごとの実装仕様、各テンプレートの完全版は、本書の後続文書として別途定義する。

---

## 2. 背景と課題

### 2.1 背景

LLMを用いた開発支援では、コード生成、テスト生成、レビュー、設計補助などが高速に実行できる。一方で、LLMの出力は確率的であり、同一指示であっても出力や評価が揺れる。

また、LLMによる評価は、以下のような制約を持つ。

- 評価結果が毎回安定するとは限らない
- 評価値の分布が正規分布に従う保証がない
- 複数回評価して中央値を取っても、偏りが消える保証がない
- モデル更新、プロンプト、文脈、安全制約によって評価軸が変動し得る
- 学習データ由来の偏りや盲点を外部から観測しにくい
- AIが生成し、AIが評価し、AIが修正する閉じた循環では、誤りが自己強化される危険がある

そのため、AI生成物をそのまま成果物として採用するのではなく、採用可否を判定するための外部化された構造が必要となる。

### 2.2 解決すべき課題

本スキルセットが解決する主な課題は以下である。

1. AI生成物の採用可否を、LLMの主観評価だけに依存せず判定したい。
2. 要求、契約、テスト、証跡、判定をリポジトリ内に明示的に配置したい。
3. PHP以外の処理系に対しても、同様の品質ゲート系を短時間で構築したい。
4. プロジェクトごとに異なる言語、フレームワーク、テストランナーへ柔軟に対応したい。
5. 生成された品質ゲートの意味を、後から監査・説明できる状態にしたい。
6. ALLOW / DENY / REVIEW の判定意味を、処理系をまたいで共通化したい。
7. 抽象論だけでなく、主要言語ごとの実装例を保持し、生成品質を安定させたい。

---

## 3. システム概要

### 3.1 システム名

仮称：多言語対応・証跡駆動品質ゲート生成スキルセット

英名案：Polyglot Evidence Gate Skillset

### 3.2 システムの基本方針

本スキルセットは、以下の方針で設計する。

1. LLM評価を最終的な合格根拠にしない。
2. 要求をREQとして明文化する。
3. 機械的に検査できる契約を定義する。
4. 処理系標準のテストランナーへ接続する。
5. 検査結果を証跡として保存する。
6. 判定は ALLOW / DENY / REVIEW の3値で表現する。
7. ALLOWは「定義済み検査に通過した」ことを意味し、「完全な正しさ」を意味しない。
8. 言語・フレームワークごとの差分はアダプタとして分離する。
9. 共通仕様、言語別アダプタ、具体例パックを分離して保守する。
10. 初回導入は最小構成とし、必要に応じてL2〜L6の検査を拡張する。

### 3.3 スキルセットの構成

本スキルセットは、以下の4要素で構成する。

```text
quality-gate-skillset/
  skill-creator-plus/
    汎用スキルクリエイター

  core-spec/
    共通仕様

  adapters/
    言語別アダプタ

  examples/
    主要言語・主要構成ごとの生成例
```

### 3.4 生成される品質ゲート系の概要

対象リポジトリには、原則として以下の構造を生成する。

```text
project-root/
  .quality-system/
    config.json
    req/
      REQ-APP-001.md
    contracts/
      REQ-APP-001/
        contract.json
    evidence/
      REQ-APP-001/
        latest/
          gate.json
          summary.md
          command.log
          junit.xml

  tests/
    quality/
      L1_behavior/
      L2_state/
      L3_boundary/
      L4_flow/
      L5_contract/
      L6_experience/

  scripts/
    quality-gate.*
    verify-contracts.*
```

実際の拡張子、スクリプト言語、テスト配置は、対象リポジトリの処理系に合わせて調整する。

---

## 4. 用語定義

| 用語 | 意味 |
|---|---|
| REQ | Requirement。成立すべき要求を記述した正本。 |
| CONTRACT | 機械的に検査可能な契約。UI、API、CLI、ファイル、DB状態などを対象とする。 |
| TEST | 要求や契約を検証する自動テスト。 |
| EVIDENCE | 実行結果、ログ、JUnit XML、スクリーンショット、判定結果などの証跡。 |
| GATE | REQ単位で検査を実行し、ALLOW / DENY / REVIEW を返す判定機構。 |
| ADAPTER | 言語、フレームワーク、テストランナーごとの差分を吸収する接続層。 |
| ALLOW | 定義済みの契約・検査・テストに通過した状態。完全な正しさは保証しない。 |
| DENY | 定義済みの検査に失敗した状態。採用不可。 |
| REVIEW | 機械的検査だけでは採否を決められず、人間確認が必要な状態。 |
| L1〜L6 | 品質確認を階層化した検査レベル。 |

---

## 5. 要件定義

## 5.1 業務要件

### B-001: AI生成物の採用可否判定構造を提供する

AIが生成したコード、設計、テスト、設定ファイルなどを、そのまま採用するのではなく、要求、契約、テスト、証跡に基づいて採用可否を判定できる構造を提供する。

### B-002: 処理系非依存の品質ゲート思想を提供する

PHP、Python、TypeScript、Go、Rust、.NET、Javaなど、複数の処理系に対して共通の品質ゲート思想を適用できること。

### B-003: 既存リポジトリへ最小侵襲で導入できること

既存コードへの影響を最小化し、原則として新規ディレクトリおよび新規スクリプトの追加によって導入できること。

### B-004: 監査可能な証跡を残せること

REQ単位で、実行コマンド、検査結果、テスト結果、判定結果を証跡として保存し、後から確認できること。

### B-005: 実務導入時に段階的拡張が可能であること

初回はL1およびL5を中心とした最小構成で導入し、必要に応じてL2〜L6を追加できること。

---

## 5.2 機能要件

### F-001: 対象リポジトリの構成検出

対象リポジトリを読み取り、以下の情報を推定する。

- 使用言語
- フレームワーク
- パッケージマネージャ
- テストランナー
- Lintツール
- 型検査ツール
- E2Eテストツール
- CI構成
- 実行環境

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

### F-002: ランタイム定義ファイルの生成

検出結果を `.quality-system/config.json` に保存する。

例：

```json
{
  "language": "typescript",
  "framework": "nextjs",
  "package_manager": "pnpm",
  "test_runner": "vitest",
  "e2e_runner": "playwright",
  "commands": {
    "install": "pnpm install",
    "unit_test": "pnpm vitest run",
    "e2e_test": "pnpm exec playwright test",
    "lint": "pnpm lint",
    "typecheck": "pnpm tsc --noEmit"
  }
}
```

### F-003: REQテンプレート生成

REQファイルを生成できること。

REQには以下を含める。

- REQ ID
- 要求名
- 目的
- 成立条件
- 非目標
- 入力
- 出力または状態
- 境界条件
- 契約ファイル
- 対応テスト
- 採用条件

### F-004: 契約ファイル生成

対象システムの種類に応じて、契約ファイルを生成できること。

契約種別は以下を想定する。

- Web UI契約
- HTTP API契約
- CLI契約
- バッチ処理契約
- ファイル入出力契約
- DB状態契約
- ログ契約

### F-005: テスト階層ディレクトリ生成

以下のテスト階層を生成できること。

```text
L1_behavior
L2_state
L3_boundary
L4_flow
L5_contract
L6_experience
```

初期導入時は、原則としてL1およびL5を優先して生成する。

### F-006: 品質ゲートランナー生成

対象リポジトリの処理系に合わせて、品質ゲートランナーを生成する。

例：

- Python: `scripts/quality-gate.py`
- Node / TypeScript: `scripts/quality-gate.mjs`
- Go: `scripts/quality-gate.go` または `scripts/quality-gate.sh`
- Rust: `xtask` または `scripts/quality-gate.sh`
- .NET: `scripts/quality-gate.ps1`
- Java: `scripts/quality-gate.sh` または `scripts/quality-gate.ps1`

Windows環境を考慮し、PowerShell版を優先生成できること。

### F-007: 契約検証スクリプト生成

契約ファイルを読み取り、機械的に検査するスクリプトを生成する。

初期MVPでは、以下を検査対象とする。

- ファイル存在
- 文字列包含
- JSON Schema検証
- HTTPステータス
- コマンド終了コード
- 標準出力形式
- 生成ファイル存在

### F-008: 証跡出力

品質ゲート実行時、以下を証跡として保存する。

```text
.quality-system/evidence/<REQ-ID>/latest/
  gate.json
  summary.md
  command.log
  junit.xml
```

必要に応じて、以下を追加できる。

```text
screenshots/
coverage/
trace/
raw/
```

### F-009: gate.json生成

品質ゲートの判定結果を `gate.json` に保存する。

必須項目は以下とする。

- req_id
- status
- generated_at
- runtime
- checks
- evidence_dir
- decision

### F-010: summary.md生成

人間が読みやすい判定要約を `summary.md` に保存する。

内容には以下を含める。

- REQ ID
- 判定結果
- 実行日時
- 通過した検査
- 失敗した検査
- REVIEW理由
- 次に確認すべき点

### F-011: 言語別アダプタ選択

検出した処理系に基づき、適切なアダプタを選択する。

初期対応対象は以下とする。

- Python
- TypeScript / Node.js
- Go
- Rust
- .NET
- Java
- PHP
- Generic

### F-012: 具体例パック参照

スキルクリエイターは、対象リポジトリに近い具体例を参照し、生成品質を安定させる。

例：

- Python FastAPI + pytest
- Python CLI + pytest
- Next.js + Vitest + Playwright
- Node CLI + Vitest
- Go HTTP API + go test
- Rust CLI + cargo test
- .NET Web API + dotnet test
- Java Spring Boot + JUnit

### F-013: REVIEW判定の生成

機械的検査では採否を決められない場合、ALLOWではなくREVIEWを返す。

REVIEW条件の例：

- REQは存在するが、対応契約がない
- 契約は存在するが、検査器が未対応
- テストが未定義
- LLMレビューで重大な不確実性が検出された
- 既存プロジェクトの実行方法が不明
- テスト実行は成功したが、証跡生成に失敗した

### F-014: LLMレビュー補助

任意でLLMレビューを追加できる。

ただし、LLMレビュー単独でALLOWを出してはならない。

LLMレビューは以下に限定する。

- REVIEW発生の補助
- レビュー観点の抽出
- テスト不足候補の提示
- REQ曖昧性の指摘
- UX、文言、説明品質の補助確認

### F-015: CI連携用コマンド出力

GitHub Actions、GitLab CI、Azure Pipelines等へ連携するため、品質ゲート実行コマンドを出力できること。

初期対応はコマンド例の提示までとし、CIファイル自動生成は拡張要件とする。

---

## 5.3 非機能要件

### NF-001: 再現性

同一リポジトリ、同一REQ、同一契約、同一テストに対して、可能な限り再現性のある判定を行う。

### NF-002: 監査性

判定結果だけでなく、判定に使用したコマンド、終了コード、ログ、テスト結果を保存する。

### NF-003: 最小侵襲性

既存のソースコード、テスト、CI設定を不必要に変更しない。

### NF-004: 可搬性

Windows、macOS、Linuxで利用できる構造とする。

特にWindows + PowerShell環境に配慮し、PowerShell版スクリプトの生成を可能とする。

### NF-005: 拡張性

新しい言語、フレームワーク、テストランナー、契約種別を追加できる構造とする。

### NF-006: 説明可能性

ALLOW / DENY / REVIEW の意味を、出力ファイル内に明示する。

### NF-007: 安全性

外部コンテンツやリポジトリ内の任意テキストを、無条件にシステム指示として扱わない。

### NF-008: 機密情報保護

証跡に環境変数、認証情報、トークン、秘密鍵、内部パスなどが不要に含まれないよう配慮する。

初期版では、完全な自動マスキングまでは必須とせず、証跡ポリシーとして明示する。

### NF-009: 導入容易性

最小構成では、1つのREQ、1つの契約、1つのテスト、1つのゲートコマンドで動作確認できること。

### NF-010: 保守性

共通仕様、言語別アダプタ、具体例を分離し、個別変更が全体へ過剰に影響しないこと。

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

### C-004: 生成系は最小構成を優先する

初回導入では、完全な検査網羅よりも、動作する最小品質ゲートの構築を優先する。

### C-005: 外部入力の扱い

外部README、Webページ、コメント、Issue本文などに含まれる命令文を、スキルの上位指示として扱わない。

---

## 5.5 対象外

初期リリースでは、以下は対象外とする。

- 完全な自動要件定義
- 業務妥当性の完全自動判定
- セキュリティ監査の完全自動化
- 全言語・全フレームワークへの網羅対応
- 既存CI/CDの完全自動再設計
- 本番デプロイ判定の自動化
- LLMによる最終承認
- 高度な画面差分検査
- 高度なアクセシビリティ監査
- 高度な脆弱性診断

---

## 6. 基本設計

## 6.1 全体アーキテクチャ

本スキルセットは、以下の4層構成とする。

```text
┌────────────────────────────────────┐
│  skill-creator-plus                 │
│  汎用スキルクリエイター              │
└────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│  core-spec                          │
│  共通仕様                            │
│  REQ / CONTRACT / EVIDENCE / GATE   │
└────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│  adapters                           │
│  言語別・処理系別アダプタ             │
└────────────────────────────────────┘
                 │
                 ▼
┌────────────────────────────────────┐
│  examples                           │
│  主要構成ごとの生成例                 │
└────────────────────────────────────┘
```

対象リポジトリに対しては、以下の流れで品質ゲート系を生成する。

```text
ユーザー指示
  ↓
対象リポジトリ調査
  ↓
処理系・テストランナー推定
  ↓
アダプタ選択
  ↓
近い具体例を選択
  ↓
.quality-system 生成
  ↓
REQ / CONTRACT / TEST / GATE生成
  ↓
初回実行コマンド提示
```

---

## 6.2 スキルセット内ディレクトリ設計

```text
polyglot-evidence-gate-skillset/
  README.md

  skill-creator-plus/
    SKILL.md
    prompts/
      repository-inspection.md
      adapter-selection.md
      generation-workflow.md
      safety-policy.md

  core-spec/
    SKILL.md
    docs/
      req-spec.md
      contract-spec.md
      evidence-spec.md
      gate-spec.md
      decision-semantics.md
      llm-review-policy.md
      evidence-policy.md
      security-policy.md
    schemas/
      contract.schema.json
      gate.schema.json
      config.schema.json

  adapters/
    python/
      adapter.md
      templates/
        quality-gate.py
        verify-contracts.py
        pytest-sample.py
    node-typescript/
      adapter.md
      templates/
        quality-gate.mjs
        verify-contracts.mjs
        vitest-sample.test.ts
        playwright-sample.spec.ts
    go/
      adapter.md
      templates/
        quality-gate.go
        quality-gate.ps1
        sample_quality_test.go
    rust/
      adapter.md
      templates/
        quality-gate.ps1
        sample_quality_test.rs
    dotnet/
      adapter.md
      templates/
        quality-gate.ps1
        SampleQualityTests.cs
    java/
      adapter.md
      templates/
        quality-gate.ps1
        SampleQualityTest.java
    php/
      adapter.md
      templates/
        quality-gate.php
        quality-gate.ps1
    generic/
      adapter.md
      templates/
        quality-gate.ps1
        quality-gate.sh

  examples/
    python-fastapi-pytest/
    python-cli-pytest/
    nextjs-vitest-playwright/
    node-cli-vitest/
    go-http-api/
    rust-cli/
    dotnet-webapi/
    java-spring-boot/
```

---

## 6.3 生成対象リポジトリ内ディレクトリ設計

初期生成では、以下を基本構造とする。

```text
project-root/
  .quality-system/
    config.json
    req/
      REQ-APP-001.md
    contracts/
      REQ-APP-001/
        contract.json
    evidence/
      REQ-APP-001/
        latest/
          gate.json
          summary.md
          command.log

  tests/
    quality/
      L1_behavior/
        REQ-APP-001/
      L5_contract/
        REQ-APP-001/

  scripts/
    quality-gate.*
    verify-contracts.*
```

対象リポジトリの慣習に合わせ、`tests/quality` の配置は変更可能とする。

例：

- Python: `tests/quality/`
- Node: `tests/quality/` または `__tests__/quality/`
- Go: `quality/` または `tests/quality/`
- Rust: `tests/quality/`
- .NET: `tests/Quality/`
- Java: `src/test/java/.../quality/`

---

## 6.4 処理フロー設計

### 6.4.1 初回構築フロー

```text
1. ユーザーが対象リポジトリへの品質ゲート構築を指示する
2. スキルクリエイターがリポジトリ構造を調査する
3. 処理系、フレームワーク、テストランナーを推定する
4. 推定結果を表示または config.json に保存する
5. 適切なアダプタを選択する
6. 近い具体例を選択する
7. .quality-system を生成する
8. サンプルREQを生成する
9. サンプル契約を生成する
10. 最小テストを生成する
11. 品質ゲートランナーを生成する
12. 実行コマンドを提示する
```

### 6.4.2 品質ゲート実行フロー

```text
1. quality-gate に REQ ID を渡す
2. REQファイルの存在を確認する
3. 契約ファイルの存在を確認する
4. 契約検証を実行する
5. 対応するL1〜L6テストを探索する
6. 存在するテストを実行する
7. 結果を収集する
8. gate.json を生成する
9. summary.md を生成する
10. ALLOW / DENY / REVIEW を返す
```

### 6.4.3 判定フロー

```text
契約ファイルなし
  → REVIEW

契約検証失敗
  → DENY

必須テストなし
  → REVIEW

テスト失敗
  → DENY

証跡生成失敗
  → REVIEW

全必須検査成功
  → ALLOW
```

---

## 6.5 判定設計

### 6.5.1 判定値

| 判定 | 意味 | 採用可否 |
|---|---|---|
| ALLOW | 定義済み検査を通過した | 条件付き採用可 |
| DENY | 定義済み検査に失敗した | 採用不可 |
| REVIEW | 機械判定では不足 | 人間確認が必要 |

### 6.5.2 ALLOWの意味

ALLOWは以下を意味する。

```text
このREQに対して定義されている契約、検査、テストは通過した。
```

ALLOWは以下を意味しない。

```text
この成果物は完全に正しい。
このREQは完全である。
この仕様は業務上妥当である。
この実装はセキュリティ上安全である。
この実装は将来も保守可能である。
```

### 6.5.3 REVIEWの重要性

REVIEWは失敗ではなく、採否に必要な情報が不足している状態である。

REVIEWを積極的に使うことで、AI生成物を不当にALLOWすることを防ぐ。

---

## 6.6 L1〜L6設計

| レベル | 名称 | 目的 | 例 |
|---|---|---|---|
| L1 | 表層動作検査 | ユーザーから見える基本動作を確認する | HTTP 200、CLI終了コード0、画面表示 |
| L2 | 状態生成検査 | DB、ファイル、セッション等の状態変化を確認する | レコード作成、ファイル出力 |
| L3 | 境界条件検査 | 異常系、空値、権限なし、重複を確認する | 400/403、バリデーションエラー |
| L4 | 流れ検査 | 複数手順の業務フローを確認する | ログイン→登録→確認 |
| L5 | 契約検査 | 機械的契約を満たすか確認する | JSON Schema、DOM属性、OpenAPI |
| L6 | 体験・非機能検査 | UX、文言、性能、監査性を確認する | 表示文言、アクセシビリティ、ログ |

初期導入時の必須候補はL1およびL5とする。

---

## 6.7 共通ファイル仕様

## 6.7.1 config.json

対象リポジトリの処理系情報を保持する。

例：

```json
{
  "schema_version": "1.0",
  "project": {
    "name": "sample-project"
  },
  "runtime": {
    "language": "python",
    "framework": "fastapi",
    "package_manager": "uv",
    "test_runner": "pytest"
  },
  "commands": {
    "unit_test": "uv run pytest",
    "lint": "uv run ruff check .",
    "typecheck": "uv run mypy ."
  },
  "quality_gate": {
    "default_required_levels": ["L1", "L5"],
    "allow_requires_evidence": true,
    "llm_review_can_allow": false
  }
}
```

## 6.7.2 REQファイル

REQファイルのテンプレートは以下とする。

```md
# REQ-APP-001: 要求名

## 目的

この要求が満たすべき目的を記述する。

## 成立条件

- 条件1
- 条件2
- 条件3

## 非目標

- 今回扱わないこと

## 入力

- 入力条件

## 出力・状態

- 期待される出力または状態

## 境界条件

- 異常系、空入力、権限なし、タイムアウトなど

## 契約

- `.quality-system/contracts/REQ-APP-001/contract.json`

## 対応テスト

- L1:
- L2:
- L3:
- L4:
- L5:
- L6:

## 採用条件

このREQは、対応する契約検証および指定テストが通過した場合にALLOWとする。
ただし、未定義の仕様判断が発生した場合はREVIEWとする。
```

## 6.7.3 contract.json

契約ファイルは、対象種別に応じて構造を変える。

### Web UI契約例

```json
{
  "schema_version": "1.0",
  "type": "web-ui",
  "req_id": "REQ-APP-001",
  "routes": [
    {
      "path": "/",
      "method": "GET",
      "expected_status": 200,
      "must_contain_selectors": [
        "[data-page-id=\"home\"]",
        "[data-slot=\"main\"]"
      ]
    }
  ]
}
```

### HTTP API契約例

```json
{
  "schema_version": "1.0",
  "type": "http-api",
  "req_id": "REQ-API-001",
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/items",
      "expected_status": 201,
      "request_schema": "schemas/create_item.request.json",
      "response_schema": "schemas/create_item.response.json"
    }
  ]
}
```

### CLI契約例

```json
{
  "schema_version": "1.0",
  "type": "cli",
  "req_id": "REQ-CLI-001",
  "commands": [
    {
      "command": "tool export --format json",
      "expected_exit_code": 0,
      "stdout_must_be_json": true,
      "stdout_schema": "schemas/export.response.json"
    }
  ]
}
```

## 6.7.4 gate.json

品質ゲート実行結果を保存する。

例：

```json
{
  "schema_version": "1.0",
  "req_id": "REQ-APP-001",
  "status": "ALLOW",
  "generated_at": "2026-05-14T00:00:00+09:00",
  "runtime": {
    "language": "typescript",
    "framework": "nextjs",
    "test_runner": "vitest"
  },
  "checks": [
    {
      "name": "contract",
      "level": "L5",
      "status": "passed",
      "command": "node scripts/verify-contracts.mjs REQ-APP-001",
      "exit_code": 0
    },
    {
      "name": "behavior",
      "level": "L1",
      "status": "passed",
      "command": "pnpm vitest run tests/quality/L1_behavior/REQ-APP-001",
      "exit_code": 0
    }
  ],
  "evidence_dir": ".quality-system/evidence/REQ-APP-001/latest",
  "decision": {
    "result": "ALLOW",
    "meaning": "Defined checks passed. This is not proof of total correctness."
  }
}
```

---

## 6.8 言語別アダプタ設計

## 6.8.1 Pythonアダプタ

### 検出ファイル

```text
pyproject.toml
requirements.txt
uv.lock
Pipfile
pytest.ini
```

### 想定ツール

```text
pytest
ruff
mypy
coverage
```

### 生成物

```text
scripts/quality-gate.py
scripts/verify-contracts.py
tests/quality/
```

### 実行例

```powershell
python scripts/quality-gate.py REQ-APP-001
```

---

## 6.8.2 TypeScript / Node.jsアダプタ

### 検出ファイル

```text
package.json
tsconfig.json
vite.config.*
next.config.*
pnpm-lock.yaml
yarn.lock
package-lock.json
```

### 想定ツール

```text
vitest
jest
playwright
eslint
tsc
```

### 生成物

```text
scripts/quality-gate.mjs
scripts/verify-contracts.mjs
tests/quality/
```

### 実行例

```powershell
node scripts/quality-gate.mjs REQ-APP-001
```

---

## 6.8.3 Goアダプタ

### 検出ファイル

```text
go.mod
```

### 想定ツール

```text
go test
go vet
staticcheck
```

### 生成物

```text
scripts/quality-gate.ps1
quality/
```

### 実行例

```powershell
.\scripts\quality-gate.ps1 REQ-APP-001
```

---

## 6.8.4 Rustアダプタ

### 検出ファイル

```text
Cargo.toml
```

### 想定ツール

```text
cargo test
cargo clippy
cargo fmt --check
```

### 生成物

```text
scripts/quality-gate.ps1
tests/quality/
```

### 実行例

```powershell
.\scripts\quality-gate.ps1 REQ-CLI-001
```

---

## 6.8.5 .NETアダプタ

### 検出ファイル

```text
*.csproj
*.sln
```

### 想定ツール

```text
dotnet test
dotnet format
xUnit
NUnit
MSTest
```

### 生成物

```text
scripts/quality-gate.ps1
tests/Quality/
```

### 実行例

```powershell
.\scripts\quality-gate.ps1 REQ-API-001
```

---

## 6.8.6 Javaアダプタ

### 検出ファイル

```text
pom.xml
build.gradle
settings.gradle
```

### 想定ツール

```text
Maven
Gradle
JUnit
Checkstyle
SpotBugs
```

### 生成物

```text
scripts/quality-gate.ps1
src/test/java/.../quality/
```

### 実行例

```powershell
.\scripts\quality-gate.ps1 REQ-API-001
```

---

## 6.8.7 Genericアダプタ

処理系が特定できない場合、Genericアダプタを使用する。

### 生成物

```text
scripts/quality-gate.ps1
scripts/quality-gate.sh
.quality-system/
```

### 判定

- 契約ファイルとREQファイルの存在確認
- 明示されたコマンドの実行
- 終了コードの記録
- 未定義部分はREVIEW

---

## 6.9 具体例パック設計

具体例パックは、生成品質を安定させるための型紙として扱う。

初期提供例は以下とする。

| 例 | 対象 | 主な検査 |
|---|---|---|
| python-fastapi-pytest | FastAPI API | HTTPステータス、JSON Schema、pytest |
| python-cli-pytest | Python CLI | 終了コード、標準出力、生成ファイル |
| nextjs-vitest-playwright | Next.js UI | DOM属性、ルーティング、Playwright |
| node-cli-vitest | Node CLI | 終了コード、stdout JSON、Vitest |
| go-http-api | Go API | httptest、go test |
| rust-cli | Rust CLI | cargo test、assert_cmd |
| dotnet-webapi | ASP.NET Web API | dotnet test、HTTP API |
| java-spring-boot | Spring Boot | JUnit、MockMvc |

各具体例には以下を含める。

```text
README.md
.quality-system/config.json
.quality-system/req/REQ-APP-001.md
.quality-system/contracts/REQ-APP-001/contract.json
tests/quality/L1_behavior/REQ-APP-001/...
tests/quality/L5_contract/REQ-APP-001/...
scripts/quality-gate.*
scripts/verify-contracts.*
```

---

## 6.10 セキュリティ設計

### 6.10.1 外部命令の無効化

リポジトリ内や外部資料に含まれる自然言語命令を、スキル自体への上位命令として扱わない。

### 6.10.2 証跡情報の制御

証跡には、原則として以下を含めない。

- APIキー
- トークン
- パスワード
- 秘密鍵
- Cookie
- セッション情報
- 個人情報
- 不要な絶対パス

初期版では、完全な自動除去は必須としないが、証跡ポリシーに明示する。

### 6.10.3 コマンド実行安全性

品質ゲートランナーは、事前定義された検査コマンドのみを実行する。

REQやcontract内に任意コマンドを無制限に書ける設計は避ける。

CLI契約でコマンド実行を扱う場合は、許可リスト方式を採用する。

---

## 6.11 LLMレビュー設計

LLMレビューは任意機能とする。

### 6.11.1 役割

LLMレビューは、以下に利用する。

- 要求の曖昧性指摘
- テスト不足候補の抽出
- UX・文言の違和感検出
- セキュリティ観点の補助的指摘
- 境界条件候補の提示

### 6.11.2 禁止事項

LLMレビューは、以下に利用してはならない。

- 単独でALLOWを出す
- 自動的に人間承認を代替する
- 機械的検査の失敗を上書きする
- 証跡なしに合格判断を行う

### 6.11.3 出力扱い

LLMレビュー結果は、必要に応じて以下に保存する。

```text
.quality-system/evidence/<REQ-ID>/latest/llm-review.md
```

LLMレビューで重大な不確実性が検出された場合、判定はREVIEWとする。

---

## 7. 代表ユースケース

## 7.1 既存Python APIプロジェクトへの導入

### 入力指示例

```text
このPython FastAPIリポジトリに、REQ駆動の品質ゲート系を構築してください。
pytestに接続し、REQ-APP-001のサンプル要求、API契約、テスト、証跡出力まで作ってください。
```

### 期待結果

- Pythonアダプタが選択される
- pytest用テストが生成される
- HTTP API契約が生成される
- `python scripts/quality-gate.py REQ-APP-001` が実行可能になる

---

## 7.2 Next.jsプロジェクトへの導入

### 入力指示例

```text
このNext.jsプロジェクトに、画面表示とUI契約を検査する品質ゲートを作ってください。
VitestとPlaywrightが使える前提で、最小のREQとテストを生成してください。
```

### 期待結果

- Node / TypeScriptアダプタが選択される
- L1表示テストが生成される
- L5 UI契約検査が生成される
- `node scripts/quality-gate.mjs REQ-APP-001` が実行可能になる

---

## 7.3 CLIツールへの導入

### 入力指示例

```text
このCLIツールに、終了コード、標準出力、生成ファイルを検査するREQ駆動品質ゲートを作ってください。
```

### 期待結果

- CLI契約が生成される
- コマンド実行結果の証跡が保存される
- stdout JSONや生成ファイルの検査が可能になる

---

## 8. MVP定義

初期MVPでは、以下を実装対象とする。

### 8.1 必須機能

- リポジトリ構成検出
- Python / Node / Generic の初期対応
- `.quality-system` 生成
- REQテンプレート生成
- contract.json生成
- L1 / L5 テストディレクトリ生成
- quality-gateスクリプト生成
- gate.json生成
- summary.md生成
- ALLOW / DENY / REVIEW判定

### 8.2 初期対応例

- Python CLI + pytest
- Python FastAPI + pytest
- Node CLI + Vitest
- Next.js + Vitest
- Generic PowerShell

### 8.3 MVPで扱わないもの

- 完全なL2〜L6自動生成
- 高度なDOMレンダリング検査
- スクリーンショット差分
- 高度なアクセシビリティ検査
- 脆弱性診断
- 完全なCI自動生成

---

## 9. 将来拡張

### 9.1 契約検査の高度化

- OpenAPI検証
- JSON Schema検証
- DOMレンダリング後のセレクタ検証
- PlaywrightによるE2E検査
- DBスナップショット検査
- ログ契約検査

### 9.2 証跡ビューア

証跡を一覧表示するローカルビューアを追加する。

想定機能：

- REQ一覧
- ALLOW / DENY / REVIEW一覧
- gate.json表示
- summary.md表示
- テストログ表示
- 差分表示

### 9.3 CI統合

- GitHub Actions生成
- GitLab CI生成
- Azure Pipelines生成
- PRコメント出力
- JUnitレポート連携

### 9.4 REQ品質レビュー

REQ自体の品質を確認する仕組みを追加する。

検査例：

- 成立条件が検査可能か
- 非目標が明示されているか
- 境界条件があるか
- 契約とテストが対応しているか
- 曖昧語が多すぎないか

### 9.5 言語対応拡張

- Kotlin
- Swift
- Ruby
- Elixir
- C / C++
- PowerShell
- Bash

---

## 10. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| 抽象化しすぎる | 実際には動かない設計になる | 具体例パックを重視する |
| 言語別差分が大きい | 共通仕様だけでは吸収できない | アダプタで分離する |
| ALLOWを過信する | 完全な正しさと誤解される | decision.meaning に明記する |
| 証跡に機密が混入する | ログや環境情報が漏れる | 証跡ポリシーとマスキングを導入する |
| LLMレビューに依存する | 主観評価に戻ってしまう | LLM単独ALLOWを禁止する |
| 初回導入が重くなる | 現場で使われない | L1/L5中心のMVPにする |
| 既存プロジェクトを壊す | テストや依存関係を変更しすぎる | 最小侵襲を原則にする |

---

## 11. 受け入れ条件

本スキルセットの初期版は、以下を満たした場合に受け入れ可能とする。

1. PythonまたはNodeのサンプルプロジェクトに対して、品質ゲート系を生成できる。
2. `REQ-APP-001` のREQ、契約、L1テスト、L5検査を生成できる。
3. 品質ゲートコマンドを実行し、`gate.json` と `summary.md` を出力できる。
4. 検査成功時にALLOWを返せる。
5. 検査失敗時にDENYを返せる。
6. 契約やテストが不足している場合にREVIEWを返せる。
7. ALLOWの意味が「定義済み検査通過」であることを出力内に明示できる。
8. LLMレビュー単独でALLOWを出さない方針が明示されている。
9. 主要言語ごとのアダプタ方針が文書化されている。
10. 少なくとも3種類以上の具体例パックが用意されている。

---

## 12. 開発優先順位

### Phase 1: 仕様固定

- core-spec作成
- gate.json schema作成
- contract.json schema作成
- decision-semantics作成
- LLM review policy作成

### Phase 2: MVP実装

- skill-creator-plus作成
- Pythonアダプタ作成
- Nodeアダプタ作成
- Generic PowerShellアダプタ作成
- 最小品質ゲート生成

### Phase 3: 具体例整備

- Python CLI例
- Python FastAPI例
- Node CLI例
- Next.js例

### Phase 4: 拡張

- Goアダプタ
- Rustアダプタ
- .NETアダプタ
- Javaアダプタ
- CI連携

### Phase 5: 運用支援

- 証跡ビューア
- REQ品質レビュー
- レポート生成
- 導入ガイド整備

---

## 13. 結論

本スキルセットは、LLMの生成能力を前提としつつ、その評価の揺らぎや主観性を直接信頼しないための開発基盤である。

中核は、以下の分離にある。

```text
要求
契約
テスト
証跡
判定
```

この5要素を処理系非依存の共通構造として定義し、各言語・フレームワーク固有の実行方法はアダプタに分離する。

さらに、主要言語ごとの具体例パックを保持することで、抽象的な思想に留まらず、実際に動作する品質ゲート系を短時間で生成できるようにする。

本設計の最も重要な原則は、以下である。

```text
LLMは候補生成と補助レビューには使える。
しかし、LLMの主観評価だけでALLOWを出してはならない。
ALLOWは、定義済みの契約と検査に通過したことのみを意味する。
```

この原則を維持することで、AI生成物を無批判に採用するのではなく、採用可能性を検査・説明・改善できる開発系を構築できる。

