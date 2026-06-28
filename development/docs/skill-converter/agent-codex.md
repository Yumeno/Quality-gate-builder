---
agent: codex-cli
status: supported
last_verified: 2026-06-27
official_docs_url: https://developers.openai.com/codex
hook_support: codex_hooks_json
known_gaps:
  - SKILL.md frontmatter キーの全網羅は未確認 (name/description 必須までは確認、その他は要 probe)
  - dynamic context injection (Claude Code の `!command` 相当) の有無不明
  - AGENTS.md と Skills の優先関係 (両方ある場合) 未確認
supported_outputs:
  - SKILL.md
  - helper_files_in_skill_dir
  - AGENTS.md (補助、Codex CLI 固有経路)
---

# Codex CLI 対応メモ

Phase 5 で qgb の skill を Codex CLI 向けに生成するときの現行仕様理解と変換判断。

## Skills 機構の基本

Codex CLI も Agent Skills 標準 (<https://agentskills.io>) に準拠しており、`SKILL.md` 形式は Claude Code と core 部分は共通。

### 配置場所

| Location | Path | Applies to |
|---|---|---|
| User | `~/.agents/skills/<skill-name>/SKILL.md` | All projects (個人ユーザー共通) |
| Project | `.agents/skills/<skill-name>/SKILL.md` | Working dir から上位の repo root まで discovered |
| Admin | `/etc/codex/skills/<skill-name>/SKILL.md` | System-wide |
| System | Codex 組み込み | Bundled |

qgb スキルの想定: **User** が main 経路 (`~/.agents/skills/qgb/SKILL.md` + helper files)。Project 経路 (`.agents/skills/qgb/`) も対応可。

Claude Code との違い: パスが `~/.claude/skills/` vs `~/.agents/skills/`。これは agent 中立化のため Codex CLI が `.agents/` を採用した模様 (Agent Skills 標準の推奨ディレクトリと推測)。

### Skill ディレクトリ構造

```
<skill-name>/
├── SKILL.md (必須、progressive disclosure 用 description あり)
├── scripts/             # 任意
├── references/          # 任意
├── assets/              # 任意
└── agents/openai.yaml   # 任意、Codex 固有設定
```

`agents/openai.yaml` の存在は Codex CLI 独自。Claude Code には対応物なし。Phase 5 では当面これを使わず、必要が出たら拡張。

## Frontmatter (要 probe)

確認できた範囲:

- **必須**: `name` + `description`
- **その他のキー**: 公式 docs 完全網羅は未取得 (`allowed-tools` / `disable-model-invocation` 相当があるか不明)

進め方の提案: 5.b 実装段階で Codex CLI の skill を実際に書いて挙動を確認する (smoke 範囲)。判明次第本ファイルを更新。

## Progressive Disclosure

Claude Code との大きな違い: Codex CLI は「**progressive disclosure**」モデル。

- 初期段階: skill の **description だけ** が提示される
- 起動時 (`/skills` コマンドや user の暗黙的 match): **完全な SKILL.md** が読み込まれる

これは Claude Code の `disable-model-invocation` 制御と機能的には類似 (full skill 内容は invoke 時に load)、ただし default 挙動が違う可能性あり。

## 起動方法

- **明示**: `/skills` コマンドまたは `$` で直接指定 (Codex CLI 固有の syntax)
- **暗黙**: user prompt が `description` に match で自動選択

qgb の場合: `/qgb` 起動 + 自動起動 (user が「qgb 入れて」「REQ 追加」等を言ったとき)。

## qgb 向け SKILL.md 設計案

```yaml
---
name: qgb
description: |
  qgb (quality-gate-builder) を使って任意のプロジェクトに証跡ゲート
  (REQ → contract → 機械検査 → ALLOW/DENY) を構築するスキル。
  利用者から「qgb 入れて」「REQ 追加」「契約段階の設計」「ALLOW 判定して」
  等を依頼されたとき自動起動する。
---
```

`description` は Claude Code 版と共通文言で OK (Agent Skills 標準ベースなので)。`allowed-tools` 相当が Codex CLI で使えるかは 5.b で確認。

## AGENTS.md (Codex CLI 固有、補助経路)

### 仕様

- 配置: `~/.codex/AGENTS.md` (user) / project root から cwd までの各階層 / `.override.md` で上書き可
- 構造: **frontmatter なし**、素の Markdown
- 役割: 「Codex builds an instruction chain when it starts (once per run)」= セッション開始時の instruction 素材
- merge: root → cwd 順に結合、下層が上層を上書き、`project_doc_max_bytes` (default 32 KiB) で打ち切り

### qgb での使い道

qgb skill の **代替経路**として、利用者プロジェクトに `AGENTS.md` を置きたいケースがあれば使う:

- 利用者プロジェクトが Codex CLI 中心で `.agents/skills/qgb/` を使わない場合
- 利用者プロジェクトの project root に「Codex がこのプロジェクトで qgb を使うべき context」を直接書きたい場合

**ただし Phase 5 main 経路は SKILL.md** (Agent Skills 標準で wide 適用可能、Claude Code とも共通)。AGENTS.md は補助、Phase 5 で生成するかは下記判断:

### AGENTS.md を Phase 5 で生成するかの判断

- **生成しない案**: main 経路 SKILL.md で十分、利用者は `~/.agents/skills/qgb/` か `.agents/skills/qgb/` に入れる。AGENTS.md は利用者が必要に応じて手で書く
- **生成する案**: `body.md` (および split build 用に converter が body.md include marker から機械生成する `workflow.md` / `references.md`、A1' 構造) を連結した AGENTS.md を `dist/skills/{full,split}/codex/AGENTS.md` として用意、利用者の選択肢を増やす

**Phase 5 v4 では「生成しない」がデフォルト判断**。Codex CLI 向け main 経路は SKILL.md、AGENTS.md は Phase 6+ で利用者要望があれば追加 (issue 起票で対応)。

## Hook 機構 (Phase 5 trigger 戦略 (γ) 用)

Codex CLI も hook 機構を持つ。Claude Code とほぼ並行。

### 設定場所

- `~/.codex/hooks.json` (user)
- `~/.codex/config.toml` の `[hooks]` table (inline)
- `<repo>/.codex/hooks.json` (project)
- Plugin manifest 同梱

### Lifecycle events (主要)

Claude Code と同型:

- `SessionStart` / `SubagentStart` / `SubagentStop` / `Stop`
- `PreToolUse` / `PostToolUse` / `PermissionRequest`
- `PreCompact` / `PostCompact`
- `UserPromptSubmit`

### Matcher (per event)

正規表現 / tool 名 / source (startup/resume/clear/compact) で filter。Claude Code とほぼ同型。

### Merge ルール

複数 source から merge (replace でなく)。各 layer ごとに `hooks.json` か inline `[hooks]` の片方推奨 (両方は warn)。

### qgb skill が提供する hook テンプレ (Phase 5 Step 5.a-2-3 で実装済)

Step 5.a-2-3 (commit `a7234e6`) + K=2 r1 fix #3 で実装した実装形:

- `skills/source/hooks/codex/hooks.example.json` — `UserPromptSubmit` event を登録、command は PowerShell script を起動
- `skills/source/hooks/codex/scripts/check-relevance.ps1` — Windows native PowerShell (5/7 両対応)、pure ASCII + Unicode escape で JP keyword を構築 (PowerShell 5 の BOM なし `.ps1` 日本語 cp932 誤読を回避)
- `skills/source/hooks/codex/README.md` — opt-in / dry-run / validate / 非破壊 の 4 原則 + 利用者手順

### Codex CLI hook 機構の確定知見 (K=2 r1 で明示化)

#### `UserPromptSubmit` の `matcher` フィールドは silently 無視される

K=2 r1 横断レビュー (2026-06-28) で確定:

- `hooks.UserPromptSubmit[].matcher` を書いても **prompt 本文での filtering にはならない** (Claude Code も同様)
- 公式 docs: https://developers.openai.com/codex (UserPromptSubmit hook の matcher は ignored)
- 対策: **script 内側で stdin JSON の `.prompt` を正規表現判定** (`scripts/check-relevance.ps1` で実装、非 match → exit 0 + stdout 空、match → plain text nudge)
- `hooks.example.json` の hook 階層に `matcher` フィールドは **意図的に書かない** (silently ignored を見せかけ非破壊にしない)

#### hook 設定の validate 経路

Codex CLI の `/hooks` コマンドで以下が確認可能 (K=2 r1 で確定):

- 登録された hook の一覧 (event 名 / command path)
- source (どの config layer に書かれているか、`~/.codex/hooks.json` / inline `[hooks]` / repo-local 等)
- trust (利用者が hook 実行を許可済みか、Codex は初回起動時に prompt するため利用者意思確認の証跡)
- enabled / disabled state

利用者は merge 後に `/hooks` で source path / trust 状態を確認する (README.md に明文化済)。

### Claude Code 同型の規律

opt-in / dry-run / validate / 非破壊 規律を適用。詳細は `skills/source/hooks/codex/README.md` 参照。

## 知見の変化点記録

(将来の仕様変更時に追記)

- 2026-06-27: 初回 verify (Phase 5 Step 5.a-0)。SKILL.md frontmatter 完全網羅と dynamic context injection 有無は未確認、5.b で実機検証する想定
- 2026-06-28: hook 実装完了 (Step 5.a-2-3 commit `a7234e6`、K=2 r1 fix #3 で PowerShell script + matcher 非対応対策を反映)。`UserPromptSubmit` matcher silently ignored / stdin filtering / `/hooks` trust review の運用知見を追加
