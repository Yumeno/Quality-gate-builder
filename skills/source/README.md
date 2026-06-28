# skills/source/ — Phase 5 中間表現 (A1' 完成、本実装)

`skills/source/` は qgb スキルの **エージェント中立な中間表現の正本**。`tools/build_skill.py` (Phase 5 で新設) が本 dir から `dist/skills/{full,split}/{claude,codex}/` を機械生成する。

## A1' 構造 (Phase 5 Step 5.a-2-2 で確定)

skills/source/ の authored source は **`body.md` のみ** (A1' = body.md 単一正本)。split build で個別 helper として配置される `workflow.md` / `references.md` / `prompts/` 各ファイルは、`body.md` 内の include marker (`<!-- split:helper_start <NAME> --> ... <!-- split:helper_end -->`) から converter が機械生成する。これらの helper は `skills/source/` には存在せず、`dist/skills/split/{claude,codex}/` 配下にのみ現れる。

| ファイル | 場所 | 役割 |
|---|---|---|
| `metadata.yaml` | skills/source/ | thin typed manifest (build matrix 宣言) |
| `metadata.schema.json` | skills/source/ | JSON Schema 型固定 |
| `body.md` | skills/source/ | authored source 正本 (full モード本文 + split helper 本文を include marker で内包) |
| `workflow.md` | dist/skills/split/{claude,codex}/ | converter 生成、split helper |
| `references.md` | dist/skills/split/{claude,codex}/ | 同上 |
| `prompts/design-stages.md` | dist/skills/split/{claude,codex}/prompts/ | 同上 |
| `prompts/review-policy.md` | dist/skills/split/{claude,codex}/prompts/ | 同上 |

## 集合分離契約

- `metadata.yaml#source_files` は **converter が直接読む authored source 文書**の一覧 (現状 `[body.md]` のみ)
- `body.md` 内の include marker 名は **split build の生成 helper 名**を宣言
- 両者は **別集合** であり、marker 名は `source_files` に含めない
- A1' により skills/source/ に「読まないが置かれているファイル」は存在しない

## 機械正本 / 人間正本 の二重ファイル設計

- **機械正本**: `metadata.schema.json` + `tools/build_skill.py` (Phase 5 で新設) + `tools/_golden/{claude,codex}/{full,split}/`
- **人間正本**: `development/docs/skill-converter/` (各 agent 仕様の理解、過去の変換判断、変化追跡)

これは Phase 3 Step 3.0 の `project-context.{md, json}` と同型のパターン。詳細は `development/docs/skill-converter/README.md`。

## `metadata.yaml` の責務 (Phase 5 v4 case C)

`metadata.yaml` は **build matrix の宣言のみ**:

- `skill_id` / `version` / `description` / `converter_min_version`: skill のメタ情報
- `source_files`: converter が直接読む authored source (A1' で `[body.md]` のみ)
- `build_modes`: `[full, split]` の集合 (両方生成)
- `target_agents`: `[claude, codex]` の集合 (Antigravity は GitHub issue [#25](https://github.com/Yumeno/Quality-gate-builder/issues/25) で TODO、Gemini は扱わない)

**`agent_bindings` は廃止** (Phase 5 v4 で廃止)。agent 別の変換規則は `tools/build_skill.py` が持ち、agent 状態 (status / last_verified / hook_support 等) は `development/docs/skill-converter/agent-{name}.md` の front matter で 1 か所だけ管理。

build_skill.py が実行時に `target_agents` の各 agent について journal `agent-{name}.md` の `status: supported` を読んで整合検証する (片方を機械正本、もう片方を補助情報とする二重管理回避設計)。

## 機械検証フロー (5.b で実装)

`tools/build_skill.py` が以下の機械検証を行う:

1. `metadata.yaml` を `metadata.schema.json` で validate (jsonschema、Phase 1 から runtime 依存)
2. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter を読む
3. 各 agent の `status` が `supported` であることを確認 (なければ error、`build_modes` 別の生成を skip)
4. `source_files` に列挙されたファイル (= `body.md`) が本 dir 配下に存在することを確認
5. `body.md` 内の include marker (例: `<!-- split:helper_start workflow.md -->`) を parse し、`build_modes: [full, split]` 両方を生成:
   - **full モード**: marker 内容を本文ごと `SKILL.md` 1 ファイルに埋め込み
   - **split モード**: marker 内容を helper file (`workflow.md` / `references.md` / `prompts/<name>.md`) として切り出し、`SKILL.md` には trigger 参照行だけ残す
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
- prejournal v4: `development/docs/journal/phase5-prejournal.md` (historical record、v4 tree 図は A1' 確定前の設計記録。最終 tree は本 README + 5.a-2 完結 journal が normative)
- Step 5.a-0 完結 journal: `development/docs/journal/phase5-step5-a-0.md`
- Step 5.a-2 進行 journal: `development/docs/journal/phase5-step5-a-2-progress.md`
- converter design journal: `development/docs/skill-converter/`
