# Phase 5 Step 5.a-0 完結ジャーナル: Agent contract probe

完結日: 2026-06-27
着手前判断: `phase5-prejournal.md` v4 (commit `9fb089b`)

## Step 5.a-0 で確立した境界 (恒久記録)

### Agent contract probe の結論

| Agent | Status | 主要参照 |
|---|---|---|
| Claude Code | supported | <https://code.claude.com/docs/en/skills>, <https://code.claude.com/docs/en/hooks> |
| Codex CLI | supported | <https://developers.openai.com/codex>, <https://developers.openai.com/codex/skills>, <https://developers.openai.com/codex/hooks>, <https://developers.openai.com/codex/guides/agents-md> |
| Antigravity CLI | TODO (issue #25) | (Phase 5 では着手しない) |
| Gemini CLI | 扱わない (終息) | — |

### 重要な発見

#### Claude Code と Codex CLI は共通の "Agent Skills" 標準に乗っている

- 両 agent が <https://agentskills.io> の Agent Skills 標準を実装
- SKILL.md 形式の core 部分 (`name` / `description` + Markdown 本体) は共通
- 主な違い:
  - **配置ディレクトリ**: Claude = `~/.claude/skills/`、Codex = `~/.agents/skills/` または `.agents/skills/` (project)
  - **frontmatter キー**: Claude Code は豊富 (`allowed-tools` / `disable-model-invocation` / `paths` / 等)、Codex CLI は `name` + `description` 必須でその他は要 probe
  - **dynamic context injection**: Claude Code は `` !`<command>` `` syntax で実行時 shell 注入対応、Codex CLI は progressive disclosure モデルで異なる仕組み

これは Phase 5 中間表現の効率に直接効く: **SKILL.md の core body は両 agent 共通で再利用可能**、agent 別の変換は配置先 + frontmatter キー差分のみ。

#### AGENTS.md は Codex CLI 固有、Phase 5 main 経路は SKILL.md

- AGENTS.md は Codex CLI の「instruction chain」素材 (`~/.codex/AGENTS.md` / project root 階層 merge)
- frontmatter なし、素の Markdown、`project_doc_max_bytes` (32 KiB) で打ち切り
- Phase 5 main 経路は **`~/.agents/skills/qgb/SKILL.md`** (Agent Skills 標準準拠、Claude Code と並行)
- AGENTS.md は補助、Phase 5 で生成しないがデフォルト判断 (Phase 6+ で利用者要望があれば追加)

#### Hook 機構は両 agent でほぼ並行

- 種類 / matcher / lifecycle events / merge ルールが Claude Code と Codex CLI でほぼ同型
- 設定 file 場所だけ違う (Claude = `settings.json`、Codex = `~/.codex/hooks.json` / `config.toml [hooks]`)
- Phase 5 v4 判断: **両 agent 向け hook テンプレを提供**、ただし dogfood は案 ii (Claude 深 / Codex smoke のみ)

### qgb 向け設計判断 (Step 5.a-0 で確定)

#### Skill 配置と命名

- Claude Code: `~/.claude/skills/qgb/SKILL.md` (main 経路、利用者は Project `.claude/skills/qgb/` も可)
- Codex CLI: `~/.agents/skills/qgb/SKILL.md` (main 経路、Project `.agents/skills/qgb/` も可)
- 命令名: `/qgb` (両 agent で共通、ディレクトリ名 `qgb` から自動)

#### Frontmatter 共通文言

両 agent で共通の `description` を使う想定:

```
qgb (quality-gate-builder) を使って任意のプロジェクトに証跡ゲート
(REQ → contract → 機械検査 → ALLOW/DENY) を構築するスキル。
利用者から「qgb 入れて」「REQ 追加」「契約段階の設計」「ALLOW 判定して」
等を依頼されたとき自動起動する。
```

Claude Code 専用の追加キー (`allowed-tools` / `disable-model-invocation`) は Claude 生成時のみ付与、Codex 生成時は省く。

#### Hook テンプレ

- `skills/source/hooks/claude-code/settings.example.json`: `UserPromptSubmit` で qgb 関連語に match → `additionalContext` で skill 起動を促す
- `skills/source/hooks/codex/hooks.example.json`: 同様の構造、Codex CLI の hook.json 形式

両方とも acceptance: opt-in / dry-run / validate / 非破壊 (prejournal v4 §3.5)。

## Step 5.a-0 の成果物 (commit 範囲)

| ファイル | 内容 |
|---|---|
| `development/docs/skill-converter/README.md` | converter design journal の責務 + 保守原則 + compatibility matrix |
| `development/docs/skill-converter/agent-claude.md` | Claude Code 仕様メモ (front matter `status: supported`) |
| `development/docs/skill-converter/agent-codex.md` | Codex CLI 仕様メモ (front matter `status: supported`、`known_gaps` で要 probe 項目記録) |
| `development/docs/skill-converter/acceptance-matrix.md` | 成果物 acceptance matrix (4 cell × 9 観点) |
| `development/docs/skill-converter/transitions/` | 空 dir (将来の agent 終息 / 後継対応時に追加) |
| GitHub issue [#25](https://github.com/Yumeno/Quality-gate-builder/issues/25) | Antigravity CLI TODO 記録 |
| `development/docs/journal/phase5-step5-a-0.md` | 本ファイル (完結ジャーナル) |

## レビュー / K=2

本 Step は **調査 + 文書化中心** で、コード変更も spec の構造変更もなし。Phase 3 Step 3.2 で確立した「small だから省略禁止」を踏まえつつ、本 Step の性質 (Web 調査 + journal 起草) を考慮し、以下の運用とする:

- 段 1 観点別並列レビュー: **省略可** (本 Step はコード変更なし、journal 起草のみ)
- 段 3 Codex 横断レビュー: **5.a-1 着手前に 1 回**、5.a-0 全 4 ファイル + Antigravity issue を context として Codex に確認 (新規 finding なければ進む)

5.a-0 単独の K=2 ではなく、5.a (5.a-0 + 5.a-1 + 5.a-2) 全体の完結時に K=2 を取る運用 (Step 3.x 単位の K=2 と同型)。

## 次の Step 申し送り

### 5.a-1 (`metadata.yaml` 薄い構造 + `metadata.schema.json` + minimal `skills/source/` tree)

5.a-0 の成果物を前提に:

- `skills/source/metadata.yaml` で `target_agents: [claude, codex]` 確定
- `skills/source/metadata.schema.json` で 7 必須キー (`skill_id` / `version` / `description` / `converter_min_version` / `source_files` / `build_modes` / `target_agents`) を型固定
- `skills/source/` 配下に空ファイル (`body.md` 等) を minimal で作り、schema 検証だけ通る状態
- `tools/build_skill.py` で「yaml `target_agents` の各 agent について journal `agent-{name}.md` の front matter `status: supported` を検証」のロジック設計 (実装は 5.b)

### 5.a-2 (full モードで body.md + helper 本実装)

- `agent-claude.md` / `agent-codex.md` の知見を踏まえて body.md を full モードで起草
- `body.md` 内に split 用 include marker (例: `<!-- split:helper_start workflow.md -->`) を仕込む
- 完成後 token 数計測 → split 切り出し判断 (user 介入)
- 切り出す場合は 5.a-2 内で split モード本実装

### Codex CLI の要 probe 項目 (5.b で確認)

`agent-codex.md` の `known_gaps`:

- SKILL.md frontmatter キーの全網羅 (`name` / `description` 以外で qgb が使いたいキーがあるか)
- dynamic context injection (Claude Code の `!command` 相当) の有無
- AGENTS.md と Skills の優先関係 (両方ある場合)

5.b で実際に Codex CLI 向け SKILL.md を書いてローカル動作確認するときに同時に検証。判明次第 `agent-codex.md` 更新。

## 関連ファイル

- prejournal v4: `development/docs/journal/phase5-prejournal.md` (commit `9fb089b`)
- converter design journal: `development/docs/skill-converter/`
- Antigravity TODO issue: <https://github.com/Yumeno/Quality-gate-builder/issues/25>
