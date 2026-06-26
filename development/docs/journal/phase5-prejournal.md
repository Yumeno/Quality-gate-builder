# Phase 5 着手前判断: Skill Creator 化

着手前判断確定: 2026-06-26 (v1)
Codex セカンドオピニオン r1 反映: 2026-06-26 (v2)
user 視点反映 (agent 変化前提 / build mode / trigger ハーネス依存): 2026-06-26 (v3)
**Codex r2 反映 + user 判断 8 件確定 (確定版): 2026-06-27 (v4)**

## v4 改訂サマリ (v3 → v4)

v3 commit (`6e5616d`) を Codex r2 セカンドオピニオンにかけ、code fix 4 件 + spec fix 5 件 + out of scope 維持の評価を受領。並行して user 視点で「二重管理回避」「マルチ対応保証の保守工数」を絞る方針が確定:

### v4 で確定した user 判断 (8 件)

| # | 判断点 | v4 確定 |
|---|---|---|
| 1 | `metadata.yaml` 構造 | **案 C: 薄い build matrix のみ** (agent_bindings 廃止、二重管理回避) |
| 2 | `body.md` 分量 | **full / split 両モード生成** (5.a-2 で full 先行、token 計測後 split 判断) |
| 3 | `design-stages.md` スコープ | オンデマンド + パターン B/C 統合 (章分離)、維持 |
| 4 | dogfooding 順序 | **2 段階 + Claude 主・Codex 軽め** (案 ii、Claude 深 dogfood、Codex は smoke + 利用者目線 1 サイクル) |
| 5 | CI ビルド third-party action | `gh release upload` のみ、維持 |
| 6 | Step 3.3 並走判断 | Phase 5 後 + blocker のみ例外、維持 |
| 7 | trigger / hook 戦略 | (α) body.md trigger + (γ) agent 別 hook 二段、維持 |
| 8 | 対象 agent | **Claude Code + Codex CLI 2 つ supported**、Antigravity CLI は GitHub issue で TODO 記録、Gemini CLI は扱わない |

### Codex r2 で受領した修正 (9 件) の反映

| # | Codex r2 指摘 | v4 反映 |
|---|---|---|
| code fix #1 | yaml 薄すぎ → thin typed manifest | 案 C で `skill_id`/`version`/`description`/`converter_min_version`/`source_files`/`build_modes`/`target_agents` を型固定、`agent_bindings` 廃止 |
| code fix #2 | full/split 二重管理破綻リスク | source block / include marker / manifest から converter が **full と split を単一正本から生成**、golden は `mode × agent` で固定 |
| code fix #3 | hook が trigger 発火を保証は言い過ぎ | hook = opt-in / dry-run / validate 可能 / ユーザー設定を自動破壊しない、を acceptance に明示 |
| code fix #4 | acceptance 粗い | `supported agent × build mode` ごとに生成ファイル一覧 / 構文検証 / install guide / manual smoke / hook 有無を matrix 化 |
| spec fix #1 | agent 状態 4 値分類 | user 判断 8 で **supported = Claude+Codex の 2 つだけ**、Antigravity = TODO (issue)、Gemini = 扱わない、experimental/community/deferred/removed の枠は当面使わない |
| spec fix #2 | journal リッチ化 | 各 `agent-*.md` の front matter に `status` / `last_verified` / `official_docs_url` / `hook_support` / `known_gaps`、`README` に compatibility matrix |
| spec fix #3 | converter Python = 機械正本は危険 | **schema + converter + golden fixtures = 機械正本**、journal = 人間正本 |
| spec fix #4 | 規模下限が楽観的 | 案 C + Y' (Codex/Claude のみ supported + Antigravity TODO) で **baseline 8〜13**、上振れ 16〜20 |
| spec fix #5 | canary が Claude full 優先だけ | supported matrix 全体に軽量 smoke 必須化、深 dogfood は **Claude (full + split)**、Codex は smoke + 利用者目線 1 サイクルのみ (案 ii) |

## 1. 経緯

Phase 1 (Python CLI MVP, 2026-05) / Phase 2 (編集を安全にする, 2026-06-13 完結) / Phase 3 (機械責務側の最終整備, 2026-06-26 完結) を経て、qgb 本体は機械責務側の整備を完了。Phase 4 (CI 連携) は 2026-06-21 廃止。Phase 5 (Skill Creator 化) が次の主軸。

## 2. Phase 5 の理念的位置づけ

### 2.1 何を解決するか

Phase 1〜3 で qgb 本体は完成したが、**「LLM 環境からどう qgb を呼び出すか」** という運用層が未整備。Phase 5 はこれを:

- スキル本体 (qgb の使い方 + philosophy + 段階設計手順 + プロンプト) を **エージェント中立な中間表現** として書く
- コンバータ `tools/build_skill.py` が Claude Code / Codex CLI 向けに機械的に生成
- 利用者は自分の agent 用 1 セットだけを取得して入れる

### 2.2 ライン引きの維持 (Phase 1〜3 で確立した境界の継承)

Phase 5 で **Phase 1〜3 で確立した境界を一切緩めない**:

- **Step 3.0 ライン引き (対象認識)**: スキルは対象を Read で読んで理解する (LLM 責務)、qgb 本体は contract で宣言されたコマンドを実行するだけ (機械責務)
- **Step 3.1 ライン引き (異常時責務分離 + ドメイン依存性)**: スキルは利用者プロジェクトに responsibility 分離を提案するが、リアルタイム制御等の他ドメインには qgb 流を普遍適用しない注意喚起を含める
- **Step 3.2 ライン引き (lock 文化 vs 利用者運用)**: スキルは利用者プロジェクトに `--require-hashes` を**提案**できるが**強制しない**

### 2.3 Phase 5 固有のライン引き

#### Agent 変化前提

Agent CLI は終息・後継が頻繁に起きるドメイン (例: Gemini CLI 終息 / Antigravity CLI 登場、Phase 5 着手期前後の実例)。Phase 5 では:

- 対応 agent は **「現時点での仕様スナップショット」** に基づき、永続適合は保証しない
- 変換ロジックは Python (`tools/build_skill.py`) と golden fixtures に固定、設計判断は converter design journal
- 新 agent (Antigravity 等) 対応は **GitHub issue で TODO 化**、実需が出てから着手

#### 対応範囲の絞り込み (user 判断、Phase 3 ドメイン依存性同型)

qgb メンテナの保守工数は (Claude Code 深 dogfood) + (Codex CLI 軽 smoke + 利用者目線 1 サイクル) に圧縮:

- **Claude Code = supported (主環境)**: 中間表現変換 + 深 dogfood (canary + 利用者目線)
- **Codex CLI = supported (副環境)**: 中間表現変換 + smoke + 利用者目線 1 サイクル
- **Antigravity CLI = TODO**: GitHub issue で記録、Phase 5 では着手しない
- **Gemini CLI = 扱わない**: 終息品

この絞り込みは Phase 3 Step 3.1 で確立した「異常時責務分離はドメイン依存」と同じ姿勢 (qgb が責任を持つ範囲を明確に絞る)、philosophy P11 (ALLOW の比較不可能性) と整合。

### 2.4 二重管理の回避 (user 判断、v3 → v4 で再点検)

v3 で構想した「yaml の `agent_bindings` と journal `agent-*.md`」は **二重管理リスク** (user 指摘「片方から片方が機械生成ならいいけど」)。v4 で:

- yaml は **build matrix の宣言のみ** (`target_agents`, `build_modes`, `source_files` 等)
- agent 状態 (status / last_verified / hook_support) は **journal `agent-*.md` の front matter で 1 か所だけ**管理
- build_skill.py が実行時に journal front matter を読み、yaml `target_agents` との整合を機械検証

これにより agent 状態の正本は journal、yaml は build matrix の宣言という責務分離が成立。

### 2.5 機械正本 / 人間正本の二層 (Codex r2 spec fix #3 反映)

Phase 5 では:

- **機械正本**: `schema + converter (build_skill.py) + golden fixtures`
  - schema (`metadata.schema.json`) が中間表現の構造を型固定
  - converter が schema 準拠の中間表現から決定論的に生成物を作る
  - golden fixtures が「同じ入力なら同じ出力」を CI で機械検証
- **人間正本**: converter design journal (`development/docs/skill-converter/`)
  - 各 agent 仕様の理解、過去の変換判断、変化追跡
  - schema や converter コードだけでは語れない「なぜそう変換するか」を残す

これは Phase 3 Step 3.0 の `project-context.{md, json}` (md = 人間正本、json = 機械正本) と同型のパターン。

### 2.6 Phase 6 以降との関係

Phase 5 完結後、qgb は「フレームワーク + LLM 向けスキル (Claude Code / Codex CLI)」のセット配布物となる。Phase 6 以降は実需に応じて Step 3.3 残務 / 新 verification_type / Antigravity 対応 (TODO issue から起こす)。

## 3. Phase 5 スコープ

### 3.1 中核: F-019 エージェント中立スキル提供 (v4 確定構造)

```text
skills/source/                      # 中間表現 (正本)
  metadata.yaml                     # v4: 薄い build matrix 宣言のみ
  metadata.schema.json              # JSON Schema (build matrix の型固定)
  body.md                           # スキル本体 (full モード正本、split は include marker で切り出し)
  workflow.md                       # 作業手順 (.quality-system/ を作るまで)
  references.md                     # philosophy / stage-design 等への参照集
  prompts/
    design-stages.md                # 段階設計プロンプト (パターン B/C 統合、章分離)
    review-policy.md                # レビュー観点プロンプト
  hooks/                            # agent 別 install option
    claude-code/
      settings.example.json         # Claude Code 用 settings.json hook テンプレ
    codex/                          # Codex CLI 用 hook 設定 (5.a-0 で確認可否を判断)

tools/build_skill.py                # コンバータ (変換ロジックの正本)
tools/_golden/                      # 決定的ビルドの fixture (mode × agent ごと)
  claude/full/...
  claude/split/...
  codex/full/...
  codex/split/...

development/docs/skill-converter/   # converter design journal (人間正本)
  README.md                         # converter 責務 + 保守原則 + compatibility matrix
  agent-claude.md                   # Claude Code 仕様 (front matter で status 等)
  agent-codex.md                    # Codex CLI 仕様 (同上)
  transitions/                      # agent 終息 / 後継対応の履歴 (該当時のみ)

dist/skills/                        # ビルド成果物 (.gitignore、CI で生成)
  full/   claude/ codex/            # 全部盛り
  split/  claude/ codex/            # 補助分割
```

### 3.2 対象エージェント (v4 確定、user 判断 8)

| エージェント | 状態 | 5.a-0 probe 必須項目 | Phase 5 dogfood レベル |
|---|---|---|---|
| Claude Code | **supported (主)** | SKILL.md frontmatter / settings.json hook / 配置先 | canary (full) + 利用者目線 (full + split) |
| Codex CLI | **supported (副)** | AGENTS.md 構造 / hook 可否 / 配置先 | smoke (全 mode) + 利用者目線 1 サイクル |
| Antigravity CLI | **TODO (issue)** | — | (Phase 5 では着手しない) |
| Gemini CLI | (扱わない) | — | — |

Antigravity は GitHub issue (`[Phase 6+] Antigravity CLI 向け skill build 対応`) として記録。Phase 5 中に仕様が安定し公式 docs が整備されたら issue 内で再判断、ただし Phase 5 規模 確定後の再判断は user 介入必須。

### 3.3 metadata.yaml 構造 (v4 確定、案 C)

```yaml
# skills/source/metadata.yaml (例)
skill_id: quality-gate-builder
version: 0.1.0
description: 任意のプロジェクトに証跡ゲートを構築する
converter_min_version: 0.1.0

source_files:
  - body.md
  - workflow.md
  - references.md
  - prompts/design-stages.md
  - prompts/review-policy.md

build_modes: [full, split]
target_agents: [claude, codex]
```

- `skill_id` / `version` / `description` / `converter_min_version` / `source_files` / `build_modes` / `target_agents` を schema で型固定 (Codex r2 code fix #1)
- `agent_bindings` 廃止 (user 判断 1、二重管理回避)
- build_skill.py 実行時に `target_agents` の各 agent について journal `agent-{name}.md` の front matter `status` を読み、`status` が `supported` でなければ error (機械検証で整合保証)

### 3.4 build mode (v4 確定、案 ii)

利用者の context 予算 / 用途に応じて 2 モードを生成:

| モード | `entry_body` (body.md) | `helper_files` | LLM context 量 | 用途 |
|---|---|---|---|---|
| **full** | philosophy / stage-design / examples / trigger 表 すべて埋め込み (大盛り) | 空 (補助ファイルなし) | 大 (推定 4-6 KB / 2-3 千語) | 初心者、頻度低、token cost 許容 |
| **split** | 骨子 (500-1000 語) + trigger 表 | workflow.md / references.md / prompts/ 等別ファイル | 小 (推定 1-2 KB) | 熟練者、高頻度呼び出し、cost 重視 |

**正本は full、split は include marker で生成** (Codex r2 code fix #2):

- `body.md` の中に `<!-- split:helper_start workflow.md -->` ... `<!-- split:helper_end -->` のような marker を埋め込む
- converter が full モード生成時はマーカーを無視して本文ごと埋め込み、split モード生成時はマーカー部分を切り出して helper file へ移動 + body.md には trigger 行だけ残す
- 二重管理 (full と split を別 md ファイルで保守) を構造的に回避

5.a-2 で full モードで body.md を書きながら marker を仕込む → 5.b で converter が両モード生成。

### 3.5 trigger / hook 戦略 (v4 確定、user 判断 7)

| 層 | 内容 | 対応 agent |
|---|---|---|
| **(α) body.md 内 trigger 表** | LLM 指示遵守に依存、文書としての trigger | Claude / Codex 両方 (minimum 保証) |
| **(γ) agent 別 hook** | harness レベル機構で trigger 発火を補強 | Claude Code (settings.json hook 確実)、Codex は 5.a-0 で可否確認 |

hook acceptance (Codex r2 code fix #3 反映):

- **opt-in**: 利用者が明示的に install option として選ぶ
- **dry-run**: hook を有効化する前に「何が起こるか」を確認できる
- **validate 可能**: hook 設定が壊れていないことを確認するコマンドを提供
- **ユーザー設定を自動破壊しない**: 既存 `settings.json` 等を上書きでなくマージ、衝突時は warn

(γ) の実装は agent ごとに違うので install option として提供、install ガイドで「Claude Code は hook 自動設定可、Codex は仕様確認後に判断」と説明。

### 3.6 acceptance matrix (v4 新規、Codex r2 code fix #4)

`supported agent × build mode` で各成果物の acceptance を機械化:

| 観点 | Claude / full | Claude / split | Codex / full | Codex / split |
|---|---|---|---|---|
| 生成ファイル一覧 | SKILL.md + helpers | SKILL.md + helpers | AGENTS.md | AGENTS.md |
| 構文検証 | YAML frontmatter parse | YAML frontmatter parse | Markdown only | Markdown only |
| install guide 存在 | ✓ | ✓ | ✓ | ✓ |
| manual smoke | ✓ (深 dogfood 含む) | ✓ (深 dogfood 含む) | ✓ (smoke のみ) | ✓ (smoke のみ) |
| hook 提供 | settings.example.json | settings.example.json | 5.a-0 後判断 | 5.a-0 後判断 |
| golden fixture | ✓ | ✓ | ✓ | ✓ |

各 row は CI 機械検証 + manual smoke で確認。深 dogfood は Claude のみ (案 ii)。

### 3.7 converter design journal 構造 (v4 確定、Codex r2 spec fix #2)

```
development/docs/skill-converter/
  README.md                # converter 責務 + 保守原則 + compatibility matrix
  agent-claude.md          # Claude Code 仕様メモ
  agent-codex.md           # Codex CLI 仕様メモ
  transitions/             # agent 終息 / 後継対応の履歴 (該当時のみ)
```

各 `agent-*.md` の front matter:

```yaml
---
agent: claude-code
status: supported           # supported / experimental / deferred / removed (当面は supported のみ使用)
last_verified: 2026-06-27
official_docs_url: https://docs.claude.com/...
hook_support: settings_json_hook  # or none / config_toml / etc
known_gaps: []              # 未対応 / 仕様未確認の項目
supported_outputs:          # この agent 向けに何を生成するか
  - SKILL.md
  - helper_files
---

# Claude Code 対応メモ

(本文: 仕様の理解、過去の変換判断、変化追跡)
```

build_skill.py が `target_agents` の各 agent について front matter を読み、`status: supported` でなければ error。yaml `target_agents` と journal `status` の整合性を機械検証することで、二重管理ではなく **片方 (journal) を正本、もう片方 (yaml) を集合宣言** とする責務分離を実現。

`README.md` には現在の compatibility matrix:

| agent | status | last_verified | full mode | split mode | hook |
|---|---|---|---|---|---|
| Claude Code | supported | 2026-06-27 | ✓ | ✓ | settings.json |
| Codex CLI | supported | 2026-06-27 | ✓ | ✓ | TBD |

(matrix は 5.a-0 で初期値を埋める)

### 3.8 スコープ内 (Phase 5 で必ずやる)

- 中間表現 (`skills/source/`) の本実装 (v4 構造に従って各ファイルを埋める)
- `metadata.yaml` 薄い build matrix + `metadata.schema.json` (JSON Schema)
- `tools/build_skill.py` 実装 (決定的ビルド契約 + full/split を単一正本から生成 + golden fixture mode×agent)
- agent 別 hook テンプレ (`skills/source/hooks/`) と install ガイドへの組み込み + hook acceptance (opt-in / dry-run / validate)
- converter design journal (`development/docs/skill-converter/`) で Claude / Codex 仕様 + 変化対応履歴を記録
- CI build check (5.b 直後、`dist/` を生成 + golden fixture と diff)
- Claude / Codex 向け運用ガイド (インストール / 更新 / トラブルシューティング)
- canary dogfooding (5.b 後、Claude full) + 利用者目線 dogfooding (5.d 後、Claude full+split 深、Codex full+split 軽)
- CI からの GitHub Releases 添付 (dogfooding 完了後、`gh release upload`、third-party action 不要)
- **Antigravity CLI 対応 GitHub issue 起票** (Phase 5 着手前または 5.a-0 中、Phase 6+ TODO として記録)

### 3.9 スコープ内 (任意)

- 利用者プロジェクト向け CI テンプレ生成機能 (旧 Phase 4 吸収、5.g): optional
- 言語非依存ドメインの examples 追加 (5.h): 実需待ち

### 3.10 スコープ外 (Phase 5 でやらない)

- Phase 2 繰越実需回収 (Step 3.3): blocker のみ例外
- AI Agent 評価フレームワーク: P6 と緊張。ただし dogfooding checklist + 人間 review rubric は Phase 5 内で作る
- 新 verification_type 追加: 実需が出てから判断
- adapter 復活: Phase 3 Step 3.0 で撤回した方針を維持
- SBOM 自動生成 / vuln scan: Phase 3 Step 3.2 で整理済
- **agent 仕様への永続適合保証**: agent 終息 / 後継は構造的に起きるため、Phase 5 で「全 agent 永続対応」は約束しない
- **Antigravity CLI 対応**: GitHub issue で TODO 記録のみ、Phase 5 では着手しない
- **Gemini CLI 対応**: 終息品、扱わない
- **3 件目以降の agent (experimental / community)**: 公式 docs 未確認 agent への本対応は out of scope (stub + journal + deferred ではなく、TODO issue 化)

## 4. サブステップ構成 (v4 確定)

v3 の 12 サブステップを v4 視点で更新 (Antigravity 削除で軽量化、案 ii で Codex の dogfood 工数を削減):

| Step | 内容 | 規模 | 自走可否 |
|---|---|---|---|
| **5.a-0** | Agent contract probe (Claude / Codex 仕様確認 + Antigravity 仕様調査の上限) + Antigravity TODO issue 起票 + 成果物 acceptance matrix 固定 + converter design journal 雛形作成 (front matter スキーマ確定 + initial agent-*.md) | 1.0〜1.5 | 自走 (調査 + issue 起票) |
| **5.a-1** | `metadata.yaml` 薄い build matrix + `metadata.schema.json` (JSON Schema) + minimal `skills/source/` tree + journal front matter と yaml `target_agents` の整合検証ロジック設計 | 0.5〜1.0 | 自走 |
| **5.a-2** | full モードで `body.md` / `workflow.md` / `references.md` / `prompts/` 本実装 + split 用 include marker 仕込み + token 計測 + user に提示 → split 切り出し判断 + (必要なら) split モード本実装 | 2.0〜3.0 | 部分自走 (split 切り出し判断点) |
| **5.b** | `tools/build_skill.py` 実装 (決定的ビルド契約 + include marker → full/split 単一正本生成 + agent × mode で 4 出力 + journal front matter 整合検証) + golden fixture (`tools/_golden/`) + converter design journal 本文記述 + ローカル build 検証 | 2.0〜3.0 | 自走 (5.a 確定後) |
| **5.b-ci** | CI に build check job 追加 (Phase 3 Step 3.1/3.2 規律踏襲、golden fixture と diff) | 0.3〜0.5 | 自走 |
| **5.d-canary** | canary dogfooding (Claude Code で `dist/skills/full/claude/SKILL.md` を読ませて軽い改善 1 件、例: docstring 1 つ追加) | 0.3〜0.7 | 部分自走 |
| **5.d** | Claude / Codex 向け運用ガイド + hook install option ガイド (acceptance matrix 反映) + dogfooding checklist + 人間 review rubric | 0.5〜1.0 | 自走 |
| **5.e** | 利用者目線 dogfooding: Claude (full + split 両方 1 サイクル深、qgb 本体への新 contract 追加等)、Codex (full + split smoke + 利用者目線 1 サイクル軽) + 補修 | 0.7〜1.5 | 部分自走 |
| **5.c** | CI からの GitHub Releases 添付自動化 (`gh release upload`、third-party action 不要) | 0.3〜0.5 | 自走 |
| **5.f** | 完結ドキュメント + journal + memory (Phase 3 Step 3.1/3.2 同型) | 0.5〜1.0 | 自走 |
| 任意 5.g | 利用者プロジェクト向け CI テンプレ生成 (旧 Phase 4 吸収) | 0.5〜1.0 | スコープ判断点 |
| 任意 5.h | 言語非依存 examples 追加 | 0.3〜0.8 | 実需待ち |

**合計規模見積もり**: **8.0〜13.0** (v3 8.5〜15.0 から下方修正、案 ii で Codex 深 dogfood 削減 + Antigravity 削除分)
**上振れリスク線**: **16〜20** (Codex r2 spec fix #4 推奨と整合)

### 4.1 v3 → v4 規模変化の説明

| 要素 | v3 規模 | v4 規模 | 差分 |
|---|---|---|---|
| 5.a-0 | 1.0〜1.5 | 1.0〜1.5 | 維持 (Antigravity probe は上限あり、結果が「TODO」なら 5.a-0 内で終わる) |
| 5.a-2 | 2.0〜3.5 | 2.0〜3.0 | 微減 (Antigravity 不要分) |
| 5.b | 2.5〜4.0 | 2.0〜3.0 | 削減 (2 agent × 2 mode = 4 output、Antigravity 不要分) |
| 5.d-canary | 0.5〜1.5 | 0.3〜0.7 | 削減 (Claude full のみ、Codex は smoke は別 step) |
| 5.e | 0.5〜1.5 | 0.7〜1.5 | 微増 (Codex 利用者目線 1 サイクル追加分、Claude split 追加分) |
| その他 | — | — | 維持 |

### 4.2 5.a-0 の重要性

v4 でも 5.a-0 は **Phase 5 全体の前提確定 step**:

- 対象 agent の仕様確認 (Claude SKILL.md / Codex AGENTS.md の現行仕様)
- Antigravity の仕様調査 (上限あり、未整備なら 5.a-0 内で TODO issue 起票)
- 成果物 acceptance matrix の固定
- converter design journal の雛形 (front matter スキーマ確定 + initial agent-claude.md / agent-codex.md)

5.a-0 が固まらないと 5.a-1 以降が動けない (依存)。

## 5. レビュープロセス (Phase 1〜3 と同じ運用)

各 Step ごとに:

1. 本体実装 (サブステップ単位で commit)
2. 段 1 観点別並列レビュー (5 観点: correctness / P9 / philosophy / NF-004 / spec-drift)
3. 段 2 Claude 集約
4. 段 3 Codex 横断レビュー
5. 補修 + 段 5 K=2 収束

「small だから省略禁止」を Phase 3 Step 3.2 で再証明済。Phase 5 も同様の厳格運用。

## 6. 関連ファイル (v4 確定)

- `skills/source/` 配下 (本実装)
  - `metadata.yaml` (薄い build matrix) + `metadata.schema.json`
  - `body.md` (full モード正本、split 用 include marker 仕込み)
  - `workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md`
  - `hooks/claude-code/settings.example.json` (Codex hook は 5.a-0 後判断)
- `tools/build_skill.py` (新設) + `tools/_golden/{claude,codex}/{full,split}/` (golden fixtures)
- `development/docs/skill-converter/` (converter design journal)
  - `README.md` (responsibility + compatibility matrix)
  - `agent-claude.md` (front matter + 本文)
  - `agent-codex.md` (同上)
  - `transitions/` (該当時のみ)
- `pyproject.toml` (dev extras に `pyyaml>=6,<7` 追加)
- `requirements.lock` / `requirements-dev.lock` (`pyyaml` 追加で再生成、Phase 3 Step 3.2 規律)
- `.github/workflows/test.yml` (build check job 追加) + `.github/workflows/release.yml` (新設)
- `dist/` 配下 (`.gitignore` で除外)
- `.gitignore` (`dist/` 追加)
- `SECURITY.md` (Phase 5 で release workflow 説明追加)
- `development/docs/journal/phase5-step5-*.md` (各 Step の prejournal + 完結 journal)
- `development/docs/detailed-design.md` §16 新設 (Phase 5 詳細)
- `development/docs/requirements_and_development.md` §13 (Phase 5 進捗反映)
- `README.md` (利用者向けインストール経路 + build mode 説明 + agent 別動作確認レベル明示)
- `CLAUDE.md` (Phase 5 完結反映)
- `tools/diff_locks.py` (既存、Phase 3 Step 3.2、そのまま使い回し)
- GitHub Issue 1 件: `[Phase 6+] Antigravity CLI 向け skill build 対応`

## 7. v4 着手準備状況

- ✅ prejournal v1 commit (`dc6c9a7`)
- ✅ Codex 計画レビュー r1 (15 件 finding 反映)
- ✅ v2 commit (`5fd1689`)
- ✅ user 視点 3 件反映 (v3 commit `6e5616d`)
- ✅ Codex 計画レビュー r2 (9 件 finding 反映)
- ✅ user 判断 8 件確定 (案 C / 案 ii / Antigravity TODO 化)
- ✅ 本書 v4 (確定版)
- ⏳ **Antigravity TODO issue 起票** (5.a-0 でも可、v4 commit 後ただちに起票するのが望ましい)
- ⏳ user による v4 最終確認 → **Step 5.a-0 着手**

## 8. user 提示用判断点まとめ (v4 確定版)

| # | 判断点 | v4 確定 |
|---|---|---|
| 1 | `metadata.yaml` 構造 | **案 C: 薄い build matrix のみ** (agent_bindings 廃止) |
| 2 | `body.md` 分量 | **full / split 両モード、include marker で単一正本から生成** |
| 3 | `design-stages.md` スコープ | オンデマンド + B/C 統合 (章分離) |
| 4 | dogfooding 順序 | **2 段階 + Claude 主・Codex 軽め** (案 ii) |
| 5 | CI ビルド third-party action | `gh release upload` のみ |
| 6 | Step 3.3 並走判断 | Phase 5 後 + blocker のみ例外 |
| 7 | trigger / hook 戦略 | (α) body.md trigger + (γ) agent 別 hook 二段、hook = opt-in / dry-run / validate / 非破壊 |
| 8 | 対象 agent | **Claude Code + Codex CLI 2 つ supported**、Antigravity = TODO issue、Gemini = 扱わない |

これで Phase 5 のスコープ / 構造 / 規模 / レビュープロセス / 関連ファイル / 判断点が確定。Step 5.a-0 着手準備完了。
