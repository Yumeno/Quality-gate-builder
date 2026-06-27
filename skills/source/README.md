# skills/source/ — Phase 5 中間表現 (本実装中)

`skills/source/` は qgb スキルの **エージェント中立な中間表現の正本**。Phase 5 で本実装中、`tools/build_skill.py` (Phase 5 で新設) が本 dir から `dist/skills/{full,split}/{claude,codex}/` を機械生成する。

## 現状 (Phase 5 Step 5.a-1 完結時点)

| ファイル | 状態 |
|---|---|
| `metadata.yaml` | ✅ 確定 (薄い build matrix 宣言、Phase 5 v4 case C) |
| `metadata.schema.json` | ✅ 確定 (JSON Schema 型固定、7 必須キー) |
| `body.md` | stub (Phase 5 Step 5.a-2 で full モード正本実装、split include marker 込み) |
| `workflow.md` | stub (Step 5.a-2 で実装) |
| `references.md` | stub (Step 5.a-2 で実装) |
| `prompts/design-stages.md` | stub (Step 5.a-2 で実装) |
| `prompts/review-policy.md` | stub (Step 5.a-2 で実装) |
| `hooks/claude-code/` | dir 作成済 (Step 5.a-2 で `settings.example.json` 実装) |
| `hooks/codex/` | dir 作成済 (Step 5.a-2 で `hooks.example.json` 実装、Codex hook 機構は agent-codex.md で確認済) |

## 機械正本 / 人間正本 の二重ファイル設計

- **機械正本**: `metadata.schema.json` + `tools/build_skill.py` (Phase 5 で新設) + `tools/_golden/{claude,codex}/{full,split}/`
- **人間正本**: `development/docs/skill-converter/` (各 agent 仕様の理解、過去の変換判断、変化追跡)

これは Phase 3 Step 3.0 の `project-context.{md, json}` と同型のパターン。詳細は `development/docs/skill-converter/README.md`。

## `metadata.yaml` の責務 (Phase 5 v4 case C)

`metadata.yaml` は **build matrix の宣言のみ**:

- `skill_id` / `version` / `description` / `converter_min_version`: skill のメタ情報
- `source_files`: 本 dir 配下のどのファイルを converter が読むか
- `build_modes`: `[full, split]` の集合 (Phase 5 では両方生成)
- `target_agents`: `[claude, codex]` の集合 (Antigravity は GitHub issue [#25](https://github.com/Yumeno/Quality-gate-builder/issues/25) で TODO)

**`agent_bindings` は廃止**。agent 別の変換規則は `tools/build_skill.py` が持ち、agent 状態 (status / last_verified / hook_support 等) は `development/docs/skill-converter/agent-{name}.md` の front matter で 1 か所だけ管理。

build_skill.py が実行時に `target_agents` の各 agent について journal `agent-{name}.md` の `status: supported` を読んで整合検証する (片方を機械正本、もう片方を補助情報とする二重管理回避設計)。

## 機械検証フロー (5.b で実装)

`tools/build_skill.py` が以下の機械検証を行う:

1. `metadata.yaml` を `metadata.schema.json` で validate (jsonschema、Phase 1 から runtime 依存)
2. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter を読む
3. 各 agent の `status` が `supported` であることを確認 (なければ error、`build_modes` 別の生成を skip)
4. `source_files` に列挙されたファイルが本 dir 配下に存在することを確認
5. `body.md` 内の include marker (例: `<!-- split:helper_start workflow.md -->`) を parse し、`build_modes: [full, split]` 両方を生成
6. 各 agent 別の変換ロジック (frontmatter キー差分 / 配置先 / etc) を適用
7. `dist/skills/{mode}/{agent}/` に成果物を書き出し
8. `tools/_golden/{agent}/{mode}/` と byte 一致を CI で検証

## 利用者目線 (Phase 5 完結後)

利用者は `dist/skills/{full or split}/{claude or codex}/` から自分の agent 用 1 セットだけ取得し、各 agent の規約に従って配置:

- Claude Code: `~/.claude/skills/qgb/` (Personal) または `.claude/skills/qgb/` (Project)
- Codex CLI: `~/.agents/skills/qgb/` (User) または `.agents/skills/qgb/` (Project)

詳細は Phase 5 完結時の release ノートとインストールガイドで提供予定。

## 関連

- F-019 (`development/docs/requirements_and_development.md` §F-019): Phase 5 中間表現とコンバータの正式要件
- `development/docs/framework-shape.md` §5: Layer 3 スキル層の構造
- prejournal v4: `development/docs/journal/phase5-prejournal.md`
- Step 5.a-0 完結 journal: `development/docs/journal/phase5-step5-a-0.md`
- converter design journal: `development/docs/skill-converter/`
