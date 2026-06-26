# 成果物 acceptance matrix (Phase 5)

Step 5.a-0 で確定する成果物受け入れ条件。5.b 実装 + 5.b-ci CI + 5.d-canary / 5.e dogfood で各 cell を満たすことを確認する。

## acceptance matrix

| 観点 | Claude / full | Claude / split | Codex / full | Codex / split |
|---|---|---|---|---|
| **生成ファイル** | `SKILL.md` 単独 (本文に philosophy/stage-design/examples 全て埋め込み) | `SKILL.md` + `workflow.md` + `references.md` + `prompts/design-stages.md` + `prompts/review-policy.md` | `SKILL.md` 単独 (構造は Claude full と同等の本文、frontmatter 差分のみ) | `SKILL.md` + helper files (Claude split と同型) |
| **frontmatter** | `name: qgb` + `description` + `allowed-tools` + 他 (`agent-claude.md` 参照) | 同 (full / split で frontmatter 同一) | `name: qgb` + `description` (Codex CLI で確認済キーのみ) | 同 |
| **構文検証** | YAML frontmatter parse 成功 + Markdown parse 成功 | 同 + helper files も Markdown parse 成功 | 同 (Codex 側で `name`/`description` が読める) | 同 + helper files Markdown parse |
| **生成物 header** | 全成果物先頭に generator comment (converter version + source commit hash + 生成日時 + 「これは生成物。`skills/source/` を編集すること」 ) | 同 | 同 | 同 |
| **install ガイド** | `dist/skills/full/claude/INSTALL.md` 同梱、`~/.claude/skills/qgb/` への配置手順 | `dist/skills/split/claude/INSTALL.md`、配置手順 + helper files の関係説明 | `dist/skills/full/codex/INSTALL.md`、`~/.agents/skills/qgb/` への配置手順 | 同 (split 用) |
| **golden fixture** | `tools/_golden/claude/full/` 配下に期待生成物全件、`tools/build_skill.py` 出力と byte 一致 | `tools/_golden/claude/split/` 配下、同 | `tools/_golden/codex/full/` 配下、同 | `tools/_golden/codex/split/` 配下、同 |
| **manual smoke** | 配置 → 利用者 prompt 「qgb 入れて」で skill 起動確認 → SKILL.md 内容が Claude に読まれている確認 (深 dogfood で完全な対話を実施) | 同 + helper files が必要な依頼 (例: 「契約段階の設計やって」) で `workflow.md` / `prompts/design-stages.md` が参照される確認 (深 dogfood) | 配置 → smoke (`/skills` で qgb が一覧に出る + 起動成功) のみ。深 dogfood は不要 (案 ii) | 同 (smoke のみ) |
| **hook (任意)** | `dist/skills/full/claude/hooks/settings.example.json` 同梱、INSTALL.md で opt-in 手順説明 | 同 | `dist/skills/full/codex/hooks/hooks.example.json` 同梱、INSTALL.md で opt-in 手順説明 | 同 |
| **build mode 整合性** | full モードは body.md に embedded、`helper_files: []` で外部参照ゼロ | split は body.md 骨子 + helper files で参照、include marker 通りに本文が分割されている | full / split / agent 別の整合性確認は build_skill.py + golden fixture で機械検証 | 同 |

## 検証時期

| acceptance 項目 | 5.b 実装 | 5.b-ci CI | 5.d-canary | 5.e 利用者目線 |
|---|---|---|---|---|
| 生成ファイル | ✓ (ローカル build で確認) | ✓ (CI で diff vs golden) | △ (Claude full のみ skill 起動確認) | ✓ (Claude full + split 深、Codex full + split smoke) |
| frontmatter | ✓ | ✓ | ✓ | ✓ |
| 構文検証 | ✓ | ✓ | — | — |
| 生成物 header | ✓ | ✓ | — | — |
| install ガイド | ✓ (内容のみ) | — | — | ✓ (実際にガイドに従ってインストール) |
| golden fixture | ✓ (生成) | ✓ (vs build output) | — | — |
| manual smoke | — | — | ✓ (Claude full) | ✓ (全 cell) |
| hook | ✓ (テンプレ作成) | ✓ (parse 検証) | — | ✓ (任意で opt-in 確認) |
| build mode 整合性 | ✓ | ✓ | — | — |

## 「supported」 の合格基準

各 agent が `supported` 状態であるためには:

- Claude Code: 上記 matrix の全 cell が緑、Claude / full + Claude / split で深 dogfood 通過
- Codex CLI: 上記 matrix の全 cell が緑、Codex / full + Codex / split で smoke 通過 (深 dogfood は不要、案 ii)

未達成の場合の状態 (`agent-*.md` 前 matter):

- 全 cell 緑 + 深 dogfood OK → `supported`
- 全 cell 緑 + smoke のみ OK → `supported` (Codex は smoke で充分、案 ii)
- 一部 cell 不可 → `experimental` (Phase 5 で当面使わない、TODO 化したものは別)
- 構造的に対応不能 → `deferred` または GitHub issue で TODO

## 「TODO」 状態 (Antigravity 等)

5.a-0 で対象から外した agent は **GitHub issue で記録**、本 matrix の対象外。issue が「supported に昇格」する判断トリガは:

1. 公式 docs が SKILL ファイル相当の仕様レベルで整備される
2. コミュニティから具体的な利用ケースの要望が出る
3. qgb メンテナが主環境にする (例: Phase 5 中に Codex から Antigravity に乗り換える等)

該当 issue: [#25 [Phase 6+] Antigravity CLI 向け skill build 対応](https://github.com/Yumeno/Quality-gate-builder/issues/25)

## 関連

- `README.md` (本 dir、保守原則 + compatibility matrix)
- `agent-claude.md` / `agent-codex.md` (各 agent 仕様メモ)
- prejournal v4 §3.6 (本 matrix の骨子)
- 5.b 完結時の journal `phase5-step5-b.md` で matrix 各 cell の達成状況を記録
