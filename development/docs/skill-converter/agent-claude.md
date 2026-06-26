---
agent: claude-code
status: supported
last_verified: 2026-06-27
official_docs_url: https://code.claude.com/docs/en/skills
hook_support: settings_json_hook
known_gaps: []
supported_outputs:
  - SKILL.md
  - helper_files_in_skill_dir
---

# Claude Code 対応メモ

Phase 5 で qgb の skill を Claude Code 向けに生成するときの現行仕様理解と変換判断。

## Skill ファイルの基本

### 配置場所

| Location | Path | Applies to |
|---|---|---|
| Personal | `~/.claude/skills/<skill-name>/SKILL.md` | All projects (個人ユーザー全プロジェクト共通) |
| Project | `.claude/skills/<skill-name>/SKILL.md` | This project only |
| Plugin | `<plugin>/skills/<skill-name>/SKILL.md` | Where plugin is enabled |
| Enterprise | Managed settings 経由 | All users in organization |

qgb スキルの想定: **Personal** が main 経路 (`~/.claude/skills/qgb/SKILL.md` + helper files)。利用者プロジェクトに置きたい場合は Project 経路 (`.claude/skills/qgb/`) も可。

### Skill ディレクトリ構造

```
<skill-name>/
├── SKILL.md           # 必須、frontmatter + 本体
├── helper1.md         # 任意、本体から参照
├── helper2.md         # 任意
├── scripts/           # 任意、Claude が実行できる
│   └── validate.sh
└── examples/          # 任意
    └── sample.md
```

qgb の場合: SKILL.md + workflow.md + references.md + prompts/design-stages.md + prompts/review-policy.md (split モード時)、full モード時は SKILL.md 単独。

### Command 名の決まり方

ディレクトリ名がコマンド名になる。`~/.claude/skills/qgb/SKILL.md` → `/qgb` で起動。frontmatter `name` は表示名のみ (コマンド名には影響しない、plugin-root SKILL.md を除く)。

## Frontmatter Reference

`---` で囲まれた YAML frontmatter で skill 挙動を制御。全フィールド optional だが、`description` が推奨 (Claude が自動起動判断に使う)。

### 必須/推奨

| Field | Required | Description |
|---|---|---|
| `name` | No | 表示名。default = ディレクトリ名 |
| `description` | **Recommended** | スキルの目的 + いつ使うか。Claude が自動起動判断に使う、最大 1536 文字 (`description` + `when_to_use` 合算) |

### 起動制御

| Field | Default | Description |
|---|---|---|
| `disable-model-invocation` | `false` | `true` で Claude 自動起動を無効化、user の `/qgb` 起動のみ |
| `user-invocable` | `true` | `false` で `/` メニューから隠す (background knowledge 用、Claude のみ起動可) |
| `when_to_use` | — | description への追加情報、trigger phrase 等 |
| `paths` | — | glob で skill が active になるファイル限定 (例: `**/*.py`) |
| `argument-hint` | — | autocomplete のヒント (例: `[issue-number]`) |
| `arguments` | — | 名前付き positional 引数、`$name` で参照 |

### 権限制御

| Field | Default | Description |
|---|---|---|
| `allowed-tools` | — | Skill active 中、permission 要求なしで使える tools (例: `Bash(git *) Read Grep`) |
| `disallowed-tools` | — | Skill active 中、使用禁止 tools (active な subagent / background skill 向け) |

### 実行環境制御

| Field | Default | Description |
|---|---|---|
| `model` | inherit | Skill active 中の model 上書き |
| `effort` | inherit | `low` / `medium` / `high` / `xhigh` / `max` |
| `context` | — | `fork` で forked subagent context で実行 |
| `agent` | `general-purpose` | `context: fork` 時の subagent 種別 (`Explore` / `Plan` / 等) |
| `shell` | `bash` | `bash` or `powershell`、` `` !`command` `` syntax 用 |
| `hooks` | — | Skill lifecycle スコープの hook |

## qgb 向け frontmatter 設計案

```yaml
---
name: qgb
description: |
  qgb (quality-gate-builder) を使って任意のプロジェクトに証跡ゲート
  (REQ → contract → 機械検査 → ALLOW/DENY) を構築するスキル。
  利用者から「qgb 入れて」「REQ 追加」「契約段階の設計」「ALLOW 判定して」
  等を依頼されたとき自動起動する。
allowed-tools:
  - Read
  - Glob
  - Grep
  - Write
  - Edit
  - Bash(python -m qgb *)
  - Bash(git *)
disable-model-invocation: false
---
```

- `description`: 利用者の依頼語 (qgb 入れて / REQ 追加 / 契約段階 / ALLOW 判定) を含めて Claude が自動起動判断できるように
- `allowed-tools`:
  - `Read` / `Glob` / `Grep` (対象プロジェクト調査、philosophy.md / examples/ 等の参照)
  - `Write` / `Edit` (利用者プロジェクトの `.quality-system/` に書き込み)
  - `Bash(python -m qgb *)` (qgb CLI 呼び出し、`python -m qgb validate-policy` 等)
  - `Bash(git *)` (git 状態確認、commit support)
- `disable-model-invocation: false`: Claude 自動起動も `/qgb` 直接起動も両方 OK (qgb は提案系で副作用が少ない、deploy/commit のように `true` にする必要なし)

## Dynamic Context Injection

`` !`<command>` `` syntax で skill 本文に shell command 結果を埋め込める (preprocessing、Claude が実行するのではない):

```markdown
## Current changes
!`git diff HEAD`
```

qgb での想定使用例:

```markdown
## qgb 本体 version 確認
!`python -m qgb --version`

## 現在の .quality-system/ 構造
!`ls -R .quality-system/ 2>/dev/null || echo '(まだ初期化されていません)'`
```

これにより skill 本文が「現在の状況」を踏まえた状態で Claude に渡る。`disableSkillShellExecution: true` setting で全 skill の `!` 実行を無効化可能 (managed settings で適用される可能性あり、考慮)。

## Skill Content Lifecycle

- skill が起動すると `SKILL.md` 内容が **会話中 1 つのメッセージ** として注入される
- セッション中は持続 (re-read されない、token 食い続ける)
- auto-compaction では最後の skill invocation を 5,000 tokens まで保持、5 skills 累計 25,000 tokens budget

**含意**: skill 本文を大きくしすぎると毎ターン token cost。Phase 5 の build mode (full / split) はこのトレードオフへの直接の解答。

## Hook 機構 (Phase 5 trigger 戦略 (γ) 用)

Claude Code は `settings.json` の `hooks` キーで lifecycle event ごとに hook 設定可:

### Hook 種類

- `command` (shell スクリプト、stdin JSON / stdout JSON / exit codes)
- `http` (HTTP endpoint、POST body JSON / response body JSON)
- `mcp_tool` (MCP server tool)
- `prompt` (LLM 評価、yes/no decision)
- `agent` (subagent verification)

### Lifecycle events (主要)

| Event | 用途 (qgb 向け案) |
|---|---|
| `SessionStart` | qgb 用 hook を session 開始時に initialize |
| `UserPromptSubmit` | 利用者 prompt に「REQ」「契約」「ALLOW」等が含まれる → qgb skill 起動を強制 |
| `PreToolUse` (matcher: `Bash(python -m qgb *)`) | qgb CLI 呼び出し前に project-context 等の準備 |
| `PostToolUse` (matcher: `Bash(python -m qgb *)`) | qgb CLI 結果を解析して context 注入 |
| `Stop` | qgb 関連の終了処理 (現状想定なし) |

### Hook 設定の merge

優先度 (高 → 低): managed > user (`~/.claude/settings.json`) > project (`.claude/settings.json`) > local (`.claude/settings.local.json`) > plugin > skill frontmatter

複数 source から merge (replace でなく)。

### qgb skill が提供する hook テンプレ案

`skills/source/hooks/claude-code/settings.example.json` に:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "matcher": "qgb|REQ-[A-Z]+-\\d+|契約段階|gate.json|ALLOW|DENY|NOT_READY",
        "hooks": [
          {
            "type": "command",
            "command": "echo '{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":\"qgb skill is relevant for this prompt. Load qgb skill if not already loaded.\"}}'"
          }
        ]
      }
    ]
  }
}
```

ただしこの hook は **opt-in** (利用者が install 時に手動で設定 merge)。**dry-run** (utils で hook 効果を確認できる手順を install ガイドに含める)。**validate** (`claude config validate` 相当があれば利用、なければ手動 review)。**非破壊** (既存 `settings.json` と merge、上書きしない、衝突時 warn)。

これは Phase 5 prejournal v4 §3.5 trigger / hook 戦略の (γ) 実装。

## bundled skill との関係

Claude Code には `code-review` / `debug` / `loop` 等の bundled skills がある。qgb は名前衝突を避けるため `qgb` 名前で OK (`code-review` 等と直接衝突しない)。Phase 5 進行中に bundled skills が増えて競合する可能性は注視。

## 知見の変化点記録

(将来の仕様変更時に追記)

- 2026-06-27: 初回 verify (Phase 5 Step 5.a-0)
