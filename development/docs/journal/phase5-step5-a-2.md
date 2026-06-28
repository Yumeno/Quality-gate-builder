# Phase 5 Step 5.a-2 完結ジャーナル: A1' 単一正本 + 上位仕様 spec drift 訂正

完結日: 2026-06-28
着手前判断: `phase5-prejournal.md` v4 (commit `9fb089b`)
前提: Step 5.a-1 完結 (`05f6288` + `6c5d155`)
進捗 journal (compact 跨ぎ用): `phase5-step5-a-2-progress.md` (commit `d5d9356` 以降の各 commit で逐次追記)

## 1. Step 5.a-2 で確立した境界 (恒久記録)

### 1.1 A1' = body.md 単一正本 (Phase 5 Step 5.a-2-2 で確定)

`skills/source/` の authored source は **`body.md` のみ** という構造を確定。`workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md` は **`skills/source/` には存在しない**、`body.md` 内の include marker (`<!-- split:helper_start <NAME> --> ... <!-- split:helper_end -->`) から converter (5.b で実装) が split build で機械生成する。

確定経緯:

- prejournal v4 §3.4 「body.md が正本、split モード生成時はマーカー部分を切り出して helper file へ移動 + body.md には trigger 行だけ残す」「二重管理 (full と split を別 md ファイルで保守) を構造的に回避」が原則だが、§3.1 `source_files` 一覧では helper も列挙されており、metadata.schema.json description でも「converter はここに列挙されたファイルだけを読む」と書かれていた。5.a-2-2 着手時に解釈ブレを発見
- user 確定 (Q1): 解釈案 A 採用 (body.md 単一正本)
- user 確定 (Q2-pre): full モード = LLM が SKILL.md しか読まない場合の保険として `prompts/*` も body.md に embed → A1' (= A1 拡張、helper 全部 marker 経由) を採用
- user 確定 (Q2): `skills/source/` から helper 4 ファイル全削除
- user 確定 (Q5): body.md §2 trigger 表は両モード共用 (mode-neutral)

### 1.2 集合分離契約 (Codex r1 code fix #1 反映)

- `metadata.yaml#source_files` は **converter が直接読む authored source 文書** (現状 `[body.md]` のみ)
- `body.md` 内の include marker 名は **split build の生成 helper 名**を宣言
- 両者は **別集合** であり、marker 名は `source_files` に含めない
- A1' により skills/source/ に「読まないが置かれているファイル」は存在しない
- 5.b の build_skill.py は marker name と source_files の集合分離を構造的に検証 (collision detection で fail-closed)

### 1.3 marker path 安全性契約 (Codex r1 code fix #5 反映)

`metadata.schema.json` の `source_files.items.pattern` で構造的に拒否:

- `..` (parent traversal)
- `./` (current ref)
- 連続 `//` (空 segment)
- 先頭 / 末尾スラッシュ (絶対 / trailing)
- バックスラッシュ
- `.md` 以外の拡張子

境界ケース 22 件 (正常 7 + 危険 15) で機械検証済。5.b の marker parser も同等の path 安全性を強制する責務分担。

### 1.4 build mode 別の読み替え原則 (Codex r1 code fix #1, #2 反映、段階 3.5)

body.md §2 trigger 表 + 関連 cross-reference を mode-neutral 化:

- **full モード**: 同じ SKILL.md 内の埋め込み見出し (本ファイル内の該当章) を読む。`#` で始まる見出し名を identifier として扱う
- **split モード**: 指定 helper を別ファイルとして必ず読む (配置先は本ファイルと同一ディレクトリ、Read tool でファイル名指定で読める)

「本ファイル §12 / §13」のような番号付き節参照は実在しない見出しを指していたため、見出し名 (「段階設計プロンプト」「レビュー観点プロンプト」) ベースに修正。

### 1.5 削除と再作成の間に compact 走るリスクへの対応原則

LLM 開発主体特有の失敗モード (削除と再作成の間に context 断絶が走る) を踏まえ、段階を「追加 first、削除 last」に分割。各段階完了で個別 commit + push、各段階の進捗を journal に逐次反映。段階 5 のような不可逆な削除は最終段階に置き、削除前に欠落比較 (段階 4.5) + Codex r2 横断レビューを挟む構成。

## 2. Codex r1 spec fix #1 反映: 旧→新対応表

prejournal v4 や上位仕様には A1' 確定前 (v3 以前) の構造記述が残っていた。Step 5.a-2-2 で訂正した内容を以下の表で記録する。**この表が 5.a-2 完結時点の normative reference**。

### 2.1 主要訂正対象 (Codex r2 必須 S1 / S2 / S3 / S4)

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 / 移行先 | 現行 normative 文書 | 訂正理由 |
|---|---|---|---|---|---|
| 1 | `prejournal v4 §3.1` tree 図 (commit `9fb089b`) | `skills/source/` に `body.md` + `workflow.md` + `references.md` + `prompts/design-stages.md` + `prompts/review-policy.md` を authored source として列挙 | `skills/source/` の authored source は `body.md` + `metadata.yaml` + `metadata.schema.json` + `README.md` のみ | 本 journal §1.1 + `skills/source/README.md` (commit `c416345`) + `framework-shape.md` §5 (commit `c416345`) | A1' = body.md 単一正本確定、helper は body.md include marker からの生成物。prejournal v4 は historical record として保持 (silent edit せず、本表で対応) |
| 2 | `prejournal v4 §3.3` metadata.yaml 例 + `framework-shape.md` §5 旧 metadata.yaml 例 (line 134-162 既存) | `entry_body: body.md`、`helper_files: [workflow.md, references.md, prompts/*]`、`agent_bindings: {claude: {...}, codex: {...}, gemini: {...}}` | thin typed manifest: `skill_id` / `version` / `description` / `converter_min_version` / `source_files` (= `[body.md]` のみ) / `build_modes` / `target_agents`。`agent_bindings` は v4 で廃止、agent 状態は journal `agent-{name}.md` の front matter で 1 か所だけ管理 (二重管理回避) | `skills/source/metadata.yaml` (commit `c416345`) + `framework-shape.md` §5 (commit `c416345`) + `requirements_and_development.md` §F-019 (commit `c416345`) | Phase 5 v4 case C 確定。agent_bindings は v4 で廃止判断、source_files と marker 名の集合分離を確立 |
| 3 | `prejournal v4 §3.4` build mode 表「full モード: helper_files: 空」 | full モード: 単一 SKILL.md ファイル (helper 内容を本文に embed)。split モード: SKILL.md + helper 4 ファイルを同ディレクトリに配置 | 本 journal §1.1 + `framework-shape.md` §5 + `skills/source/README.md` | user 確定 (Q2-pre) で full モード = LLM が SKILL.md しか読まない場合の保険として prompts も embed する方針を採用。「helper_files: 空」は marker helper だけの意味だったと整理 |
| 4 | `prejournal v4 §3.4` 「full モード token 4-6 KB」 | full モード実測: 27,990 chars / 17,094 cl100k tokens / 13,834 o200k tokens (body.md 803 行) | 本 journal §3.1 + `skills/source/body.md` (commit `c416345`) | full モード = 全部のせ + prompts も embed の方針確定により、見積もりが約 4 倍に拡大。これは「LLM が SKILL.md しか読まない場合の保険」の用途と整合 (Claude 200K context の 8.5%、token cost 許容用途) |
| 5 | `prejournal v4 §3.1` dist 出力先 + `framework-shape.md` §5 dist tree (line 119-122 既存) | `dist/skills/{claude, codex, gemini}/` の 3 agent 想定 | `dist/skills/{full, split}/{claude, codex}/` の supported 2 agent × 2 mode = 4 成果物 | `framework-shape.md` §5 (commit `c416345`) + `requirements_and_development.md` §F-019 (commit `c416345`) + `skills/source/README.md` | Phase 5 v4 で supported = Claude Code + Codex CLI 確定 (Gemini = 扱わない、終息品)。Antigravity = GitHub issue #25 で TODO 化 |
| 6 | `framework-shape.md` line 20 / 27 / 104 / 166 / 174 / 181 / 271 / 335 / 436 (既存) | 「3 エージェント」「Claude / Codex / Gemini」「`GEMINI.md`」等 | 「Claude Code + Codex CLI」「supported 2 agent」「明示的撤回記述 (Gemini は扱わない、Antigravity は GitHub issue で TODO)」 | `framework-shape.md` (commit `c416345`) | 同上 (Phase 5 v4 supported 確定) |
| 7 | `requirements_and_development.md` line 29 / 199 / 648-688 / 768 / 771 / 1402-1410 (既存) | 「3 エージェント」「Gemini CLI」「`GEMINI.md`」「`agent_bindings`」等 | A1' 構造 + Phase 5 v4 supported = Claude Code + Codex CLI に揃える | `requirements_and_development.md` (commit `c416345`) | 同上 |
| 8 | `skills/source/README.md` line 11-17 (既存) | helper を stub として `skills/source/` 配下に列挙、「Phase 5 で実装中」 | A1' 完成形: skills/source/ の authored source は body.md のみ、helper は dist/ 配下の生成物 | `skills/source/README.md` (commit `c416345`) | A1' 完成 (段階 5)、`test_step9_docs.py::test_skills_source_readme_mentions_phase5_plan` の keyword (workflow.md / references.md / prompts/ 等) は A1' 文脈で説明文として維持 |
| 9 | `skills/source/metadata.schema.json` `source_files` description (commit `05f6288`) | 「skills/source/ 配下の source 文書一覧。converter はここに列挙されたファイルだけを読む」 | 「converter が直接読む authored source 文書の順序付き一覧。各要素は skills/source/ 配下に実在しなければならない。split helper の出力名は body.md の split:helper_start marker で宣言し、source_files には含めない。A1' (Phase 5 Step 5.a-2-2) では body.md が本文および helper 内容の単一正本となる。path は POSIX 形式 relative path のみ、絶対パス・親参照・空 segment・カレント参照・連続区切り・バックスラッシュは禁止」 | `skills/source/metadata.schema.json` (commit `5532bfb`) | Codex r1 必須 #4 反映、永続契約として最終化。集合分離契約と path 安全性宣言を明文化 |
| 10 | `progress journal §2` (commit `d5d9356`) | 「prompts は body に embed しない」前提の解釈案 A/B/C 議論 | SUPERSEDED admonition + §7 (最終確定) へのポインタ追加、§2 は historical record として保持 | `phase5-step5-a-2-progress.md` (commit `c416345`) | Codex r1 spec fix #3 + Codex r2 必須 S4 反映、案 1 採用 (取り消し線全面適用や移動は不採用) |

### 2.2 推奨補足訂正 (Codex r2 推奨 S5)

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 |
|---|---|---|---|---|
| 11 | `skill-converter/README.md` line 59 (既存) | `body.md` / `workflow.md` / `references.md` を連結した AGENTS.md の選択肢 | A1' 補足: helper は body.md include marker からの生成物名 (skills/source/ には存在しない) | A1' 構造との誤読防止 |
| 12 | `skill-converter/acceptance-matrix.md` line 17 (既存) | full モード: helper_files: [] で外部参照ゼロ | A1' 文言: full モードは body.md include marker 内容を本文に embedded、helper は skills/source/ には authored source として存在しない、source_files (= `[body.md]`) と marker 名の集合分離検証も明示 | 同上 |
| 13 | `skill-converter/agent-codex.md` line 112 (既存) | `body.md` / `workflow.md` / `references.md` を連結した AGENTS.md の選択肢 | A1' 補足: 同上 (helper は body.md include marker から converter が機械生成) | 同上 |

### 2.3 維持対象 (historical record として残す、訂正しない)

以下は Step 5.a-2-2 で訂正の対象としない:

- 過去 journal (`prejournal v4`, `phase5-step5-a-0.md`, `phase5-step5-a-1.md`, `phase3-step3-2.md` 等): historical record として保持、本表が訂正/移行先の単一の参照点
- `examples/*/knowledge/project-context.md` 内の「Gemini CLI 等」: 利用者プロジェクトの補佐 LLM 例として一般的記述、Phase 5 supported target の宣言ではない
- `detailed-design.md` 内の補佐 LLM 例: 同上

## 3. Step 5.a-2 の作業成果 (commit chronology)

### 3.1 body.md final 状態 (commit `c416345`)

- 行数: 803
- chars: 約 28,000
- cl100k tokens: 約 17,100 (Claude 近似)
- o200k tokens: 約 13,800 (GPT-4o)
- include marker: 4 件 (workflow.md / references.md / prompts/design-stages.md / prompts/review-policy.md)、対応 OK、入れ子なし、コメント内例示除外
- 章構造: §1 何のためのスキルか / §2 trigger 表 (mode-neutral) / §3 絶対遵守の 4 原則 (P5/P6/P7/P8) / §4 qgb の構造 / §5 段階設計の柔軟性 (P10) / §6 作業手順 (workflow.md marker) / §7 参照集 (references.md marker) / §8 supply-chain 規律 / §9 ドメイン依存性 / §10 トラブルシューティング / §11 スキル自身の責務範囲 / §12 段階設計プロンプト (prompts/design-stages.md marker) / §13 レビュー観点プロンプト (prompts/review-policy.md marker)

### 3.2 commit chronology (5.a-2 全体)

| commit | Step / 段階 | 内容 |
|---|---|---|
| `f048deb` | 5.a-2-1 | body.md full モード正本実装 + split include marker (§6 / §7) |
| `d5d9356` | 5.a-2 進捗 (compact 跨ぎ) | progress journal 作成 |
| `555081a` | 5.a-2-2 着手前確定 | A1' 6 段階手順を progress journal §7 / §8 に追記 |
| `755d696` | 5.a-2-2 段階 1 | prompts/design-stages.md + review-policy.md を独立ファイル正本として本実装 |
| `6f4e96a` | 5.a-2-2 段階 2 | workflow.md / references.md stub を A1 中間状態に置換 (「正本は body.md §6 / §7」) |
| `c8e3809` | 5.a-2-2 段階 3 | body.md §12 / §13 で prompts/* を include marker embed (skills/source/prompts/ 原本は段階 5 まで残す、二重化過渡) |
| `73676a2` | 5.a-2-2 進捗反映 | progress journal §8 に段階 1-3 完了ログ追記 |
| `c9c2a09` | 5.a-2-2 段階 3.5 | body.md §2 trigger 表 mode-neutral 化 + cross-reference 修正 (Codex r1 必須 #1, #2) |
| `5532bfb` | 5.a-2-2 段階 4 | metadata.schema.json description 最終契約化 + source_files path 安全性強化 (Codex r1 必須 #4, #5) |
| `17498d6` | 5.a-2-2 段階 4.5 | embedded vs 原本 欠落比較 (Codex r1 #6) + progress journal 追記 |
| `c416345` | 5.a-2-2 段階 5 | A1' 完成不可分 commit (helper 4 ファイル物理削除 + source_files: [body.md] 縮小 + README A1' 完成形 + framework-shape §5 全面改訂 + requirements §F-019 / C-008 / Phase 5 概要訂正 + progress journal SUPERSEDED + converter design 3 ファイル補足訂正、Codex r2 必須 #C1/#S1/#S2/#S3/#S4 + 推奨 S5) |
| 本 commit | 5.a-2-2 段階 6 | 5.a-2 完結 journal (本書、Codex r1 spec fix #1 反映) |

### 3.3 Codex 横断レビュー履歴

| ラウンド | context file | 主要指摘 | 反映 |
|---|---|---|---|
| r0 (段階 2 前) | `codex_ctx_5a22_helper_decision.txt` → `codex_ctx_p5_step5a-2-2_review_20260628-012308.txt` (rename) | A1+ 推奨、spec fix #5 (full/prompts 矛盾) 発見、9 件指摘 | user 確定 (Q2-pre) で full モードでも prompts embed = A1' に拡張 |
| r1 (段階 3 後) | `codex_ctx_p5_step5a-2-2c_review_r1_20260628-105714.txt` | 必須 code fix 5 件 + 推奨 2 件 + spec fix 3 件 | 段階 3.5 / 4 / 4.5 / 段階 5 で全件反映 |
| r2 (段階 5 前) | `codex_ctx_p5_step5a-2-2_review_r2_20260628-131141.txt` | 追加必須 4 件 (C1 / S1 / S2 / S3 / S4) + 推奨 S5 | 段階 5 不可分 commit で全件反映、5.b 必須契約 (marker parser コメント内例示除外) は 5.b 着手時に反映予定 |

## 4. 機械検証実績 (段階 4.5 / 段階 5 / 全 Step)

- **marker 集合検証**: 4 件 (workflow.md / references.md / prompts/design-stages.md / prompts/review-policy.md)、対応 OK、重複なし、入れ子なし、コメント内例示除外
- **schema 境界ケース**: 22 件 (正常 7 件 + 危険 15 件) 全 PASS
- **metadata.yaml schema 検証**: 段階 4 / 段階 5 後とも valid
- **embedded vs 原本 欠落比較** (段階 4.5): 見出し 60/60 identical / code blocks 8/8 / table rows 21/21
- **README keyword test**: `test_step9_docs.py::test_skills_source_readme_mentions_phase5_plan` 通過
- **全 pytest**: 段階 1 / 2 / 3 / 3.5 / 4 / 4.5 / 5 すべての commit で 753 passed + 3 skipped (POSIX-only、Phase 3 Step 3.2 完結時から件数変動なし)
- **削除後 git grep**: 残存参照はすべて historical journal record (時系列記録として正しい状態)

## 5. レビュー / K=2

5.a-2 単独では:
- 段 1 観点別並列レビュー: **省略** (機械検証で代替)
- 段 3 Codex 横断レビュー: **3 ラウンド実施** (r0 / r1 / r2)
- 段 5 K=2: **5.a 全体完結時にまとめて実施** (5.a-0 + 5.a-1 + 5.a-2 を context に渡す)

## 6. 次の Step 申し送り

### 6.1 Step 5.a-2-3 (hooks テンプレ実装、未着手)

`skills/source/hooks/claude-code/settings.example.json` + `skills/source/hooks/codex/hooks.example.json` を本実装。5.a-0 で確立した `agent-claude.md` / `agent-codex.md` の hook 仕様を踏まえる。opt-in / dry-run / validate 可能 / 非破壊の acceptance 規律 (Codex r0 code fix #3) を反映。

### 6.2 5.a 全体完結 (5.a-0 + 5.a-1 + 5.a-2 + 5.a-2-3 で K=2)

各サブの単独 K=2 は省略 (調査 + 文書 + schema 中心)、5.a 全体完結時にまとめて段 3 Codex 横断 + 段 5 K=2 を 1 回回す。context には:

- skills/source/ 配下全体 (metadata.yaml + schema + body.md + hooks/)
- development/docs/skill-converter/ 全体
- prejournal v4 + 5.a-0 / 5.a-1 / 5.a-2 完結 journal
- 上位仕様 訂正後の framework-shape / requirements_and_development

を渡して、Codex に「Phase 5 5.a 全体の構造として整合しているか」「5.b 着手に必要な情報が揃っているか」「prejournal v4 と実装のドリフトはないか (本書 §2 対応表で訂正済の項目以外に残ドリフトがないか)」を点検してもらう。

### 6.3 Step 5.b (build_skill.py 実装) で必要になる前提

A1' 確定により build_skill.py の責務が明確化:

1. `metadata.yaml` を `metadata.schema.json` で validate
2. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter `status: supported` を確認
3. `source_files` (= `[body.md]`) が skills/source/ 配下に存在することを確認
4. `body.md` 内の include marker (`<!-- split:helper_start NAME --> ... <!-- split:helper_end -->`) を parse:
   - **行頭が `<!-- split:helper_start <NAME> --> `である marker のみ実 marker と判定** (HTML コメント内例示は除外、Codex r2 5.b 必須契約)
   - start / end の対応 (各 start に対応する end が存在、入れ子なし、未閉鎖なし)
   - marker name の重複なし
   - marker name の path 安全性 (`..` / `./` / 連続 `//` / 先頭末尾スラッシュ / バックスラッシュ拒否、schema regex と同等)
   - marker name と `source_files` の集合分離 (collision detection で fail-closed)
5. **full モード生成**: marker をそのまま無視 (本文ごと埋め込み)、`SKILL.md` 1 ファイル + コメント自体は除去
6. **split モード生成**: marker 内容を helper file (`workflow.md` / `references.md` / `prompts/<name>.md`) に切り出し、body.md (= SKILL.md) には trigger 参照行だけ残す
7. agent 別変換:
   - Claude Code: SKILL.md frontmatter (`allowed-tools` 等を追加)、`~/.claude/skills/qgb/` 配置想定
   - Codex CLI: SKILL.md frontmatter (Agent Skills 標準準拠)、`~/.agents/skills/qgb/` 配置想定
8. `dist/skills/{mode}/{agent}/` に成果物を書き出し
9. `tools/_golden/{agent}/{mode}/` と byte 一致を CI で検証

### 6.4 5.b で実装する fixture 構造

Codex r1 code fix #3 反映:

- `tools/_golden/{claude,codex}/{full,split}/`: 正常な最終成果物の byte 一致 fixture
- `tests/fixtures/build-skill/`: parser 異常系 fixture を分離 (duplicate-marker / unclosed-marker / nested-marker / path-traversal / case-collision / source-output-collision / empty-helper)

### 6.5 dependency 追加

`pyyaml>=6,<7` を dev extras に追加、Phase 3 Step 3.2 規律で `requirements-dev.lock` の再生成が必要。

### 6.6 dogfooding の保守シナリオ (Codex r1 spec fix #4)

Step 5.d / 5.e の dogfooding に「保守シナリオ」を含める:

1. workflow の一文を変更する
2. full と split の双方へ一度だけ反映されることを確認
3. 新 marker helper を追加する
4. collision / malformed marker が fail-closed になることを確認

これは A1' (body.md 単一正本) が保守視点で正しく機能していることを検証する。

## 7. 関連ファイル

- prejournal v4: `development/docs/journal/phase5-prejournal.md` (commit `9fb089b`、historical record、本 journal §2 対応表で訂正)
- 5.a-0 完結 journal: `development/docs/journal/phase5-step5-a-0.md` (commit `3fce8df`)
- 5.a-1 完結 journal: `development/docs/journal/phase5-step5-a-1.md` (commit `6c5d155`)
- 5.a-2 進捗 journal (compact 跨ぎ用): `development/docs/journal/phase5-step5-a-2-progress.md` (commit `d5d9356` 以降逐次追記)
- 本書 5.a-2 完結 journal
- 中間表現: `skills/source/body.md` + `metadata.yaml` + `metadata.schema.json` + `README.md` (commit `c416345`)
- 上位仕様 (A1' 反映済): `development/docs/framework-shape.md` §5 + `development/docs/requirements_and_development.md` §F-019 / §C-008 (commit `c416345`)
- converter design journal: `development/docs/skill-converter/`
- 関連 issue: <https://github.com/Yumeno/Quality-gate-builder/issues/25> Antigravity TODO
