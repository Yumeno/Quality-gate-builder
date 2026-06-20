# quality-gate-builder 要件定義書・基本設計書 v0.3

## 1. 文書概要

### 1.1 文書名

quality-gate-builder 要件定義書・基本設計書 v0.3

### 1.2 目的

本書は、任意の対象プロジェクトに対して、要求・契約・テスト・証跡・判定ゲートからなる品質確認系を生成するための `quality-gate-builder` (qgb) について、要件および基本設計を定義する。

本システムは、LLM による生成物や評価を無条件に信頼するのではなく、要求、機械的契約、自動テスト、証跡、ユーザー判断を組み合わせることで、成果物の採用可否を説明可能にすることを目的とする。

### 1.3 v0.3 での主な更新点

本版は v0.2 を全面改訂し、設計判断の整理と関連文書の分離を行った。主な変更：

- 思想層を `philosophy.md`（思想憲章）として分離。本書の上位制約とする
- 固定の L1〜L6 段階体系を削除し、対象系適応的な段階設計に転換
- 段階設計フェーズの仕様を `stage-design.md` として分離
- フレームワーク／利用者プロジェクトの境界を `framework-shape.md` として分離
- 判定値を ALLOW / DENY / REVIEW から ALLOW / DENY の 2 値に整理（REVIEW 廃止）
- 実行前検証フェーズ（READY / NOT_READY）を導入し、構成ミスを判定から分離
- TDD mode の `mode` フィールド削除、`phase` (red/green/refactor/verify) で表現
- gate.json スキーマを最小化（runner / failed_stage / stages[].contract_ref を追加、checks[] を stages[] に統合）
- 採用判定 (`evidence/`) と揮発 (`artifacts/`) の 2 系統パス分離を採用
- 新コマンド `qgb design-stages`, `qgb validate-policy` を追加
- エージェント中立スキル提供方針を追加：単一の中間表現から Claude Code / Codex CLI / Gemini CLI 向けスキル成果物をコンバータで生成する（F-019, C-008）

> 撤回履歴: v0.3 の当初版では「入口分離（`qgb verify` 軽量 / `qgb run` 採用判定）」と新コマンド `qgb verify` を追加していたが、後の Phase 1 spec-review で撤回した。理由は思想憲章 P3（保証対象の転換＝コード不変を前提にしない）と「検査範囲を絞る軽量入口」が緊張するため。部分検証は CLI コマンドでなく REQ 分割（設計）で扱う。詳細は `stage-design.md` §3.1 および `yaoyorozu-entry-points-investigation.md` を参照。

> 2026-06-21 Phase 3 全面再構築: Phase 2 完結後の user 指摘 + Codex セカンドオピニオン (2026-06-20 / 2026-06-21) で次を確定:
> - **adapter 量産方針の撤回**: `qgb detect` / `qgb/adapters/` を廃止。対象プロジェクトの分析は Phase 5 スキル (LLM) の責務、qgb 本体は機械的検査と証跡固定に徹する。理由 = (a) 対象プロジェクトの広がり (Markdown / プロンプト集 / 設定群 / 法務テンプレ等) に adapter 抽象が追いつかない、(b) 検出結果は ALLOW/DENY 判定の根拠でない、(c) 残存すると Phase 5 スキルへの悪い few-shot 教材になる
> - **`.quality-system/project-context.{md,json}` の二重ファイル設計**: md (人間正本、自然言語の設計意図) + json (機械正本、schema 検証可能) で対象プロジェクトの自己定義を表現。補佐 Agent (利用者環境 LLM) が md → json 変換、本番 LLM (Phase 5 スキル) が json を含む propose-context を読む二重 LLM 構造
> - **Phase 4 (CI 連携) の廃止**: 当初項目は別の場所に吸収または WONTFIX (詳細 §13)。qgb 自身の CI は Phase 3 Step 3.1 で最小構成 (qgb の P6 を qgb 自身に適用、POSIX 経路を論証だけで済ませず機械的判定する装置として)
> - **Phase 3 を「機械責務側の最終整備」に再定義**: Step 3.0 (detect 廃止 + project-context 導入) / Step 3.1 (command runner 強化 + CI 雛形) / Step 3.2 (依存解決固定) / Step 3.3 (Phase 2 繰越の実需回収、任意) の 4 サブステップ、規模 3.4〜4.3

### 1.4 対象読者

- quality-gate-builder を設計・実装する開発者
- AI 支援開発環境を構築する技術者
- LLM を用いてソフトウェア開発・検証を行うユーザー
- 要件定義、テスト設計、レビュー、監査に関与する担当者

### 1.5 本書の位置づけ

本書は qgb の要件定義・基本設計の正本である。

ただし、本書は思想憲章 (`philosophy.md`) に従属する。思想憲章と本書が衝突する場合、思想憲章が優先される。

### 1.6 関連文書

本書と並列に維持される文書：

- `philosophy.md` — 思想憲章（本書の上位制約）
- `stage-design.md` — 段階設計フェーズ仕様
- `framework-shape.md` — フレームワーク境界
- `project-background.md` — 本プロジェクトの経緯
- `wakaba-talk-summary.md` — 着想の起点となった発表資料のまとめ
- `yaoyorozu-system-references.md` — 参考実装の情報
- `requirements_and_development.v0.2.md` — 前版（履歴保存）

---

## 2. 背景と課題

背景の詳細は `project-background.md` および `philosophy.md` 第 2 節を参照。

### 2.1 解決すべき課題

1. LLM 生成物の採用可否を、LLM の主観評価だけに依存せず判定したい
2. 要求・契約・テスト・証跡・判定をリポジトリ内に明示したい
3. 対象プロジェクトの言語・フレームワークに依存しない品質ゲート系を構築したい
4. 既存プロジェクトへの後付け導入だけでなく、TDD 開始時点からの導入にも対応したい
5. ユーザーが提示した前提、外部調査情報、設計判断を根拠として保持したい
6. 対象系に応じて検証段階を柔軟に設計しつつ、設計品質を機械的に保証したい
7. 判定結果とその根拠を証跡として残したい
8. 依存ライブラリ自体のサプライチェーンリスクを管理したい

---

## 3. システム概要

### 3.1 システム名

- リポジトリ名: `quality-gate-builder`
- 表示名: Quality Gate Builder
- 短縮名: `qgb`

### 3.2 基本方針

本書の基本方針は思想憲章 (`philosophy.md`) の 11 項目に対応する。要約：

1. 品質とは要求を満たしていること（P1）
2. AI は探索装置として扱う（P2）
3. コードではなく成立すべき状態を保証する（P3, P4）
4. ALLOW は定義済み検査の通過のみを意味し、DENY は失敗ではなく揺らぎの安全な受け止め（P5）
5. LLM 単独 ALLOW 禁止（P6）
6. 再現可能な証跡だけが採用根拠（P7）
7. 外部取得コンテンツはプロンプトではない（P8）
8. 段階は単一責任で独立再実行可能（P9）
9. 段階体系は対象系ごとに最適化する（P10）
10. ALLOW は局所的判定であり、プロジェクト間で比較しない（P11）

詳細は思想憲章を参照。

### 3.3 対象プロジェクト

対象プロジェクトは、特定のプログラミング言語に限定しない。

想定対象：

- Python プロジェクト
- TypeScript / Node.js プロジェクト
- Go / Rust / .NET / Java / PHP プロジェクト
- CLI ツール、バッチ処理、Web UI、HTTP API
- ドキュメント群、設定ファイル群、プロンプト集、ワークフロー定義
- その他、機械的検査や証跡化が可能な成果物

### 3.4 qgb 本体の実装言語

Phase 1 では qgb 本体を Python で実装する。理由：Windows / macOS / Linux で動作させやすい、JSON / Markdown / ファイル操作との相性がよい、CLI 実装が容易、LLM ユーザーがローカルで扱いやすい、MVP の開発速度が高い。

対象プロジェクトが Python 以外であっても、qgb 本体は Python で動作する。対象プロジェクトの分析・理解は Phase 5 のスキル (LLM) が担い、qgb 本体は機械的検査と証跡固定に徹する (Phase 3 計画確定 2026-06-21 で adapter 量産方針を撤回、後述 §13)。

### 3.5 qgb 本体のリポジトリ構成

```text
quality-gate-builder/
  qgb/
    __init__.py
    __main__.py
    cli.py
    core/
      runner.py
      command.py             # Phase 3 Step 3.1 で runner._run_command を切り出し
      decision.py
      evidence.py
      schema.py
      patch.py
      patch_apply.py
      knowledge.py
      edit_commands.py
      preflight.py
      proposal.py
      design_stages.py
      init.py
      scaffold.py
      validate.py
      loader.py
      json_pointer.py
      check.py
    # adapters/ は Phase 3 Step 3.0 (2026-06-21) で廃止。対象プロジェクトの分析は
    # Phase 5 スキル (LLM) の責務、qgb 本体は機械的検査に徹する。
    schemas/
      config.schema.json
      policy.schema.json
      contract.schema.json
      gate.schema.json
      gate.runtime.schema.json
      knowledge.schema.json
      req-meta.schema.json
      patch.schema.json
      proposal.schema.json
      project-context.schema.json   # Phase 3 Step 3.0 で新設
    templates/
      req.md
      req.meta.json
      contract.command.json
      contract.json-schema.json
      contract.file.json
      summary.md
      quality-gate.ps1
  development/
    docs/
      philosophy.md
      requirements_and_development.md
      stage-design.md
      framework-shape.md
      project-background.md
      wakaba-talk-summary.md
      yaoyorozu-system-references.md
      requirements_and_development.v0.2.md
  examples/
    generic-minimal/
    python-cli-pytest/
    markdown-docs/
  skills/
    source/                          # 単一の中間表現（正本）
      metadata.yaml
      body.md
      workflow.md
      references.md
      prompts/
        design-stages.md
        review-policy.md
  tools/
    build_skill.py                   # 3 エージェント向けスキル生成コンバータ
  dist/
    skills/                          # ビルド成果物（.gitignore、リリース時にのみ生成）
      claude/
      codex/
      gemini/
  tests/
  pyproject.toml
  README.md
  LICENSE
```

詳細は `framework-shape.md` Layer 2 を参照。

### 3.6 生成される対象プロジェクト側構造

```text
project-root/
  .quality-system/
    config.json
    policy.json
    project-context.json       # 機械正本: 対象プロジェクトの自己定義 (Phase 3 Step 3.0 で新設)
    req/
      REQ-APP-001.md
      REQ-APP-001.meta.json
    contracts/
      REQ-APP-001/
        S1.json
        S2.json
    knowledge/
      knowledge.jsonl
      source-index.json
      project-context.md       # 人間正本: 自然言語で書く設計意図と背景
    evidence/
      REQ-APP-001/
        latest/
          gate.json
          summary.md
          stages/
            S1.log
            S2.log
    artifacts/
      REQ-APP-001/
        runs/
          2026-05-15T012345Z/
            gate.json
            stages/
              S1.log

  tests/
    quality/
      <stage-id>/
        <REQ>/

  scripts/
    quality-gate.ps1
```

- `evidence/<REQ>/latest/` — 採用判定の最新証跡（コミット対象）
- `artifacts/<REQ>/runs/<timestamp>/` — 揮発的な実行証跡（`.gitignore` で除外）

詳細は `framework-shape.md` Layer 4 を参照。

---

## 4. 用語定義

| 用語 | 意味 |
|---|---|
| REQ | Requirement。成立すべき要求を記述した正本 |
| STAGE | 検証段階。policy.json で定義された単一責任の検査単位 |
| CONTRACT | 機械的に検査可能な契約。段階ごとに REQ 単位で定義される |
| TEST | 要求や契約を検証する自動テスト |
| EVIDENCE | 実行結果、ログ、終了コード、判定結果などの証跡 |
| GATE | REQ 単位で検査を実行し、ALLOW / DENY を返す判定機構 |
| ADAPTER | 言語、フレームワーク、テストランナーごとの差分を吸収する接続層 |
| Project Knowledge Base | 対象プロジェクトの前提情報、外部調査情報、ユーザー判断を保持する根拠ストア |
| ALLOW | 定義済みの必須検査に通過した状態。完全な正しさは保証しない |
| DENY | 定義済みの必須検査に失敗した状態。揺らぎを安全に受け止めた結果であり、失敗ではない |
| READY | 検査を実行可能な準備が整った状態 |
| NOT_READY | 構成不備により検査を実行できない状態。gate.json は生成されない |
| waived | 本来は必要だが、理由つきで免除された状態 |
| phase | TDD サイクル上の位置。`red` / `green` / `refactor` / `verify` |

---

## 5. 要件定義

### 5.1 業務要件

#### B-001: AI 生成物の採用可否判定構造を提供する

AI が生成したコード、設計、テスト、設定ファイルなどを、そのまま採用するのではなく、要求、契約、テスト、証跡に基づいて採用可否を判定できる構造を提供する。

#### B-002: 処理系非依存の品質ゲート思想を提供する

対象プロジェクトの言語やフレームワークにかかわらず、REQ、CONTRACT、STAGE、EVIDENCE、GATE の共通構造を適用できる。

#### B-003: qgb 本体は対象プロジェクトから独立して動作する

qgb 本体は、対象プロジェクトの言語とは独立した Python 製 CLI として実装する。対象プロジェクト固有の検査は、adapter および設定されたコマンドを通じて実行する。

#### B-004: 既存リポジトリへ最小侵襲で導入できる

既存コードへの影響を最小化し、原則として `.quality-system`、`tests/quality`、`scripts` などの追加によって導入できる。

#### B-005: TDD 開始時点から導入できる

既存プロジェクトへの後付けだけでなく、新規開発において REQ、contract、失敗する初期テスト、gate を先に生成できる。

#### B-006: 監査可能な証跡を残せる

REQ 単位で、実行コマンド、検査結果、テスト結果、判定結果、参照した根拠、runner バージョンを証跡として保存できる。

#### B-007: 対象系に応じた段階設計をユーザー裁量で行える

固定の段階体系を強制せず、対象プロジェクトの構造と目的に応じて段階を設計できる。段階の設計品質は機械的に検査される。

#### B-008: LLM ユーザーが導入可能である

Phase 1 では、PyPI 公開や完全自動インストーラを必須とせず、導入マニュアルに従って LLM ユーザーがローカル実行できることを目標とする。

### 5.2 機能要件

#### F-001: リポジトリ構成検出

対象リポジトリを読み取り、以下を推定する：

- 使用言語、フレームワーク、パッケージマネージャ
- テストランナー、Lint ツール、型検査ツール、E2E テストツール
- 実行コマンド候補

検出対象ファイルの例：

```text
package.json, pnpm-lock.yaml, yarn.lock, package-lock.json
pyproject.toml, requirements.txt, uv.lock, Pipfile
Cargo.toml, go.mod, pom.xml, build.gradle
*.csproj, *.sln, composer.json
Makefile, Dockerfile
```

#### F-002: config.json 生成

検出結果を `.quality-system/config.json` に保存する。

例：

```json
{
  "schema_version": "1.0",
  "project": { "name": "sample-project" },
  "runtime": {
    "target_language": "python",
    "framework": "cli",
    "package_manager": "pip",
    "test_runner": "pytest"
  },
  "qgb": {
    "core_language": "python",
    "version": "0.1.0"
  },
  "commands": {
    "unit_test": "pytest",
    "lint": "ruff check"
  }
}
```

#### F-003: policy.json 生成

対象系に応じた段階定義を `.quality-system/policy.json` に保存する。段階の構造は `stage-design.md` を参照。

例：

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
    }
  ]
}
```

#### F-004: REQ 生成

REQ 本文は Markdown で生成する。機械可読メタデータは JSON sidecar として保存する。

```text
.quality-system/req/REQ-APP-001.md
.quality-system/req/REQ-APP-001.meta.json
```

REQ 本文には以下を含める：目的、成立条件、非目標、入力、出力または状態、境界条件、契約、対応する段階、採用条件。

REQ メタには以下を含める：

```json
{
  "req_id": "REQ-APP-001",
  "stages": [
    {
      "stage_id": "S1",
      "contract_ref": ".quality-system/contracts/REQ-APP-001/S1.json",
      "required": true
    }
  ]
}
```

#### F-005: contract.json 生成

各段階の検査パラメータを `.quality-system/contracts/<REQ>/<stage-id>.json` に保存する。

contract.json の構造は `policy.json` の `verification_type` と `required_contract_fields` に従う。

Phase 1 で対応する検査種別：

- `command` — 外部コマンド実行と終了コード検査
- `file_exists` — ファイル存在検査
- `substring_match` — テキスト内文字列包含検査
- `json_schema` — JSON Schema 検証
- `manual_check` — 人間判断（採用判定の根拠にできない）

##### contract.json の verification_type 固有フィールドの扱い

`contract.json` には `verification_type` ごとに必須・任意のフィールドが定まる（例: `command` なら `command`/`expected_exit_code`、`file_exists` なら `target`）。**当該 `verification_type` に対応しない余計なフィールド（別 type の必須フィールド）が混在することは、`qgb validate` 系コマンドで error として扱う**。

- `contract.schema.json` 自体は拡張可能性のため `additionalProperties: true` を維持する
- 検査種別と field の整合性は、`qgb validate` または `qgb validate-policy` 実装時に runner レベルで強制する
- これは思想 P5（ALLOW/DENY の意味の限定）および P7（再現可能な証跡）を、契約の曖昧さで損なわせないための制約である

#### F-006: 段階設計フェーズ

固定の段階体系を持たず、対象系に応じた段階を設計するフェーズを提供する。仕様の詳細は `stage-design.md` を参照。

設計プロセス：

- 提案フェーズ（`qgb design-stages`）— ルールベース推定または対話で段階案を生成
- 採用フェーズ（`qgb design-stages --commit`）— 設計品質検査を経て `policy.json` に焼き込み

#### F-007: 段階の選択と免除

各 REQ メタは `policy.json` で定義された段階のサブセットを宣言する。宣言外の段階は判定対象外（存在しない）。

`waived` メタ：本来必要な段階を理由つきで免除する場合、段階に `waived: true` と `waiver_reason` を付与する。waived 段階は判定対象から除外される。免除判断は `knowledge.jsonl` に記録する。

##### Phase 1 における waiver の audit semantics (Step 6+7 統合レビュー Codex A4/A8 反映)

Phase 1 では waiver は次の意味を持つ。Step 7 実装 + 統合レビューを経て確定:

1. **判定対象除外は人間判断**: waived 段階は decision の判定母集団から除外される。これは「人間が判断して除外した」と明示的に記録された判断であり、自動評価の弱い証拠ではない。
2. **再評価は行わない**: waived とした段階は、その contract が指すファイルや対象コードが変更されても再評価しない。要件§F-007 通り「判定対象から除外」を文字通り適用する。これは思想 **P3 (コードの同一性を保証しない)** と外見上緊張するが、F-007 が「人間判断による除外」を許す設計であることと一貫している。
3. **gate.json の basis は snapshot reference**: `gate.json.basis[]` に書かれた `KNOWLEDGE-WAIVER-<REQ>-<stage>` は run 時点での knowledge.jsonl エントリへの snapshot reference であり、live link ではない。後から knowledge.jsonl を手編集して waiver エントリを削除しても、過去の gate.json は更新されない (gate.json は不変監査記録、knowledge.jsonl は live state)。
4. **waiver の更新・削除は手動操作**: 更新したい場合は knowledge.jsonl の reason を編集し、(削除なら) REQ.meta.json の waived フラグも外して、`qgb run` を再実行する。再実行で新しい gate.json が新しい状態を反映する。

**Phase 2 で検討する拡張** (Phase 1 では out-of-scope):

- waiver の expiry / 有効期限
- contract hash による「waived 後の contract 変更検知」
- 過去の gate.json と現在の knowledge.jsonl の orphan 検証 CLI
- `qgb add-waiver` / `qgb rm-waiver` の専用 CLI

#### F-008: 採用判定の入口は `qgb run` 単一

採用判定の実行入口は `qgb run` のみとする：

- `qgb run <REQ>` — 対象 REQ の**全 stage を実行**し採用判定を残す。揮発側 (`artifacts/.../runs/<ts>/`) と採用側 (`evidence/.../latest/`) の両方を更新

`qgb run` は実行前に確認プロンプトを出す（`--yes` でスキップ可）。

**「検査範囲を絞る軽量入口」(`qgb verify` 相当) は設けない。** 思想憲章 P3（保証対象の転換＝コードの同一性でなく成立すべき状態を保証、コード不変を前提にしない）と緊張するためである。LLM 編集は全文が LLM を通り、要修正部分以外が改変されない保証がない。よって「特定段階だけ追試し、触っていない部分は前回の合格が有効」とする部分追試は、既に合格していた観点が知らぬ間に壊れるリスクを抱える。

「対象を絞って検証したい」というニーズは、実行時に検査範囲を絞るのではなく **REQ 分割（設計）** で満たす：部分部分を独立 REQ として切り、各 REQ は自分の全 stage を `qgb run` で実行する（部分だけ再検証したいときはその REQ だけを run する）。結合検証は結合用の REQ を別途立てる。詳細は `stage-design.md` §3.1 を参照。

#### F-009: 段階の機械検査

`qgb validate-policy` は段階設計の品質と正本ツリーの整合性を機械検査する。検査項目は `stage-design.md` 第 11 節を参照。

Phase 1 必須検査の例：

- 必須正本ファイルの存在 (`.quality-system/config.json` と `.quality-system/policy.json`)
- stage id の重複なし
- `depends_on` が DAG
- 各 stage に `responsibility` が存在
- REQ メタの `stage_id` が policy に存在
- `contract_ref` の指す contract が存在
- contract が canonical layout (`contracts/<REQ>/<stage>.json`) に従う
- `manual_check` のみで構成される REQ は警告

これらは `qgb validate` (個別 JSON 仕様ファイルのスキーマ準拠検査) とは別の責務である。`qgb validate` は「対象プロジェクトに展開された評価システム仕様の JSON が、qgb の機械正本契約 (スキーマ) に従っているか」を見るのに対し、`qgb validate-policy` は「JSON 群が表現する評価システム設計が、思想憲章 P6 / P7 / P9 に沿った整合的な構造になっているか」を見る。両者の責務分離は思想憲章 P9 (単一責任原則) に従う。

#### F-010: 証跡出力

`qgb run` 実行時、採用側と揮発側の両方に書き込む：

```text
.quality-system/evidence/<REQ>/latest/
  gate.json
  summary.md
  stages/
    <stage-id>.log

.quality-system/artifacts/<REQ>/runs/<timestamp>/
  gate.json
  stages/
    <stage-id>.log
```

揮発側は `QGB_KEEP_RUNS` 環境変数で保持件数を制御する（デフォルト 10、`0` で無制限）。

#### F-011: gate.json 生成

判定結果を `gate.json` に保存する。必須フィールド：

| フィールド | 説明 |
|---|---|
| `schema_version` | スキーマバージョン（`major.minor`） |
| `req_id` | REQ ID（`^REQ-[A-Z0-9]+-[0-9]{3,}$`） |
| `timestamp_utc` | 履歴互換 UTC 時刻（`YYYY-MM-DDTHHMMSSZ`） |
| `timestamp_rfc3339` | ツール互換 UTC 時刻 |
| `phase` | TDD サイクル位置（`red` / `green` / `refactor` / `verify`） |
| `status` | 判定結果（`ALLOW` / `DENY`） |
| `failed_stage` | DENY 時の最初に failed になった stage id。ALLOW のとき空文字 |
| `decision` | `result` と `meaning`（ALLOW/DENY の限定的意味） |
| `runner` | `name` と `version`（qgb のバージョン） |
| `paths` | `run_dir`（揮発）と `curated_latest_dir`（採用） |
| `stages[]` | 各段階の結果。`id`, `name`, `result`, `verification_type`, `exit_code`, `contract_ref`, `log_ref` |
| `basis[]` | 判定根拠（REQ, policy, contract, knowledge の id 配列） |

例（ALLOW）：

```json
{
  "schema_version": "1.0",
  "req_id": "REQ-APP-001",
  "timestamp_utc": "2026-05-15T012345Z",
  "timestamp_rfc3339": "2026-05-15T01:23:45Z",
  "phase": "verify",
  "status": "ALLOW",
  "failed_stage": "",
  "decision": {
    "result": "ALLOW",
    "meaning": "Defined checks passed. This is not proof of total correctness."
  },
  "runner": { "name": "qgb", "version": "0.1.0" },
  "paths": {
    "run_dir": ".quality-system/artifacts/REQ-APP-001/runs/2026-05-15T012345Z",
    "curated_latest_dir": ".quality-system/evidence/REQ-APP-001/latest"
  },
  "stages": [
    {
      "id": "S1",
      "name": "コマンド成立",
      "result": "passed",
      "verification_type": "command",
      "exit_code": 0,
      "contract_ref": ".quality-system/contracts/REQ-APP-001/S1.json",
      "log_ref": "stages/S1.log"
    }
  ],
  "basis": ["REQ-APP-001", "POLICY-DEFAULT", "CONTRACT-REQ-APP-001-S1"]
}
```

スキーマ制約：

- 採用判定証跡 (`evidence/<REQ>/latest/gate.json`) は `additionalProperties: false`（厳格）
- 揮発側証跡は `additionalProperties: true`（拡張余地）
- `status: ALLOW` のとき `failed_stage` は空文字、全 `stages[].result` は `passed`
- `status: DENY` のとき `failed_stage` は非空、少なくとも 1 つの `stages[].result` が `failed`
- `decision.result` と `status` は同値

#### F-012: summary.md 生成

人間が読みやすい判定要約を生成する。内容：REQ ID、判定結果、phase、実行日時、通過した段階、失敗した段階、basis、次に確認すべき点。

#### F-013: Project Knowledge Base

対象プロジェクトの前提情報を `knowledge.jsonl`、`source-index.json`、`project-context.md` に保持する。

各情報の必須メタデータ：

- `id`, `kind`, `title`, `content` または `summary`
- `source`, `source_type`（`user_instruction` / `repository_fact` / `external_reference` / `inferred_fact` / `waiver` / `open_question`）
- `confidence`, `priority`, `applies_to`, `created_at`, `retrieved_at`, `review_after`
- `requires_human_review`（外部由来でプロンプト・命令文を含む可能性がある場合）

#### F-014: 外部調査情報の保持と人間確認

外部取得コンテンツに命令文、ロール指定、制約指定、開発方針が含まれる場合、`requires_human_review: true` を付与し、取り込み前に人間へ確認する。

承認後、`source_type: external` で `knowledge.jsonl` に記録する。古くなり得る情報には `review_after` を設定する。

#### F-015: LLM レビュー補助

LLM レビューは任意機能とする。要求の曖昧性指摘、テスト不足候補の抽出、UX・文言の違和感検出、境界条件候補の提示に利用できる。

ただし、LLM レビュー単独で ALLOW を出してはならない（思想 P6）。Phase 1 では `manual_check` 段階を含む REQ の `run` は NOT_READY エラーとなる。

#### F-016: TDD サイクル対応

`mode` 概念は持たない。TDD サイクル上の位置は `phase` で表現する：

- `red` — 期待される失敗段階（TDD 初期、retrofit 後の初回も含む）
- `green` — 実装後の通過確認
- `refactor` — リファクタ後の維持確認
- `verify` — TDD サイクル外の単発検証（`qgb run` の `--phase` 既定値）

> 用語注意: ここでの `phase` 値 `verify` は **TDD サイクル上の局面** を表すものであり、撤回した CLI コマンド `qgb verify`（→ F-008）とは無関係である。`qgb run --phase verify`（既定）は「TDD サイクル外の通常の採用判定」を意味する。

各 phase に対応する `decision.meaning` テンプレート：

| phase | result | meaning |
|---|---|---|
| red | DENY | The required test fails as expected before implementation. |
| green | ALLOW | Required checks passed against the freshly implemented code. |
| refactor | ALLOW | Required checks remained passing after refactor. |
| verify | ALLOW | Defined checks passed. This is not proof of total correctness. |
| verify | DENY | Defined checks did not pass. This is not a failure but a signal to revise. |

TDD 初期の段階を仕込むユーティリティとして `qgb tdd-init <REQ>` を提供する（内部実装は `qgb scaffold --initial-phase red` 相当）。

#### F-017: JSON Patch または専用 CLI による編集

Phase 1 では JSON ファイルの直接編集を許容するが、編集後の `qgb validate` を必須とする。

将来的には、LLM による全文書き換えではなく、JSON Patch または専用 CLI による変更を推奨する。想定コマンド例：

```powershell
python -m qgb validate
python -m qgb patch policy patch.json
python -m qgb add-waiver REQ-APP-001 S6 --reason "Internal CLI tool"
```

#### F-018: 導入マニュアル生成・整備

Phase 1 では導入マニュアルを成果物に含める。必須章立ては §8 を参照。

#### F-019: エージェント中立なスキル提供

qgb の Phase 5 スキルは、Claude Code / Codex CLI / Gemini CLI のいずれにも投入できる形で提供する。

##### 単一中間表現

スキル本体は `skills/source/` 配下の単一の中間表現を正本とする：

```text
skills/source/
  metadata.yaml         # スキル ID、バージョン、各エージェント向けバインディング
  body.md               # スキル本体（中立 Markdown）
  workflow.md           # 作業手順
  references.md         # philosophy.md / stage-design.md などへの参照集
  prompts/
    design-stages.md
    review-policy.md
```

`metadata.yaml` には各エージェント固有の配置情報（filename、frontmatter キー、補助ファイルの取り込み方）を持たせる。中間表現のフォーマット詳細は `framework-shape.md` を参照。

##### コンバータ

`tools/build_skill.py` が中間表現から 3 エージェント向け成果物を生成する：

| エージェント | 成果物 | 配置先（利用者環境） |
|---|---|---|
| Claude Code | `SKILL.md`（YAML frontmatter 付き）+ 補助ファイル一式 | `~/.claude/skills/<skill-id>/` または `.claude/skills/<skill-id>/` |
| Codex CLI | `AGENTS.md`（補助ファイルを末尾に連結したフラット Markdown） | プロジェクトルート |
| Gemini CLI | `GEMINI.md`（補助ファイルを `@import` で参照） + `.gemini/commands/<command>.toml` | `~/.gemini/` またはプロジェクト直下 |

生成物は `dist/skills/{claude,codex,gemini}/` に出力される。`dist/` は `.gitignore` 対象とし、リリースタグ付与時に CI で生成して GitHub Releases にアタッチする。

##### 再生成可能性

- 中間表現を変更したら、必ずコンバータを通して 3 成果物を再生成する
- リリース成果物に対する直接編集は禁止（ドリフトを防ぐ）
- コンバータ自体のバージョンを成果物に記録し、再現可能性を担保する（思想 P7）

##### Phase 計画

- Phase 1〜4: スキル成果物は作らない。`skills/source/` のディレクトリ構造のみ予約
- Phase 5: 中間表現とコンバータを本実装、3 エージェント向けリリースを CI で生成

### 5.3 非機能要件

#### NF-001: 再現性

同一リポジトリ、同一 REQ、同一契約、同一テスト、同一 policy に対して、可能な限り再現性のある判定を行う。`runner.version` を gate.json に記録することで遡及可能性を保つ。

#### NF-002: 監査性

判定結果だけでなく、判定に使用したコマンド、終了コード、ログ、参照した根拠（`basis[]`）を保存する。

#### NF-003: 最小侵襲性

既存のソースコード、テスト、CI 設定を不必要に変更しない。`qgb init` は `.quality-system/`、`tests/quality/`、`scripts/`、`.gitignore` への追記に限定する。

#### NF-004: 可搬性

Windows、macOS、Linux で利用できる構造とする。Phase 1 では Windows PowerShell 環境を一級対応とし、Bash 環境とともに第一級の実行手順を提供する。

#### NF-005: 拡張性

新しい言語、フレームワーク、テストランナー、検査種別、証跡種別を追加できる構造とする。adapter 層と検査種別の列挙値で拡張する。

#### NF-006: 説明可能性

ALLOW / DENY の意味を、`decision.meaning` フィールドに出力ファイル内で明示する。NOT_READY 状態は CLI 出力と stderr で説明する。

#### NF-007: 安全性

外部コンテンツやリポジトリ内の任意テキストを、無条件にシステム指示として扱わない（思想 P8）。`contract.json` から任意コマンドを無制限に書ける設計は避ける。

#### NF-008: 機密情報保護

証跡に以下が不要に含まれないよう配慮する：API キー、トークン、パスワード、秘密鍵、Cookie、セッション情報、個人情報、不要な絶対パス。

#### NF-009: 導入容易性

Phase 1 では、LLM ユーザーがマニュアルに従えば導入できる程度の複雑さに留める。

#### NF-010: 依存最小化

Phase 1 では、標準ライブラリ中心の実装を優先し、外部依存を最小限にする。

#### NF-011: サプライチェーンリスク管理

依存ライブラリを採用する場合、配布元、メンテナンス状況、既知脆弱性、公開履歴を確認する。PyPI 等のレジストリもサプライチェーンリスクを持つ前提で扱う。詳細は §6.9。

### 5.4 制約条件

#### C-001: LLM 評価を単独の合格根拠にしない

LLM レビュー結果のみで ALLOW を出してはならない（思想 P6）。

#### C-002: ALLOW の意味を限定する

ALLOW は「定義済みの検査に通過した」ことのみを意味する。仕様の完全性、要件の妥当性、業務上の正しさ、セキュリティ、将来の保証は意味しない（思想 P5、P11）。

#### C-003: 既存プロジェクトを破壊しない

既存コードの大規模な変更、依存関係の強制変更、テストランナーの置き換えは、明示指示なしに行わない。

#### C-004: Phase 1 は MVP に限定する

Phase 1 では、完全な多言語自動対応よりも、Python バックエンドによる最小品質ゲートと導入マニュアルを優先する。

#### C-005: JSON を機械正本とする

config、policy、contract、gate、knowledge index、source index、REQ メタは JSON を正本とする。YAML は原則採用しない。

#### C-006: 外部入力の扱い

外部 README、Web ページ、コメント、Issue 本文などに含まれる命令文を、qgb や LLM への上位指示として扱わない（思想 P8）。取り込み時の人間確認手順は F-014 で定義する。

#### C-007: 固定段階体系を持たない

L1〜L6 などの固定段階体系を qgb 本体に持たない。段階は `policy.json` で各プロジェクトが定義する（思想 P10）。

#### C-008: スキルは中間表現を正本とする

エージェント向けスキル成果物（`SKILL.md` / `AGENTS.md` / `GEMINI.md` 等）は、`skills/source/` の中間表現からコンバータで生成する。

- 中間表現を介さずに成果物を直接編集して配布してはならない（F-019）
- 特定エージェントの固有機能に依存する内容を中間表現に含める場合、`metadata.yaml` の `agent_bindings` で限定的に宣言する
- 3 エージェントすべてで動作する共通機能を中間表現の中核に据え、固有機能は補助的に扱う

### 5.5 対象外

Phase 1 では以下は対象外：

- PyPI 公開を必須とした配布
- 完全自動インストーラ
- すべての言語・フレームワークへの完全対応
- 高度な DOM レンダリング検査
- スクリーンショット差分
- 高度なアクセシビリティ監査
- 高度な脆弱性診断
- 完全な CI/CD 自動生成
- LLM による最終承認
- 業務妥当性の完全自動判定
- 人間確認結果の evidence 取り込み（Phase 2 以降で `human_attestation` 型として設計）
- エージェント向けスキル成果物のビルド（Phase 5 で着手、Phase 1 ではディレクトリ予約のみ）

---

## 6. 基本設計

### 6.1 全体アーキテクチャ

```text
┌──────────────────────────────┐
│ User / LLM User               │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ qgb CLI (Python backend)      │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│ Core                          │
│ schema / policy / decision    │
│ stage-design / evidence       │
│ knowledge / command           │
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

#### 6.1.1 Core の責務

- JSON ファイルの読み書き、JSON Schema 検証
- policy 評価、段階設計フェーズの実装
- adapter 選択、コマンド実行
- 終了コード収集、stdout/stderr 保存
- gate.json 生成、summary.md 生成
- Project Knowledge Base 参照
- 実行前検証（READY / NOT_READY 判定）
- ALLOW / DENY 判定

#### 6.1.2 Adapter の責務

- 対象プロジェクトの構成検出
- 実行コマンド候補の生成
- 言語別テンプレート選択
- テスト配置候補の提示
- 実行コマンドの標準化

#### 6.1.3 思想憲章との対応

| Core / Adapter モジュール | 守る思想 |
|---|---|
| `decision.py` | P5, P11 |
| `stage_design.py` | P9, P10 |
| `policy.py` | P9, P10 |
| `evidence.py` | P7 |
| `command.py` | P7, NF-007 |
| `knowledge.py` | P8 |

### 6.2 CLI 設計

#### 6.2.1 Phase 1〜2 で確立された必須コマンド

```powershell
python -m qgb init
python -m qgb design-stages [propose-context|adopt]   # Phase 2 Step 2.5 で Pattern B 追加
python -m qgb scaffold <REQ>
python -m qgb validate
python -m qgb validate-policy
python -m qgb run <REQ>
python -m qgb check [REQ]                              # Phase 2 Step 2.4
python -m qgb dev [REQ]                                # Phase 2 Step 2.4 (check の alias)
python -m qgb patch <target> <patch.json>              # Phase 2 Step 2.2
python -m qgb add-waiver <REQ> <stage-id> --reason "..."  # Phase 2 Step 2.3
python -m qgb add-knowledge <file>                     # Phase 2 Step 2.3
```

#### 6.2.2 Phase 3 Step 3.0 で廃止されたコマンド

```powershell
python -m qgb detect    # 廃止 (2026-06-21): 対象プロジェクトの分析は Phase 5 スキル (LLM) の責務
```

`detect` は対象プロジェクトの言語/フレームワーク/test runner を機械的に検出するコマンドだったが、
(a) 対象プロジェクトの広がり (Markdown / プロンプト集 / 設定群 / 法務テンプレ等) に
adapter 抽象が追いつかない、(b) 検出結果は ALLOW/DENY 判定の根拠にならない、
(c) 残存すると Phase 5 スキルが「対象判定 = 機械的検出モジュール」を悪い few-shot として
学ぶ誘因になる、の 3 点で廃止。対象プロジェクトの自己定義は `project-context.md`
(人間正本) と `project-context.json` (機械正本) で表現する。

#### 6.2.3 Phase 1 任意コマンド (未実装)

```powershell
python -m qgb verify-contract <REQ> <stage-id>
python -m qgb tdd-init <REQ>
```

#### 6.2.4 終了コード

| 終了コード | 意味 |
|---|---|
| 0 | 成功（ALLOW、または検査自体の成功） |
| 1 | DENY |
| 2 | NOT_READY（構成不備、ファイル不在、検証エラー） |
| 64 | CLI usage error（不明な引数、未実装サブコマンドの呼び出し、argparse のエラー） |
| その他 | 内部エラー |

`64` は BSD sysexits.h の `EX_USAGE` に対応する。`argparse` はデフォルトで引数エラー時に exit 2 を返すが、これは NOT_READY と衝突するため、qgb の CLI は argparse の `error()` を上書きして exit 64 に逃がす。NOT_READY (exit 2) は実行前検証フェーズが意図的に返す状態であり、CLI の引数エラーとは区別される。

#### 6.2.5 将来コマンド (Phase 3 以降)

```powershell
qgb init                  # bare entry point は Phase 3 繰越項目 13 (低優先)
qgb run <REQ>
qgb create-skill          # Phase 5 で Skill Creator 化
```

`qgb design-stages --interactive` は Phase 2 で意図的に採用しなかった。qgb 本体は LLM を直接呼ばず、`design-stages propose-context` + `design-stages adopt` の構造化 interface に徹する (Pattern B、思想 P2 / P6 / NF-010)。


### 6.3 判定設計

#### 6.3.1 判定値

| 判定 | 意味 | 採用可否 |
|---|---|---|
| ALLOW | 定義済み必須段階を通過した | 条件付き採用可（思想 P5, P11 のもとで） |
| DENY | 定義済み必須段階に失敗した | 採用不可。ただし失敗ではなく、再生成と再判定への入口 |

`NOT_READY` は判定値ではなく、検査実行前の状態。gate.json は生成されない。

#### 6.3.2 判定フロー

```text
qgb run <REQ>
  ↓
[実行前検証]
  ├─ qgb validate 失敗 → NOT_READY (exit 2)
  ├─ contract_ref が指す contract 不在 → NOT_READY
  ├─ REQ メタの stage_id が policy 未定義 → NOT_READY
  ├─ depends_on が DAG でない → NOT_READY
  ├─ required stages が空 → NOT_READY
  ├─ manual_check のみで構成 → NOT_READY (Phase 1)
  └─ READY → [採用判定へ]

[採用判定]
  ├─ 全 required 段階通過 → ALLOW (exit 0)
  └─ いずれかの required 段階失敗 → DENY (exit 1)
```

#### 6.3.3 waived の扱い

`waived: true` の段階は判定対象から除外される。免除判断は `knowledge.jsonl` に記録：

```json
{
  "id": "WAIVER-REQ-APP-001-S6",
  "kind": "waiver",
  "title": "L6 体験段階の免除",
  "applies_to": "REQ-APP-001",
  "stage_id": "S6",
  "reason": "Internal CLI tool, no UI",
  "decided_by": "user",
  "created_at": "2026-05-15T01:23:45Z"
}
```

### 6.4 段階設計

段階設計の詳細は `stage-design.md` を参照。本書では要点のみ：

- 固定の段階体系（L1〜L6 など）は持たない（思想 P10）
- `policy.json` がプロジェクト全体の段階定義、REQ メタが REQ ごとの段階選択（二段構造）
- 段階間の依存関係は DAG
- 推奨段階数は 3〜7
- 段階設計フェーズは「提案」と「採用」の 2 段階
- 採用フェーズは `qgb validate-policy` をパスしないと完了しない

### 6.5 ファイル形式設計

#### 6.5.1 方針

```text
JSON     = 機械正本
Markdown = 人間向け文書
text/log = 実行ログ
XML      = 互換出力が必要な場合のみ
YAML     = 原則使用しない
```

#### 6.5.2 JSON 正本

- config.json
- policy.json
- contract.json
- gate.json
- REQ メタ JSON
- source-index.json
- knowledge schema

#### 6.5.3 Markdown 文書

- REQ 本文
- summary.md
- project-context.md
- 導入マニュアル
- LLM レビュー結果

#### 6.5.4 LLM による編集方針

Phase 1 では JSON 直接編集を許容するが、編集後に必ず `qgb validate` と `qgb validate-policy` を実行する。将来的には JSON Patch または専用 CLI による変更へ寄せる。

### 6.6 依存ライブラリ・サプライチェーン設計

#### 6.6.1 基本方針

Phase 1 では外部依存を最小限にする。可能な限り Python 標準ライブラリで実装する。

#### 6.6.2 調査項目

外部依存採用時には、公式リポジトリ、配布元、メンテナンス状況、リリース履歴、ライセンス、既知脆弱性、不審なメンテナ交代、依存ツリーの大きさ、postinstall 等の危険な仕組みの有無、ネットワーク通信の有無、バイナリ配布の有無を確認する。

#### 6.6.3 PyPI に関する方針

PyPI もサプライチェーンリスクを持つ前提で扱う。Phase 1 では PyPI からの導入を必須にしない。初期利用者は、リポジトリを取得し、導入マニュアルに従ってローカル実行できればよい。

---

## 7. Phase 1 MVP 定義

### 7.1 Phase 1 の目的

完全な多言語品質ゲート生成基盤ではなく、Python バックエンドで動作する最小構成と、LLM ユーザーが導入できるマニュアルを提供する。

### 7.2 Phase 1 必須成果物

- Python 製 qgb CLI
- `.quality-system` 初期化機能
- config.json、policy.json、REQ Markdown + meta JSON、contract.json、gate.json、summary.md
- 採用側 (`evidence/`) と揮発側 (`artifacts/`) の 2 系統証跡
- 段階設計フェーズ（パターン A: ルールベース推定 + 確認）
- policy 設計検査器（`qgb validate-policy`）
- Generic adapter
- Python adapter
- 設計例パック 3 例（`generic-minimal`, `python-cli-pytest`, `markdown-docs`）
- 導入マニュアル
- 依存ライブラリ調査ポリシー
- 思想憲章、段階設計仕様、フレームワーク境界（本書と並列）

### 7.3 Phase 1 対応コマンド

```powershell
python -m qgb init
python -m qgb detect
python -m qgb design-stages [--commit]
python -m qgb scaffold <REQ>
python -m qgb validate
python -m qgb validate-policy
python -m qgb run <REQ>
```

### 7.4 Phase 1 で扱う対象例

- Generic（言語非依存、最小例）
- Python CLI
- Markdown ドキュメント群

### 7.5 Phase 1 で扱わないもの

- 完全な GUI
- PyPI 公開必須化
- 完全な CI 生成
- 全言語 adapter 完成
- 高度な LLM レビュー
- 高度な画面検査
- 高度なセキュリティスキャン
- 人間確認結果の evidence 取り込み

---

## 8. 導入マニュアル要件

Phase 1 の導入マニュアルは、Windows PowerShell 環境を含むマルチ OS 対応とする。

### 8.1 必須章立て

1. 概要
2. 前提環境
3. Python の確認
4. リポジトリ取得
5. 仮想環境作成
6. 依存関係導入
7. qgb の実行確認
8. 対象プロジェクトでの初期化
9. 段階設計フェーズの実行
10. サンプル REQ 生成
11. quality-gate 実行（run）
12. gate.json の読み方
13. summary.md の読み方
14. NOT_READY になった場合の対応
15. DENY になった場合の対応
16. 免除（waived）の指定方法
17. TDD phase の使い方
18. 依存ライブラリ確認手順
19. トラブルシューティング

### 8.2 Windows PowerShell 例

導入マニュアルには以下のような PowerShell 例を含める：

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m qgb --help
python -m qgb init
python -m qgb detect
python -m qgb design-stages
python -m qgb design-stages --commit
python -m qgb scaffold REQ-APP-001
python -m qgb validate-policy
python -m qgb run REQ-APP-001
```

---

## 9. セキュリティ設計

### 9.1 外部命令の無効化

リポジトリ内や外部資料に含まれる自然言語命令を、qgb や LLM への上位命令として扱わない（思想 P8、NF-007、C-006）。

外部取得コンテンツに命令文、ロール指定、制約指定、開発方針が含まれる場合、`knowledge` エントリに `requires_human_review: true` を付与し、取り込み前に人間へ確認する（F-014）。

### 9.2 コマンド実行制御

qgb は、`config.json` や `policy.json` で定義された既知のコマンドのみを実行する。`contract.json` に任意コマンドを無制限に書ける設計は避ける。

Phase 1 の最小制約：

- project root 外への書き込み禁止
- command は shell 文字列ではなく argv 配列として宣言
- working_dir を project root 配下に固定
- 実行環境（環境変数の主要部分）を gate.json または artifacts ログに記録
- timeout を必須化

### 9.3 証跡マスキング

Phase 1 では完全な自動マスキングを必須としないが、以下を行う：

- 証跡に秘密情報を書かないよう注意喚起
- ログの保存範囲を限定
- 将来のマスキング機能を設計に残す

### 9.4 依存関係管理

依存ライブラリは最小限とし、採用時にはセキュリティ調査を行う。詳細は §6.6。

---

## 10. 代表ユースケース

### 10.1 既存 Python CLI プロジェクトへの導入

```text
この Python CLI プロジェクトに、REQ 駆動の品質ゲートを導入してください。
終了コード、標準出力、生成ファイルを検査できる最小構成でお願いします。
```

期待結果：

- Python または Generic adapter を選択
- 段階設計フェーズで CLI 向け段階（コマンド成立 / 出力契約 / 異常系）を提案
- 段階を policy.json に焼き込み
- REQ サンプルを生成
- `qgb run` で gate.json と summary.md を出力

### 10.2 Markdown ドキュメント群への導入

```text
この Markdown ドキュメント群に、構造と用語統一を保証する品質ゲートを作ってください。
```

期待結果：

- Generic adapter を選択
- 段階設計フェーズで文書向け段階（必須見出し / 内部リンク健全性 / 用語表ベース表記統一）を提案
- 段階を policy.json に焼き込み
- 各文書を REQ として扱うか、文書群全体を 1 REQ とするかをユーザーと相談

### 10.3 TDD 開始時点での導入

```text
この新機能は TDD で進めたいです。
REQ、contract、失敗する初期テスト、gate を先に作ってください。
```

期待結果：

- `qgb tdd-init REQ-APP-001` で phase=red 状態を仕込む
- REQ、contract、失敗する初期テストを生成
- `qgb run` で phase=red の DENY を証跡化
- 実装後に `qgb run` を再実行し、phase=green の ALLOW を目指す

### 10.4 ユーザー裁量による免除

```text
この REQ は内部バッチなので、UI 系の段階は免除してください。
理由も証跡に残してください。
```

期待結果：

- 該当段階に `waived: true` と `waiver_reason` を付与
- `knowledge.jsonl` に waiver エントリを追加
- gate.json の `basis[]` で waiver を参照
- waived 段階は判定対象から除外

---

## 11. リスクと対策

| リスク | 内容 | 対策 |
|---|---|---|
| LLM 評価への依存 | 主観評価を合格根拠にしてしまう | LLM 単独 ALLOW 禁止、`manual_check` の NOT_READY 化（思想 P6） |
| ALLOW 過信 | 完全な正しさと誤解される | `decision.meaning` に明記（思想 P5、P11） |
| 段階設計の甘さ | スキルが甘い段階を設計しても通る | `qgb validate-policy` で機械検査（思想 P9） |
| 未定義検査の見落とし | 構成ミスが DENY に紛れる | NOT_READY 状態で gate.json を出さない |
| 自由設計の恣意性 | プロジェクトごとに ALLOW の意味がずれる | 思想 P11、`basis[]` 必須化 |
| JSON 編集ミス | LLM が JSON を壊す | `qgb validate`、`qgb validate-policy` 必須、将来 JSON Patch 化 |
| 依存ライブラリリスク | PyPI 等経由のサプライチェーン攻撃 | 依存最小化、採用前調査 |
| 証跡への機密混入 | ログに秘密情報が残る | 保存範囲制御、将来マスキング |
| 導入が重い | ユーザーが使わない | Phase 1 は Python CLI + マニュアルに限定 |
| 外部情報の劣化 | 古い仕様を根拠にする | `retrieved_at` / `review_after` を保持 |
| 任意コマンド実行 | contract から任意コマンドが走る | argv 配列宣言、working_dir 固定、timeout 必須 |

---

## 12. 受け入れ条件

Phase 1 は以下を満たした場合に受け入れ可能とする：

1. Python で qgb CLI を起動できる
2. `python -m qgb init` で `.quality-system` を生成できる
3. `python -m qgb detect` で対象系を推定できる
4. `python -m qgb design-stages` で段階を提案でき、`--commit` で採用できる
5. config.json、policy.json、REQ、contract.json を生成できる
6. `python -m qgb validate` で JSON 正本を検証できる
7. `python -m qgb validate-policy` で段階設計の品質を検査できる
8. `python -m qgb run <REQ>` で採用判定を残せる（常に全 stage を実行する）
9. gate.json、summary.md、stages/\*.log を出力できる
10. 採用側 (`evidence/.../latest/`) と揮発側 (`artifacts/.../runs/<ts>/`) の 2 系統に書き込める
11. 検査成功時に ALLOW を出せる
12. 検査失敗時に DENY を出せる
13. 構成不備時に NOT_READY を出し、gate.json を生成しない
14. `phase: red` の DENY を期待結果として証跡化できる
15. `manual_check` を含む REQ の run は NOT_READY となる
16. waived を理由つきで `knowledge.jsonl` に記録できる
17. Project Knowledge Base にユーザー明示情報を保存できる
18. 外部由来情報に `requires_human_review` を付与できる
19. 設計例パック 3 例（generic-minimal / python-cli-pytest / markdown-docs）が動作する
20. 導入マニュアルが存在する
21. 依存ライブラリ採用方針とセキュリティ確認手順が文書化されている
22. LLM レビュー単独で ALLOW を出さない方針が明示されている
23. 思想憲章、段階設計仕様、フレームワーク境界の 3 文書が並列に維持されている
24. `skills/source/` のディレクトリ構造が予約されており、Phase 5 でのエージェント中立スキル提供方針 (F-019) が要件として確定している

> 補足: 旧受け入れ条件 8「`qgb verify <REQ>` で軽量チェックを実行できる」は削除した。qgb は「検査範囲を絞る軽量入口」を持たない（思想憲章 P3 と緊張するため）。部分検証は実行時オプションでなく REQ 分割（設計）で解く。経緯は `stage-design.md` §3.1 および `yaoyorozu-entry-points-investigation.md` を参照。

---

## 13. 開発フェーズ

### Phase 1: Python CLI MVP + 導入マニュアル

- Python 製 qgb CLI（init, detect, design-stages, scaffold, validate, validate-policy, run）
- JSON 正本、JSON Schema 検証
- 段階設計フェーズ（パターン A）
- policy 設計検査器
- 採用 / 揮発の 2 系統証跡
- Generic adapter、最小 Python adapter
- 設計例パック 3 例
- 導入マニュアル
- 依存関係セキュリティ方針

### Phase 2: 編集安全化と拡張入口

> 主軸: **「編集を安全にする」**。Phase 1 で確立した検証装置の上に「修正手段の構造化」を載せる。adapter 量産 (Phase 3) と provider integration (Phase 4) には踏み込まない。
>
> Codex 計画レビュー (2026-06-01) で 7 サブステップに分解。詳細は `detailed-design.md` §14。規模感は Phase 1 Step 5 を 1.0 として **6.2〜10.0** (Phase 1 全体と同等以上)。

**サブステップ:**

- **Step 2.1 schema baseline** — format assertion / `$ref` allowlist / 後方互換監査
- **Step 2.2 patch substrate** — JSON Patch subset (`add` / `replace` / `remove` / `test`) の atomic apply 基盤
- **Step 2.3 domain edit commands** — `qgb add-waiver` / `qgb add-knowledge` / knowledge orphan check
- **Step 2.4 daily verification channel** — `qgb check` / `qgb dev` (tmp artifacts、curated `evidence/latest/` 不変)
- **Step 2.5 Pattern B external-LLM interface** — context export / proposal import (qgb は LLM を直接呼ばない)
- **Step 2.6 example packs** — FastAPI / Go / Next.js (3 サブステップに分割)
- **Step 2.7 strictness review** — `additionalProperties: false` 判断 / docs / migration notes

**Phase 2 着手前確定の設計境界 5 件:**

1. **Pattern B の LLM 境界**: qgb は LLM を直接呼ばない。context export + proposal/patch import + validate に徹する (思想 P2 / P6 / NF-010、Phase 5 skill との接続)
2. **JSON Patch subset**: `add` / `replace` / `remove` / `test` のみ。`move` / `copy` は Phase 3
3. **`qgb check` / `qgb dev` の証跡**: tmp artifacts は出すが、curated `evidence/latest/` は更新しない
4. **schema strict mode**: 段階的。前半 format + `$ref` allowlist、`additionalProperties: false` は `--strict` フラグで独立
5. **waiver 削除**: Phase 2 では add のみ。削除 / revoke / supersede モデルは Phase 3

### Phase 3: 機械責務側の最終整備 (2026-06-21 全面再構築)

> Phase 2 完結後の user 指摘 + Codex セカンドオピニオン (2026-06-20 / 2026-06-21) で、当初の Phase 3 計画 (adapter 量産 6 言語 + Phase 2 繰越 + Phase 1 負債) を全面再構築した。
>
> 撤回した方針:
> - **adapter 量産 (Go / Rust / .NET / Java / PHP / Markdown adapter)** — 対象プロジェクトの広がりに adapter 抽象が追いつかず、検出結果は ALLOW/DENY 判定の根拠でない。Phase 5 スキルが対象を読んで分析する責務に統合。
> - **Phase 4 (CI 連携)** — 廃止。当初項目は別の場所に吸収または WONTFIX (§14 参照)。qgb 自身の CI は本 Phase 3 で最小構成。
>
> 新方針: **「機械責務側の最終整備 = Phase 5 スキル提供の前提条件を揃える」**。規模 3.4〜4.3 (Phase 1 / Phase 2 と比べて軽量)。

**サブステップ:**

- **Step 3.0 detect 廃止 + project-context 導入** (規模 2.0〜2.5)
  - `qgb detect` / `qgb/core/detect.py` / `qgb/adapters/` 削除
  - `.quality-system/project-context.json` 新設 (機械正本、schema 検証可能)
  - 既存 `.quality-system/knowledge/project-context.md` は人間正本として温存
  - `qgb design-stages propose-context` の出力から `detect` フィールド削除、`project_context` フィールド追加
  - 補佐 Agent (利用者環境の LLM) が md → json 変換、本番 LLM (Phase 5 スキル) が propose-context → proposal 生成、の二重 LLM 構造
  - `source_metadata.generated_by` で「人間 / agent-assisted」を区別、`human_reviewed: bool` で人間承認状態を表現
- **Step 3.1 command runner 強化 + CI 雛形** (規模 1.5〜2.0)
  - `qgb/core/runner.py` の `_run_command` を `qgb/core/command.py` に切り出し (P9)
  - Popen + process tree kill (Windows: ctypes 経由 Job Objects + fallback / POSIX: setsid + killpg)
  - `.bat` / `.cmd` argument escaping (cmd.exe メタ文字 + C++ argv parsing を別扱い)
  - ストリーム読み取り 16 MiB 上限 (RSS cap は WONTFIX、出力ストリーム cap として処理)
  - 実 temporary `.bat`/`.cmd` fixture で検証
  - CI 雛形 (.github/workflows/test.yml): pytest only、windows-latest + ubuntu-latest matrix、actions/checkout + actions/setup-python の commit SHA pin、permissions: contents: read、third-party action ゼロ、secrets 不使用、Dependabot/Renovate なし
- **Step 3.2 依存解決固定** (規模 0.5〜0.8)
  - `pip-tools` or 同等で lock/hash (Phase 5 スキル提供時の supply-chain 信頼)
  - CI で resolved deps 出力
  - 当初 Phase 4 の「依存 audit / SBOM」はここで吸収
- **Step 3.3 Phase 2 繰越の実需回収 (任意)** (規模 0.5〜1.0)
  - Phase 5 で必要が判明したものに限定: `--strict` 実体実装 / waiver 削除 (revoke/supersede) / JSON Patch `move`/`copy` / multi-doc transaction (one-shot rename) / `qgb dev` の changed-files 絞り込み / 全 REQ 一括 check
  - 先回りで全部やらず、Phase 5 着手中に必要が出たものから

**Phase 3 完結条件:**

- Step 3.0 / 3.1 / 3.2 が完結し、CI 緑
- Step 3.3 は実需に応じた取捨選択を user と合意して決着
- Phase 5 (Skill Creator 化) 着手前提が揃う

### Phase 4: 廃止 (2026-06-21)

当初の Phase 4 (CI 連携) は次の理由で廃止した:

- **GitHub Actions / GitLab CI 例**: Phase 5 のスキル生成テンプレに含める (利用者プロジェクト向け)、qgb 本体の独立 Phase にする必然性なし
- **JUnit XML 出力**: WONTFIX。P11 (ALLOW の比較不可能性) と緊張。qgb の gate.json を CI ツール間で比較可能なふりをする方向はマーケティング目的の qgb 認証化に道を開く
- **PR コメント用 summary**: WONTFIX。利用者運用、qgb 責務外。summary.md は既に Phase 1 で生成済み
- **採用判定のレビュー連動**: WONTFIX。利用者の運用設定 (branch protection 等) で実現
- **CI による依存 audit / SBOM 生成**: Phase 3 Step 3.2 (依存解決固定) で吸収
- **qgb 自身の CI**: Phase 3 Step 3.1 で最小構成 (qgb の P6 を qgb 自身に適用、POSIX 経路を論証だけで済ませず機械的判定する装置)

### Phase 5: Skill Creator 化（エージェント中立、adapter なしで設計）

- スキル中間表現 `skills/source/` の整備（`metadata.yaml`, `body.md`, `workflow.md`, `references.md`, `prompts/`）
- コンバータ `tools/build_skill.py` の実装
- Claude Code 向け成果物（`SKILL.md` + 補助ファイル）の生成
- Codex CLI 向け成果物（`AGENTS.md` 単体）の生成
- Gemini CLI 向け成果物（`GEMINI.md` + `.gemini/commands/qgb.toml`）の生成
- 3 エージェント向け CI ビルドと GitHub Releases へのアタッチ
- 段階設計フェーズ（パターン B / C）の自律実行
- 設計例パック few-shot 参照 (Phase 2 で 6 例完成済み、Phase 5 で必要に応じて追加: prompt-collection / terraform-modules / sql-schemas / legal-templates / mixed-devops 等の言語非依存ドメイン)
- 3 エージェント向け運用ガイド（インストール・更新・トラブルシューティング）
- **スキルが対象プロジェクトを Read で読んで分析** (adapter なし、対象理解は LLM 責務、ALLOW/DENY は qgb の contract 実行結果で決まる)
- 利用者プロジェクトに CI テンプレ (GitHub Actions 等) を生成する機能はスキルに含める (当初 Phase 4 の項目を吸収)

---

## 14. 結論

quality-gate-builder は、LLM の生成能力を活用しつつ、その評価の揺らぎを外部化された構造で抑えるための品質ゲート生成基盤である。

本システムの中核は、以下の分離にある：

```text
要求
契約
段階（対象系ごとに自由設計）
証跡（採用 / 揮発の 2 系統）
判定（ALLOW / DENY / NOT_READY の 3 層）
根拠情報
```

Phase 1 では、対象プロジェクトの言語に依存しない Python 製 CLI として最小実装し、JSON を機械正本、Markdown を人間向け文書として扱う。

また、依存ライブラリ自体もサプライチェーンリスクを持つ前提で、標準ライブラリ中心・依存最小化・採用前調査を基本方針とする。

最も重要な原則は思想憲章 (`philosophy.md`) に集約される。要約：

```text
LLM は候補生成と補助レビューには使える。
しかし、LLM の主観評価だけで ALLOW を出してはならない。
ALLOW は、定義済みの段階と検査に通過したことのみを意味し、当該プロジェクト内の局所的判定である。
DENY は失敗ではなく、揺らぎを安全に受け止めた結果である。
NOT_READY は構成不備であり、gate.json には含まれない。
段階は対象系ごとに自由設計されるが、単一責任原則と機械検査による品質保証が守られる。
ユーザーが明示的に免除を定義した場合は、その理由を証跡に残したうえで判定から除外できる。
```

この原則により、AI 生成物を無批判に採用するのではなく、採用可能性を検査・説明・改善できる開発系を構築する。
