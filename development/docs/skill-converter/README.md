# skill-converter — Phase 5 converter design journal

`tools/build_skill.py` (機械正本) と本 dir (人間正本) の二重ファイル設計で、qgb のスキル変換ロジックを保守する場所。Phase 3 Step 3.0 の `project-context.{md, json}` と同型の二層構造。

## 責務範囲

### 本 dir (人間正本) がカバーするもの

- 各対象 agent の現行仕様の理解と記録 (`agent-*.md`)
- 「なぜそう変換するか」の設計判断と理由 (`agent-*.md` 本文 / 専用 transition file)
- agent 終息 / 後継切替 / 仕様変化への追従履歴 (`transitions/`)
- compatibility matrix (本 README の §現状サマリ)
- converter 保守原則 (本 README の §保守原則)

### 機械正本側 (`tools/build_skill.py` + `skills/source/metadata.schema.json` + `tools/_golden/`) がカバーするもの

- 決定論的なビルド (skills/source + metadata.yaml → dist/skills/)
- 各 agent への変換ロジック (実行コード)
- golden fixture との byte 一致機械検証
- yaml `target_agents` と journal `agent-*.md` の `status: supported` 整合検証 (build_skill.py が実行時に読む)

機械正本側だけでは「なぜこの変換にしているのか」が後から読めない。人間正本側だけでは「どう変換しているのか」が再現できない。両方を維持することで Phase 5 着手後の保守判断が継続可能。

## 現状サマリ (compatibility matrix)

最新版は各 agent file の front matter `last_verified` フィールドを参照。本 matrix は 5.a-0 時点のスナップショット。

| Agent | Status | Last Verified | Full Mode | Split Mode | Hook 機構 | Skills 標準準拠 |
|---|---|---|---|---|---|---|
| Claude Code | supported | 2026-06-27 | ✓ | ✓ | `settings.json` `hooks` / Skill frontmatter `hooks` | ✓ (Agent Skills 標準ベース) |
| Codex CLI | supported | 2026-06-27 | ✓ | ✓ | `~/.codex/hooks.json` / `~/.codex/config.toml` `[hooks]` | ✓ (Agent Skills 標準準拠、`.agents/skills/`) |
| Antigravity CLI | **TODO** (issue [#25](https://github.com/Yumeno/Quality-gate-builder/issues/25)) | — | — | — | — | — |
| Gemini CLI | 扱わない (終息) | — | — | — | — | — |

## 重要発見 (5.a-0 probe 結果)

### Claude Code と Codex CLI は共通の "Agent Skills" 標準に乗っている

- Claude Code: <https://code.claude.com/docs/en/skills> (Agent Skills 標準 + Claude Code 拡張)
- Codex CLI: <https://developers.openai.com/codex/skills> (`.agents/skills/<name>/SKILL.md`、progressive disclosure)
- 標準: <https://agentskills.io>

両 agent が共通の SKILL.md 形式を使っているため、qgb スキルの中間表現を 1 つ書けば **同じ `SKILL.md` を両方の `dist/skills/full/{claude,codex}/` に置ける可能性が高い** (frontmatter キーの細部に違いはあるが、共通核 = `name` / `description` は同型)。

ただし以下に違いがある:

- **配置ディレクトリ**: Claude Code = `~/.claude/skills/<name>/`、Codex CLI = `.agents/skills/<name>/` または `~/.agents/skills/<name>/`
- **frontmatter キー**: Claude Code は豊富 (`allowed-tools`, `disable-model-invocation`, `paths`, `effort`, `model`, `hooks`, `context: fork`, `agent` 等)、Codex CLI は `name` + `description` 必須でその他は未確認
- **dynamic context injection**: Claude Code は `` !`<command>` `` syntax で実行時 shell 注入対応、Codex CLI は progressive disclosure (本体ロード前に description だけ提示) で異なる仕組み

### AGENTS.md は Codex CLI 固有の「instruction chain」用途

- Claude Code には AGENTS.md という慣用ファイルはない (`CLAUDE.md` は別の役割)
- Codex CLI の AGENTS.md は **frontmatter なしの素の Markdown**、ディレクトリ階層で merge (root → cwd)
- 役割: 「Codex builds an instruction chain when it starts (once per run)」=「セッション開始時に組み立てられる instruction の素材」
- 配置: `~/.codex/AGENTS.md` (user) / project root (root から cwd まで) / `.override.md` で上書き可
- max bytes: `project_doc_max_bytes` (default 32 KiB)

これは Phase 5 中間表現の `body.md` (および split build で `body.md` include marker から converter が生成する `workflow.md` / `references.md`、A1' 構造) を **Codex CLI 向けには AGENTS.md として 1 ファイルに連結** する選択肢を示唆 (Codex CLI 利用者が `.agents/skills/qgb/` でなく project root に置きたい場合の経路として)。ただし Phase 5 では **`.agents/skills/qgb/SKILL.md` 経路を main 経路**にして、AGENTS.md は補助的に扱う方針 (Skill 標準の方が wide 適用可能)。なお `workflow.md` / `references.md` は **`skills/source/` には authored source として存在しない** — body.md include marker からの生成物名。

### Hook 機構は両 agent でほぼ並行

- Claude Code: `settings.json` の `hooks` キー、5 種類 (`command` / `http` / `mcp_tool` / `prompt` / `agent`)、40+ lifecycle events
- Codex CLI: `~/.codex/hooks.json` or `[hooks]` in `config.toml`、`command` 型中心、lifecycle events は Claude Code と同型 (SessionStart / PreToolUse / PostToolUse / UserPromptSubmit / Stop 等)

設定 file 場所が違うため hook テンプレは agent ごとに別ファイル (`skills/source/hooks/{claude-code,codex}/`) で持つが、内容は同型化可能。**Phase 5 Step 5.a-2-3 (commit `a7234e6`) + K=2 r1 fix #3 で Claude Code + Codex CLI 両方の hook テンプレを実装済** (`settings.example.json` / `hooks.example.json` + Windows native PowerShell script `scripts/check-relevance.ps1` + `README.md`)。UserPromptSubmit event の matcher フィールドが両 agent で silently ignored であるため、script 内部で stdin JSON の `.prompt` を正規表現判定する設計。

## 保守原則

### 仕様変化への追従

1. agent 公式 docs の仕様が変わったら **`agent-*.md` の `last_verified` を更新** + 本文に変化点を追記
2. 構造的な変化 (agent 終息 / 後継切替 / 主要 frontmatter キーの変更等) は **`transitions/YYYY-MM-<topic>.md` を新設**して経緯を残す
3. converter `tools/build_skill.py` のコードと journal は **同じ commit で更新** (機械正本と人間正本がズレるのが最大のリスク)

### 二重管理回避

- agent の status (supported / experimental / 等) は **`agent-*.md` の front matter で 1 か所だけ管理**
- yaml `target_agents` は集合宣言、build_skill.py が実行時に journal の status を読んで整合検証する
- yaml と journal で同じ情報を両方手で書かない (片方を機械生成にするか、責務を分ける)

### Phase 6 以降への展望

- Antigravity CLI 仕様が整備されたら **issue [#25](https://github.com/Yumeno/Quality-gate-builder/issues/25)** で再判断、本 dir に `agent-antigravity.md` を起こす
- Gemini CLI が完全終息したら `transitions/2026-XX-gemini-removed.md` を残す
- 新規 agent 対応の要望が出たら、本 README の compatibility matrix にまず行を追加 (status = TODO)、issue 起票

## 関連

- `tools/build_skill.py` (機械正本、Phase 5 で実装)
- `skills/source/metadata.yaml` (build matrix の宣言)
- `skills/source/metadata.schema.json` (yaml の JSON Schema)
- `tools/_golden/{claude,codex}/{full,split}/` (golden fixtures)
- `development/docs/journal/phase5-prejournal.md` v4 (本構造の確定経緯)
- `development/docs/journal/phase5-step5-a-0.md` (本 Step の完結ジャーナル、Step 完結時に新設)
