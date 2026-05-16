# フレームワーク境界 v1.0

## 1. 本書の位置づけ

本書は、qgb におけるフレームワーク側（このリポジトリ）と利用者プロジェクト側の境界を定める。

各層の責務、所有物、変更主体を明示することで、qgb 本体に開発過程の履歴が残ること、利用者プロジェクトに不要なフレームワーク内部物が漏れることを防ぐ。

本書は思想憲章 (`philosophy.md`) のうち、特に P4（不易と流行の分離）の運用化を担当する。

## 2. 4 層構造

qgb プロジェクトは次の 4 層で構成される：

```text
[Layer 1] 思想層 — qgb が固定する不易
   ↓ 制約を与える
[Layer 2] フレームワーク層 — qgb 本体（このリポジトリ）
   ↓ 道具を提供する
[Layer 3] スキル層 — Phase 5 のスキル（エージェント中立、3 エージェント向けにビルド）
   ↓ 適応・対話する
[Layer 4] 利用者プロジェクト層 — qgb init 後の対象プロジェクト
```

各層は明確な所有物と責務を持ち、上位層から下位層への一方向の依存関係を保つ。

Layer 3 のスキルは Claude Code / Codex CLI / Gemini CLI のいずれにも投入できる。詳細は §5 を参照。

## 3. Layer 1: 思想層

### 所有物

- `development/docs/philosophy.md` — 思想憲章

### 変更主体

qgb メンテナのみ。改訂は厳格に扱い、バージョン番号を上げる。

### 利用者プロジェクトへの複製

しない。利用者は qgb リポジトリの philosophy.md を直接参照する。

### 上位層

なし（最上位）。

## 4. Layer 2: フレームワーク層（qgb 本体）

### 置くもの

- `qgb/` Python パッケージ本体
  - `core/` — runner, decision, evidence, schema, knowledge, policy, command, stage-design
  - `adapters/` — python, node, go, rust, dotnet, java, php, generic
  - `schemas/` — JSON Schema 群（gate, policy, contract, knowledge, req-meta, config）
  - `templates/` — 生成テンプレート（REQ.md, contract.\*.json, summary.md, quality-gate.ps1）
- `development/docs/` — 開発文書
  - 思想憲章、要件定義書、段階設計仕様、フレームワーク境界（本書）
  - プロジェクト経緯、参考実装情報、発表資料まとめ
- `examples/` — 設計例パック（複数の対象系での段階設計例）
- `tests/` — qgb 本体のテスト
- `skills/` — Phase 5 のスキル定義（Layer 3）
- ルートファイル: `pyproject.toml`, `README.md`, `LICENSE`, `.gitignore`

### 置かないもの

- 開発過程の議論ログ、引き継ぎ資料
- 一度限りの移行・棚卸し資料
- 利用者プロジェクト固有の REQ（examples 内のサンプルは別、これはフレームワークの一部）
- 内部調整の会話記録、設計検討の途中経過
- ChatGPT / Claude / Codex などのチャットログ
- 開発者個人の作業メモ

これらは git 履歴と Issue で追えれば十分であり、リポジトリ本体に常駐させない。

### 変更主体

qgb メンテナ。実装の追加・修正・テストの拡張。

### 利用者プロジェクトへの複製

しない。利用者は git clone で qgb を取得し、`python -m qgb` 経由で実行する。Phase 2 以降で PyPI 配布を検討する場合も、配布物は本層に限定する。

## 5. Layer 3: スキル層（Phase 5、エージェント中立）

### 構造

Layer 3 は **単一の中間表現 + コンバータ + 3 エージェント向け成果物** で構成される：

```text
skills/source/                   # 中間表現（正本、リポジトリで保守）
  metadata.yaml
  body.md
  workflow.md
  references.md
  prompts/
    design-stages.md
    review-policy.md

tools/build_skill.py             # コンバータ（リポジトリで保守）

dist/skills/                     # ビルド成果物（.gitignore、リリース時に生成）
  claude/
  codex/
  gemini/
```

### 中間表現の役割

`skills/source/` がスキルの正本。各エージェント向け成果物はすべてここから派生する。

- `metadata.yaml` — スキル ID、バージョン、各エージェント固有の配置情報
- `body.md` — スキル本体（中立 Markdown）
- `workflow.md` — 作業手順
- `references.md` — Layer 1（思想憲章）と Layer 2（段階設計仕様、設計例パック）への参照集
- `prompts/` — 段階設計フェーズや policy レビュー用のプロンプト断片

`metadata.yaml` の例：

```yaml
skill_id: quality-gate-builder
version: 0.1.0
description: 任意のプロジェクトに証跡ゲートを構築するスキル
entry_body: body.md
helper_files:
  - workflow.md
  - references.md
  - prompts/design-stages.md
  - prompts/review-policy.md
agent_bindings:
  claude:
    skill_dir_name: quality-gate-builder
    frontmatter:
      name: quality-gate-builder
      description: 任意のプロジェクトに証跡ゲートを構築する
      allowed-tools: [Read, Write, Edit, Bash, Glob, Grep]
  codex:
    primary_filename: AGENTS.md
    placement: project_root
    include_helpers_as: appendix
  gemini:
    memory_filename: GEMINI.md
    command_file: .gemini/commands/qgb.toml
    command_name: qgb
    helpers_via_import: true
```

### コンバータの責務

`tools/build_skill.py` は中間表現を読み、3 エージェント向け成果物を `dist/skills/{claude,codex,gemini}/` に生成する。

各エージェント向けの変換規則：

| エージェント | 主成果物 | 補助の扱い | 配置先（利用者環境） |
|---|---|---|---|
| Claude Code | `SKILL.md`（YAML frontmatter 付き） | ディレクトリ内に補助ファイルを実体として配置 | `~/.claude/skills/<skill-id>/` または `.claude/skills/<skill-id>/` |
| Codex CLI | `AGENTS.md`（フラット Markdown） | 補助ファイルを `AGENTS.md` 末尾に章として連結 | プロジェクトルート（`AGENTS.md`） |
| Gemini CLI | `GEMINI.md` + `.gemini/commands/<command>.toml` | 補助ファイルを `@import` で参照、スラッシュコマンドは TOML | `~/.gemini/` またはプロジェクト直下の `.gemini/` |

### コンバータが守るべき制約

- 中間表現を介さない直接編集の禁止（思想憲章 C-008）
- 成果物にコンバータ版数とソースのコミットハッシュを埋め込む（再生成可能性、思想 P7）
- 各成果物に「これは生成物である。`skills/source/` を編集すること」と明示する
- 3 エージェントすべてで動作する共通機能を中核に据え、固有機能は補助的に扱う

### 責務

スキル（生成物が読み込まれた状態）の責務：

- 対象プロジェクトを分析（言語、フレームワーク、目的）
- 思想憲章と設計例パックを参照
- 段階設計案を生成
- ユーザーと対話して確定
- `policy.json`, REQ メタ, contract 雛形を Layer 4 に書き込み
- `qgb validate-policy` を呼んで機械検査

### 読む側（参照元）

- Layer 1: 思想憲章
- Layer 2: 設計例パック、JSON Schema 群、qgb CLI（`python -m qgb` 呼び出し）

### 書く側（出力先）

- Layer 4: 利用者プロジェクトの `.quality-system/`

### 変更主体

- 中間表現とコンバータ: qgb メンテナ
- 生成物: コンバータのみ（手編集禁止）

### 利用者プロジェクトへの複製

スキル本体（中間表現とコンバータ）は qgb リポジトリ側に置く。利用者プロジェクトに複製しない。

利用者はリリース成果物（`dist/skills/{claude,codex,gemini}/` または GitHub Releases）から自分の使うエージェント向けの 1 セットだけを取得し、各エージェントの規約に従って配置する。配置先の詳細はリリースに同梱するインストール手順を参照。

### Phase 計画

- Phase 1〜4: `skills/source/` のディレクトリ構造のみ予約。コンバータ未実装
- Phase 5: 中間表現とコンバータを本実装、3 エージェント向けリリースを CI で生成、GitHub Releases にアタッチ

## 6. Layer 4: 利用者プロジェクト層

### `qgb init` 後に利用者プロジェクトが所有するもの

`.quality-system/` 配下：

```text
.quality-system/
  config.json
  policy.json
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
    project-context.md
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
```

加えて：

- `tests/quality/` または対象系で適切な場所のテスト雛形
- `scripts/quality-gate.ps1` 等の薄いラッパー（任意）
- `.gitignore` への qgb 関連追記（`.quality-system/artifacts/` を除外）

### 採用済み証跡と揮発の分離

- `evidence/<REQ>/latest/` — 採用判定の最新証跡。コミット対象
- `artifacts/<REQ>/runs/<timestamp>/` — 揮発的な実行証跡。`.gitignore` で除外

採用判定 (`evidence/`) を更新できるのは `qgb run` のみ。`qgb verify` は揮発側にのみ書く。詳細は要件定義書 §6 を参照。

### 利用者プロジェクトに複製しないもの

- qgb 本体のソースコード（`qgb/` 配下）
- スキル中間表現とコンバータ（`skills/source/`, `tools/build_skill.py`）
- 思想憲章（`philosophy.md`） — 参照のみ、複製しない
- 設計例パック（`examples/` 配下）
- 段階設計仕様、フレームワーク境界、要件定義書

これらは qgb リポジトリ側に置き、利用者は必要に応じて参照する。利用者プロジェクトには「確定したもの」だけを書く。

利用者は自分が使うエージェント向けのスキル成果物（`SKILL.md` / `AGENTS.md` / `GEMINI.md` のいずれか）だけを GitHub Releases から取得し、各エージェントの規約に従って配置する。

### 変更主体

利用者プロジェクトのメンテナ。qgb は雛形を生成するが、その後の編集は利用者の責任。

### `.gitignore` への追記

`qgb init` は対象プロジェクト直下の `.gitignore` に以下を追記する：

```gitignore
# qgb volatile artifacts
.quality-system/artifacts/
```

既存 `.gitignore` がある場合は追記、無ければ生成する。利用者が手動で外す余地はある（履歴をすべて残したい運用なら採用してよい）。

## 7. 境界の運用原則

### 7.1 symlink 非依存

フレームワーク本体を symlink で参照させない。利用者プロジェクトに必要なファイルは実体として配置する。

- `.quality-system/` 配下は実体ファイル
- `scripts/quality-gate.ps1` も実体ファイル

理由：Windows での symlink 対応の差、環境依存の挙動、CI/CD ツールの symlink 解釈差を回避する。

### 7.2 公開対象には再利用可能なものだけ置く

qgb 本体に開発履歴・引き継ぎ資料を残さない。例外として `development/docs/` は開発判断の根拠として残すが、これは利用者プロジェクトには複製されない。

### 7.3 生成過程の履歴を利用者プロジェクトに継承させない

qgb の Issue 議論、設計検討、ChatGPT/Claude/Codex とのやり取りは qgb 側に閉じる。利用者プロジェクトの `.quality-system/` には「確定したもの」だけを書く。

## 8. 配布形態

### Phase 1

- 配布: git clone + 導入マニュアル
- PyPI 配布は必須としない
- LLM ユーザーがマニュアルに従ってローカル実行できる程度の複雑性に留める

### Phase 2 以降

- PyPI 配布を検討
- 配布物は Layer 2（フレームワーク層）に限定
- サプライチェーンリスク管理を実施（思想憲章 P8 と要件定義書 §6.9 に準拠）

### composer 相当の配布は採用しない

Python は composer のような vendor 配置が標準でない。core の `composer require --dev` モデルは PHP/Symfony 固有の運用であり、qgb はこれを直接模倣しない。

## 9. Phase 5 スキル化での境界

### スキルが対象プロジェクトに生成するもの

- `.quality-system/` 配下のファイル（config, policy, REQ, contract, evidence, knowledge）
- `tests/quality/` 配下のテスト雛形
- `.gitignore` への追記
- `scripts/quality-gate.ps1`（任意）

### スキルが対象プロジェクトに生成しないもの

- 思想憲章のコピー
- 設計例パックのコピー
- qgb 本体のコード
- スキル中間表現とコンバータのコピー
- 他エージェント向けのスキル成果物（利用者が使わないもの）

### スキルの動作

- Read で qgb 側の文書（思想憲章、設計例パック、JSON Schema）を参照
- Write で利用者プロジェクト側にだけ書き込む
- Bash（または各エージェントの相当機能）で `qgb validate-policy` を呼んで機械検査
- ユーザーとの対話で段階設計を確定

### エージェント間の差分の隠蔽

スキル本体（中間表現）は 3 エージェント共通のロジックを記述する。エージェント固有の差分（ツール呼び出しの構文、ファイル読み書きの API、スラッシュコマンドの起動方法）はコンバータが吸収する。

スキル利用者は、自分が使うエージェントの規約に従ってインストールするだけで、同じ動作を得られる。

## 10. 改訂の連動

本書はフレームワーク変更と連動する：

- 新しい adapter が追加されたら、Layer 2 の「置くもの」に列挙
- 新しい JSON Schema が追加されたら、Layer 2 の「置くもの」に列挙
- 利用者プロジェクト側の所有物が増えたら、Layer 4 に追記
- スキルの新機能で生成物が増えたら、Layer 3 / Layer 4 に追記
- 対応エージェントが増減した場合（Phase 5 以降）、Layer 3 の中間表現スキーマとコンバータを更新

## 11. 関連文書

- `philosophy.md` — 思想憲章（本書の上位制約、特に P4）
- `requirements_and_development.md` — 要件定義書
- `stage-design.md` — 段階設計フェーズ仕様
- `examples/` — 設計例パック
- 参考: `yaoyorozu-system/core` の `docs/framework-shape.md`（PHP 版の対応文書）
