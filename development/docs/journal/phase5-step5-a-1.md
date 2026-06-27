# Phase 5 Step 5.a-1 完結ジャーナル: metadata.yaml + JSON Schema + minimal source tree

完結日: 2026-06-27
着手前判断: `phase5-prejournal.md` v4 (commit `9fb089b`)
前提: Step 5.a-0 完結 (`3fce8df`)

## Step 5.a-1 で確立した境界 (恒久記録)

### thin typed manifest (Phase 5 v4 case C の本実装)

prejournal v4 §3.3 の薄い yaml + Python コンバータ重視方針を本実装。`metadata.yaml` は build matrix の宣言のみを責務とし、agent 別の変換規則は `tools/build_skill.py` (5.b で実装) が持ち、agent 状態は `development/docs/skill-converter/agent-*.md` の front matter で 1 か所だけ管理する構造を確立。

`metadata.yaml` 確定形:

```yaml
skill_id: qgb                    # PEP 503 風 lowercase pattern
version: 0.1.0                   # semver pattern
description: |                   # max 500 chars
  qgb (quality-gate-builder) を使って任意のプロジェクトに証跡ゲート
  (REQ → contract → 機械検査 → ALLOW/DENY) を構築するスキル。
converter_min_version: 0.1.0     # build_skill.py 互換性の閾値

source_files:                    # 5 件、.md 拡張子のみ、uniqueItems
  - body.md
  - workflow.md
  - references.md
  - prompts/design-stages.md
  - prompts/review-policy.md

build_modes: [full, split]       # enum 固定
target_agents: [claude, codex]   # enum 固定 (Antigravity は issue #25)
```

**agent_bindings は廃止** (v3 案 C 採用、二重管理回避)。

### JSON Schema による機械検証 (5.b の build_skill.py が利用)

`skills/source/metadata.schema.json` で 7 必須キーを型固定:

- `additionalProperties: false` → typo (`skil_id` 等) を構造的に拒否
- `skill_id`: PEP 503 風 lowercase pattern `^[a-z][a-z0-9-]{0,62}$`
- `version` / `converter_min_version`: semver pattern
- `description`: 1-500 文字 (agent 中立で書く前提)
- `source_files`: `.md` 拡張子のみ、`uniqueItems: true`、`minItems: 1`
- `build_modes`: `enum: [full, split]`、`uniqueItems: true`、`minItems: 1`
- `target_agents`: `enum: [claude, codex]`、`uniqueItems: true`、`minItems: 1`

将来 Antigravity 等の agent が supported に昇格した場合は schema の `target_agents.items.enum` に追加 (Phase 6+ の判断)。

### 機械検証結果 (8 件全 PASS)

| ケース | 期待 | 結果 |
|---|---|---|
| typo skil_id | reject | ✅ (additionalProperties) |
| 未知 target_agents (antigravity) | reject | ✅ (enum) |
| 未知 build_modes (compact) | reject | ✅ (enum) |
| 不正 semver (0.1) | reject | ✅ (pattern) |
| 大文字 skill_id (Qgb) | reject | ✅ (pattern) |
| 非 md source_files (body.txt) | reject | ✅ (pattern) |
| 空 source_files [] | reject | ✅ (minItems) |
| 重複 target_agents [claude, claude] | reject | ✅ (uniqueItems) |
| 正常ケース | accept | ✅ |

### 5.b 実装時の build_skill.py 整合検証フロー (8 段階)

`skills/source/README.md` に明文化したフロー (5.b で本実装):

1. `metadata.yaml` を `metadata.schema.json` で validate (jsonschema、Phase 1 から runtime 依存)
2. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter を読む
3. 各 agent の `status` が `supported` であることを確認 (なければ error、`build_modes` 別の生成を skip)
4. `source_files` に列挙されたファイルが本 dir 配下に存在することを確認
5. `body.md` 内の include marker (例: `<!-- split:helper_start workflow.md -->`) を parse し、`build_modes: [full, split]` 両方を生成
6. 各 agent 別の変換ロジック (frontmatter キー差分 / 配置先 / etc) を適用
7. `dist/skills/{mode}/{agent}/` に成果物を書き出し
8. `tools/_golden/{agent}/{mode}/` と byte 一致を CI で検証

これは Phase 3 Step 3.2 の `tools/diff_locks.py` と同型の「決定的ビルド契約 + golden fixture 比較」パターン (Codex r1 code fix #1 反映)。

### minimal tree の構造

`skills/source/` 配下:

```
skills/source/
├── README.md                        # Phase 5 進行状態 + 機械検証フロー
├── metadata.yaml                    # ✅ 確定
├── metadata.schema.json             # ✅ 確定
├── body.md                          # stub (5.a-2 で full モード正本実装)
├── workflow.md                      # stub
├── references.md                    # stub
├── prompts/
│   ├── design-stages.md             # stub
│   └── review-policy.md             # stub
└── hooks/
    ├── claude-code/.gitkeep         # dir 予約 (5.a-2 で settings.example.json)
    └── codex/.gitkeep               # dir 予約 (5.a-2 で hooks.example.json)
```

stub の段階で `source_files` との整合は確保 (5 件すべて存在)。本文は 5.a-2 で実装。

## Step 5.a-1 の成果物 (commit `05f6288`)

| ファイル | 種別 | 内容 |
|---|---|---|
| `skills/source/metadata.yaml` | 新規 | thin typed manifest 確定形 |
| `skills/source/metadata.schema.json` | 新規 | JSON Schema 2020-12 (7 必須キー型固定) |
| `skills/source/body.md` | 新規 stub | 5.a-2 で full モード正本実装予定 |
| `skills/source/workflow.md` | 新規 stub | 同上 |
| `skills/source/references.md` | 新規 stub | 同上 |
| `skills/source/prompts/design-stages.md` | 新規 stub | 同上 |
| `skills/source/prompts/review-policy.md` | 新規 stub | 同上 |
| `skills/source/hooks/claude-code/.gitkeep` | 新規 | dir 予約 |
| `skills/source/hooks/codex/.gitkeep` | 新規 | dir 予約 |
| `skills/source/README.md` | 修正 | Phase 1 予約 → Phase 5 進行状態 + F-019 / framework-shape §5 への参照明示 |

## 想定外の発見 / 補修

### test_step9_docs.py との整合性 (補修 1 件)

Phase 1 で確立した spec 整合性テスト `tests/test_step9_docs.py::test_skills_source_readme_mentions_phase5_plan` は `skills/source/README.md` が以下のキーワードを含むことを assert:

- `Phase 5`, `metadata.yaml`, `body.md`, `workflow.md`, `references.md`, `prompts/`, `F-019`, `tools/build_skill.py`

README.md 書き換え時に **F-019 への参照が抜けて**いたため 1 件 fail。即座に F-019 + framework-shape §5 への参照を追加 (`関連` セクションに 2 行追記) → 全テスト通過。

**学び**: Phase 1 で確立した spec 整合性テストは Phase 5 でも有効に機能している。本テストは「Phase 5 で予約状態を書き換える際に F-019 への trace を失わない」防御機構として設計されていた (Phase 1 完結時の Codex セカンドオピニオン経由)。

## ローカル検証

- ローカル test: 753 passed + 3 skipped (Phase 3 Step 3.2 完結時から件数変動なし)
- ruff: All checks passed
- jsonschema 境界ケース機械検証: 8 件全 PASS
- `skills/source/` 配下の `source_files` 5 件と stub の整合: 確認済

## レビュー / K=2

本 Step は **schema 設計 + stub 作成 + 機械検証** が中心で、本文の起草は 5.a-2 に分離。Step 5.a-0 と同様、`5.a` 全体 (5.a-0 + 5.a-1 + 5.a-2) の完結時に Codex 横断 + K=2 を取る運用。

5.a-1 単独では:
- 段 1 観点別並列レビュー: **省略** (機械検証 8 件で代替)
- 段 3 Codex 横断レビュー: **5.a-2 完結後にまとめて 1 回**

## 次の Step 申し送り

### Step 5.a-2 (full モードで body.md + helper 本実装、include marker、token 計測 + split 切り出し判断)

5.a-1 で確立した structure を前提に:

1. **body.md (full モード正本)** を実装
   - philosophy 11 不易 (P1〜P11) の要点
   - stage-design パターン B/C の概要 (詳細は `prompts/design-stages.md`)
   - examples 6 例の使い分け概要
   - **trigger 表** (利用者の依頼語 → どの helper を読むか)
   - **include marker** (split モード生成用、例: `<!-- split:helper_start workflow.md -->` ... `<!-- split:helper_end -->`)
2. **helper files (workflow.md / references.md / prompts/) を実装**
   - full モード時は body.md に埋め込まれる (include marker 経由)
   - split モード時は別ファイルとして配置される
3. **hooks テンプレ実装**
   - `hooks/claude-code/settings.example.json` (Claude Code settings.json hook)
   - `hooks/codex/hooks.example.json` (Codex CLI hooks.json)
   - 両方とも opt-in / dry-run / validate / 非破壊 規律
4. **token 計測**
   - full モード body.md (全 helper 埋め込み) の文字数 / token 数を測定
   - user に提示 → split 切り出し判断 (Step 5.a-2 内 user 介入点)
5. **必要なら split モード本実装**
   - converter (5.b 実装) で full/split 両方を生成できる前提で、include marker の位置を確定

規模: 5.a-2 は prejournal v4 §4 で 2.0〜3.0 と見積もり済。本 Step 内で最大。

### Codex CLI の要 probe 項目 (5.b で確認)

`agent-codex.md` の `known_gaps`:

- SKILL.md frontmatter キーの全網羅 (`name` / `description` 以外で qgb が使いたいキーがあるか)
- dynamic context injection (Claude Code の `!command` 相当) の有無
- AGENTS.md と Skills の優先関係 (両方ある場合)

5.b で実際に Codex CLI 向け SKILL.md を書いてローカル動作確認するときに同時に検証。

## 関連ファイル

- prejournal v4: `development/docs/journal/phase5-prejournal.md` (commit `9fb089b`)
- Step 5.a-0 完結 journal: `development/docs/journal/phase5-step5-a-0.md` (commit `3fce8df`)
- converter design journal: `development/docs/skill-converter/`
- F-019 (要件): `development/docs/requirements_and_development.md` §F-019
- framework-shape §5 (Layer 3): `development/docs/framework-shape.md`
