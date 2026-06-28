# Phase 5 Step 5.a-2 進行中ジャーナル (compact 跨ぎ用)

作成日: 2026-06-27
位置: Step 5.a-2-1 完結 (`f048deb`) 後 + 5.a-2-2 着手前の未解決論点記録
目的: コンテキスト compact / 新セッション後に作業を即再開するための受け渡し文書

## 1. ここまでの作業状態

### 1.1 完結した commits (Phase 5 関連、新しい順)

| commit | Step | 内容 |
|---|---|---|
| `f048deb` | 5.a-2-1 | body.md full モード正本実装 + split include marker |
| `6c5d155` | 5.a-1 ジャーナル | metadata.yaml + JSON Schema + minimal source tree の完結 journal |
| `05f6288` | 5.a-1 本体 | metadata.yaml + JSON Schema + minimal source tree |
| `3fce8df` | 5.a-0 | Agent contract probe + converter design journal 雛形 |
| `9fb089b` | prejournal v4 | 確定版 (Codex r2 反映 + user 判断 8 件確定) |

origin/main と同期済、working tree clean (本書 commit までは)。

### 1.2 確定済の設計判断 (prejournal v4 で記録、変更なし)

| # | 判断点 | 確定 |
|---|---|---|
| 1 | metadata.yaml 構造 | 案 C 薄い build matrix のみ、agent_bindings 廃止 |
| 2 | body.md 分量 | full / split 両モード生成、include marker で単一正本から |
| 3 | design-stages.md スコープ | オンデマンド + B/C 統合 (章分離) |
| 4 | dogfooding 順序 | 2 段階、Claude 主・Codex 軽め (案 ii) |
| 5 | CI ビルド third-party action | `gh release upload` のみ |
| 6 | Step 3.3 並走判断 | Phase 5 後 + blocker のみ例外 |
| 7 | trigger/hook 戦略 | (α) body.md trigger + (γ) agent 別 hook 二段 |
| 8 | 対象 agent | Claude Code + Codex CLI、Antigravity = issue #25 |

### 1.3 5.a-2-1 で完成した body.md (commit `f048deb`)

`skills/source/body.md` の構造:

- §1 何のためのスキルか
- §2 trigger 表 (機械的指針、利用者依頼語 → どの helper を読むか)
- §3 絶対遵守の 4 原則 (P5/P6/P7/P8)
- §4 qgb の構造 (`.quality-system/` 配下)
- §5 段階設計の柔軟性 (P10)
- §6 作業手順 `<!-- split:helper_start workflow.md -->` ... `<!-- split:helper_end -->`
  - 6.1 初期化フロー
  - 6.2 REQ 設計フロー
  - 6.3 デバッグフロー
  - 6.4 構造化編集フロー
- §7 参照集 `<!-- split:helper_start references.md -->` ... `<!-- split:helper_end -->`
- §8 supply-chain 規律
- §9 ドメイン依存性
- §10 トラブルシューティング
- §11 スキル自身の責務範囲

token 計測 (実機):
- cl100k_base (Claude 近似): 6,887 tokens
- o200k_base (GPT-4o): 5,583 tokens
- chars: 11,474、301 行、char/token 比 1.67

include marker は **§6 と §7 のみ**。`prompts/design-stages.md` と `prompts/review-policy.md` は body.md に embed せず、利用者の明示依頼で trigger 表経由オンデマンド読み込み (prejournal v4 判断点 3 確定方針)。

## 2. 未解決論点 (5.a-2-2 着手前の確認待ち) — ⚠️ SUPERSEDED

> **⚠️ 本節 §2 (および案 A/B/C 議論全体) は §7「5.a-2-2 着手前の最終確定」で
> 撤回され、最終決定が示された。LLM がこのファイルの途中だけを読む場合は §7 を
> 参照すること**。
>
> 最終決定への pointer:
> - §7.1 user 確定事項 (Q1 / Q2 / Q2-pre / Q5)
> - §7.2 Codex r1 横断レビュー受領
> - §7.3 安全な作業手順 (6 段階に分割、削除は最終段階)
> - 段階 5 で確定: A1' (`source_files: [body.md]` のみ、`workflow.md` /
>   `references.md` / `prompts/*` は body.md include marker から converter が
>   split build で機械生成)
>
> 本節 §2 は「議論の経緯を残すための historical record」として保持。

prejournal v4 §3.4 と §3.1 の間に小さな解釈ブレが残っていることを 5.a-2-2 着手時に発見:

### 2.1 解釈ブレの内容

- **prejournal v4 §3.4 (build mode 仕様)**: 「body.md が正本、split モード生成時はマーカー部分を切り出して helper file へ移動 + body.md には trigger 行だけ残す」 → body.md 単一正本、helper は dist の生成物
- **prejournal v4 §3.1 `source_files`**: `[body.md, workflow.md, references.md, prompts/design-stages.md, prompts/review-policy.md]` → これは「skills/source/ 配下のどの md を読むか」、helper も入力として読む建付けに見える
- **metadata.schema.json** `source_files` の description: 「converter はここに列挙されたファイルだけを読む」 (= 入力ファイル)

### 2.2 §3.4 と source_files の整合性についての 3 つの解釈案

5.a-2-2 着手時に user に提示済の選択肢:

#### 解釈案 A (私の最有力): source_files は「output 名前リスト」

- body.md が単一正本
- `workflow.md` 等の helper file は **converter 生成物の名前を予告するリスト**
- 現存する `workflow.md` / `references.md` / `prompts/*` の stub は **削除して OK**
- `metadata.schema.json` の `source_files` の description を「output filenames hint」に改める必要あり
- ただし `prompts/design-stages.md` と `prompts/review-policy.md` は body.md に embed していないので、これらは **5.a-2-2 で本実装する必要がある** (converter は生成しない、手書きの正本として残す)

#### 解釈案 B: 両方とも source、stub は将来の手書き入力場所として temporary に残す

- 現状の include marker 設計では body.md 単一正本
- でも将来「helper を独立して書きたい」要望が出るかも知れない
- stub のまま残し、5.b では include marker 経由で body.md から生成
- `source_files` の意味は揺れたまま

#### 解釈案 C: include marker 設計を逆向きに解釈、helper が正本

- 「body.md は骨子 + marker + 章フレーム」「helper file が full 内容の正本」
- 5.b の converter が full 生成時に marker 部分を helper の中身で埋める
- body.md §6 / §7 の詳細内容を helper file に移す
- prejournal v4 §3.4 の文言「split 時にマーカー部分を切り出して helper file へ移動」とは逆方向の動きになるので、prejournal の文字通りの解釈ではない (case C は不採用が正しい解釈)

### 2.3 私の推奨と未確定の論点

**推奨: 案 A**:
- body.md 単一正本という prejournal §3.4 の意図に最も忠実
- 二重管理回避 (user 判断 1 の精神) と整合
- `prompts/design-stages.md` / `prompts/review-policy.md` は **オンデマンド読み込み用の独立正本**として 5.a-2-2 で実装

**未確定論点**: `metadata.schema.json` の `source_files` の description を「output filenames hint」に書き換える対応は必要か? それとも `source_files` の意味を 5.a-2-1 で確定した body.md 中心方針に合わせて schema 側も再整理するか?

これは user 判断待ち、本書 commit 後の compact 跨ぎで判断する。

## 3. このあとの作業計画 (Step 5.a-2 残工程)

### 3.1 サブステップ構成

prejournal v4 §4 で 5.a-2 全体は規模 2.0〜3.0。5.a-2-1 で約 0.5 消化。残り:

| サブ | 内容 | 想定規模 | user 介入 |
|---|---|---|---|
| **5.a-2-2** | helper files 処理 (上記 §2 論点解決後)、prompts/ 本実装 | 0.5〜1.0 | §2.3 の論点 |
| **5.a-2-3** | hooks テンプレ (claude-code/settings.example.json + codex/hooks.example.json) | 0.3〜0.5 | hook 設計の最終確認 |
| **5.a-2-4** | 5.a-2 完結 journal | 0.2 | なし |
| (5.a 全体完結) | 5.a-0 + 5.a-1 + 5.a-2 まとめての Codex 横断 + K=2 | 0.3〜0.5 | K=2 達成判定 |

### 3.2 5.a-2-2 で具体的にやること (案 A 採用前提)

1. **解釈案 A を user 確認** → 確定したら以下:
2. `skills/source/workflow.md` / `references.md` の stub を整理:
   - 案 A 採用なら **削除 OR 「これは converter 生成物の名前予約、内容は body.md include marker 内」と書く 1 行 stub**
   - body.md と内容重複させない
3. `skills/source/prompts/design-stages.md` を **本実装**
   - Phase 2 で確立した Pattern B (external-LLM proposal/adopt 経路) の利用者向け解説
   - Pattern C (自律実行) の利用者向け解説
   - body.md trigger 表からオンデマンド読み込みされる前提
4. `skills/source/prompts/review-policy.md` を **本実装**
   - qgb 利用時の LLM レビューの観点と境界
   - 「LLM が ALLOW 判定に介入しない」「review 結果は advisory として knowledge に記録」等
   - body.md trigger 表からオンデマンド読み込み

### 3.3 5.a-2-3 で具体的にやること

5.a-0 で確立した `agent-claude.md` / `agent-codex.md` の hook 仕様を踏まえて:

1. `skills/source/hooks/claude-code/settings.example.json`
   - `UserPromptSubmit` で qgb 関連語 (qgb / REQ / 契約段階 / gate.json / ALLOW / DENY / NOT_READY) に match
   - `additionalContext` で qgb skill を起動するよう促す
   - opt-in / dry-run / validate / 非破壊
2. `skills/source/hooks/codex/hooks.example.json`
   - Codex CLI hooks.json 形式、Claude Code と同型の matcher + handler
   - opt-in / dry-run / validate / 非破壊
3. install ガイドへの組み込み方針 (5.d で正式実装)

### 3.4 5.a-2-4 (5.a-2 完結 journal)

5.a-2-1 + 5.a-2-2 + 5.a-2-3 の作業をまとめた完結 journal。Step 5.a-0 / 5.a-1 と同型の構造:

- 確立した境界 (恒久記録)
- 成果物
- 想定外の発見 / 補修
- ローカル検証
- レビュー / K=2 方針
- 次の Step 申し送り (5.b)

### 3.5 5.a 全体完結 (5.a-0 + 5.a-1 + 5.a-2 で K=2 を取る)

各サブの単独 K=2 は省略 (調査 + 文書 + schema 中心)、5.a-2 完結時にまとめて段 3 Codex 横断 + 段 5 K=2 を 1 回回す。**この時の context** には:

- skills/source/ 配下全体 (metadata.yaml + schema + body.md + helpers + prompts/ + hooks/)
- development/docs/skill-converter/ 全体
- prejournal v4 + 5.a-0 / 5.a-1 / 5.a-2 完結 journal

を渡して、Codex に「Phase 5 5.a 全体の構造として整合しているか」「5.b 着手に必要な情報が揃っているか」「prejournal v4 と実装のドリフトはないか」を点検してもらう。

## 4. 5.b 以降への申し送り (compact 跨ぎ用、確定済の前提)

Step 5.b (build_skill.py 実装) で必要になる前提:

### 4.1 build_skill.py の責務 (確定済)

1. `metadata.yaml` を `metadata.schema.json` で validate
2. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter `status: supported` を確認
3. `body.md` 内の include marker (`<!-- split:helper_start NAME -->` ... `<!-- split:helper_end -->`) を parse
4. **full モード生成**: include marker をそのまま無視 (本文ごと埋め込み)、`SKILL.md` 1 ファイル
5. **split モード生成**: マーカー内容を helper file (`NAME`) に切り出し、body.md (= SKILL.md) には trigger 参照行だけ残す
6. agent 別変換:
   - Claude Code: SKILL.md frontmatter (`allowed-tools` 等を追加)、`~/.claude/skills/qgb/` 配置想定
   - Codex CLI: SKILL.md frontmatter (`name` + `description` のみ)、`~/.agents/skills/qgb/` 配置想定
7. `dist/skills/{mode}/{agent}/` に成果物を書き出し
8. `tools/_golden/{agent}/{mode}/` と byte 一致を CI で検証

### 4.2 build_skill.py の依存

- `pyyaml>=6,<7` (dev extras に追加、Phase 3 Step 3.2 規律で lock 再生成必要)
- `jsonschema` (既存 runtime 依存)
- stdlib のみで足りる残り部分

### 4.3 5.b で確定する Codex CLI 仕様の known_gaps

`agent-codex.md` の `known_gaps`:
- SKILL.md frontmatter キーの全網羅
- dynamic context injection (Claude Code の `!command` 相当) の有無
- AGENTS.md と Skills の優先関係

5.b で実機検証 → `agent-codex.md` 更新。

### 4.4 acceptance matrix (`development/docs/skill-converter/acceptance-matrix.md`)

5.b で実装する確認項目は acceptance-matrix.md に確定済。4 cell (Claude × Codex × full × split) × 9 観点。

## 5. compact 跨ぎ後の即時アクション (新セッションの最初にやること)

1. 本書 (`phase5-step5-a-2-progress.md`) を Read
2. 未解決論点 (§2) で **解釈案 A 採用** を user に再確認 → 確定したら 5.a-2-2 着手
3. 案 A 採用なら:
   - `skills/source/workflow.md` / `references.md` を「内容は body.md include marker 内に正本がある」と書く 1 行 stub に置換 (or 完全削除)
   - `metadata.schema.json` の `source_files` description を「output filenames hint」に書き換え
   - `skills/source/prompts/design-stages.md` を本実装
   - `skills/source/prompts/review-policy.md` を本実装
4. 5.a-2-3 (hooks テンプレ実装) に進む
5. 5.a-2-4 (5.a-2 完結 journal)
6. 5.a 全体完結 → Codex 横断 + K=2

## 6. 関連ファイル (compact 跨ぎ後すぐ参照)

- prejournal v4: `development/docs/journal/phase5-prejournal.md` (commit `9fb089b`)
  - §3.4 build mode が本論点の元
  - §3.1 source_files が解釈ブレの元
- 5.a-0 完結 journal: `development/docs/journal/phase5-step5-a-0.md` (commit `3fce8df`)
- 5.a-1 完結 journal: `development/docs/journal/phase5-step5-a-1.md` (commit `6c5d155`)
- 5.a-2-1 の body.md: `skills/source/body.md` (commit `f048deb`)
  - §6, §7 に include marker 仕込み済
- metadata: `skills/source/metadata.yaml` + `metadata.schema.json` (commit `05f6288`)
- converter design journal: `development/docs/skill-converter/`
  - `README.md` / `agent-claude.md` / `agent-codex.md` / `acceptance-matrix.md`
- 関連 issue: <https://github.com/Yumeno/quality-gate-builder/issues/25> Antigravity TODO

## 7. 5.a-2-2 着手前の最終確定 (2026-06-28、Codex r1 横断レビュー後)

### 7.1 user 確定事項 (Q1 / Q2 / Q2-pre / Q5)

- **Q1 確定**: 解釈案 A 採用 (body.md 単一正本、include marker から helper を converter が split 時に生成)
- **Q2-pre 確定 (user 提起)**: full モード = **SKILL.md 1 ファイルに prompts/* も含めて全部のせ**。理由: 「LLM が手抜きして SKILL.md しか読まない」リスクへの保険。これは prejournal v4 §3.4 「full モード = 初心者、頻度低、token cost 許容」と整合
- **Q2 確定 (A1' へ昇格)**: skills/source/ から `workflow.md` / `references.md` / `prompts/design-stages.md` / `prompts/review-policy.md` を **すべて削除**。body.md が単一正本、helper はすべて include marker 経由
- **Q5 確定**: body.md §2 trigger 表は両モード共用 (split モード時は別ファイル path、full モード時は同ファイル内章への navigation)

### 7.2 Codex r1 横断レビュー受領 (`codex_ctx_p5_step5a-2-2_review_20260628-012308.txt`)

総合判定: **A1+ (A1 採用 + 契約強化)** = user の A1' と同じ方向。重要な指摘:

- **spec fix #5 (発見)**: prejournal v4 §3.4 表「helper_files: 空」と Q2 説明「full でも prompts copy」の矛盾。user 解釈で **prompts も embed = (b) パターン** に確定 → A1' 採用で一気に解消
- **code fix #1**: `source_files` と marker name を別集合として扱う (converter で集合分離契約)
- **code fix #3**: 正常 golden と異常系 parser fixture を分離 (`tests/fixtures/build-skill/`)
- **spec fix #3**: prejournal §3.1 tree 図 / §3.4 表は **silent edit せず訂正理由を journal に書く** + tree 自体訂正
- **spec fix #4**: dogfooding に **保守シナリオ** を含める (workflow 一文変更 → 両モード反映確認、新 marker 追加、collision fail-closed 確認)
- **spec fix #6**: prejournal の「full 4-6 KB」は実測 11,474 chars / 5,583-6,887 tokens で不整合 → 同時訂正対象
- **A3 系 (yaml に generated_helpers 重複宣言 / reserved-names.json / marker 論理 ID + path mapping) は全て却下**

### 7.3 安全な作業手順 (6 段階に分割、削除は最終段階)

LLM 開発主体の特性 (削除と再作成の間に compact 走るリスク) を踏まえ、A1' を「**追加 first、削除 last**」の順序で実施:

| 段階 | 内容 | A1'/A2 | 失敗時回復 | compact 耐性 |
|---|---|---|---|---|
| 1 | prompts/design-stages.md + review-policy.md を本実装 (stub→本文) | A2 + prompts 実体 | 中身書き直し | ✅ stop 可 |
| 2 | workflow.md / references.md stub を A1 中間状態へ (「正本は body.md §6/§7」と書く) | A2 過渡 | stub 書き直し | ✅ stop 可 |
| 3 | body.md に §12/§13 として prompts/* を include marker embed (skills/source/prompts/ も残す、二重化過渡) | A2 + 重複 | §12/§13 削除で段階 2 状態へ | ✅ stop 可 |
| **Codex r1** | **段階 3 完了後の横断レビュー (A1' で正しい方向か確認)** | — | — | — |
| 4 | metadata.schema.json description を A1' 移行明示に更新 (削除はしない) | A2 + A1' 移行明示 | description 元に戻す | ✅ stop 可 |
| **Codex r2** | **段階 5 着手前の最終確認 (削除の不可逆化前)** | — | — | — |
| 5 | helper 4 ファイルを git rm + metadata.yaml source_files を [body.md] に縮小 | A1' 完成 | git revert | ✅ stop 可 |
| 6 | 5.a-2 完結 journal で prejournal v4 §3.1 / §3.4 訂正方針を明文化 (silent edit せず) | — | — | — |

各段階で:
- 個別 commit + push (まとめ commit にしない)
- pytest 緑確認
- 本書 (`phase5-step5-a-2-progress.md`) に「段階 N 完了、次は段階 N+1」を 1 行追記

### 7.4 test_step9_docs.py 確認結果 (段階 1 着手前事前把握)

`tests/test_step9_docs.py` を Read した結果:

- `test_skills_source_readme_mentions_phase5_plan` (line 25-41) は **README.md のキーワード assert のみ** (`workflow.md` / `references.md` / `prompts/` 等)
- **物理ファイル存在は assert していない** → 段階 5 で skills/source/workflow.md / references.md を物理削除しても test は通る
- README.md は「split モード時に converter が生成する helper file 名」として workflow.md / references.md / prompts/ の言及を保つ (段階 5 で README.md 更新が必要)
- `metadata.yaml` の存在 / `source_files` 列挙は test 依存なし → 段階 5 で `source_files: [body.md]` に縮小しても test 影響なし

### 7.5 関連 commit (本 §7 反映時点)

- 本書 §7 追記 commit (段階 1 着手前の最終確定記録)
- 段階 1-6 各個別 commit (各段階完了後)

## 8. 段階別進捗ログ (各段階完了後に追記)

- **段階 1 完了** (commit `755d696`, 2026-06-28):
  - `skills/source/prompts/design-stages.md` (278 行, 14,347 chars) Pattern B/C 統合
  - `skills/source/prompts/review-policy.md` (210 行, 12,292 chars) LLM レビュー境界
  - pytest 753 passed + 3 skipped、ruff clean
- **段階 2 完了** (commit `6f4e96a`, 2026-06-28):
  - `skills/source/workflow.md` (9 行): 「正本は body.md §6」と書く 1 行 stub
  - `skills/source/references.md` (9 行): 「正本は body.md §7」と書く 1 行 stub
  - pytest test_step9_docs.py 15 passed
- **段階 3 完了** (commit `c8e3809`, 2026-06-28):
  - body.md に §12 (prompts/design-stages.md) + §13 (prompts/review-policy.md) を include marker embed
  - body.md 新サイズ: 798 行, 27,990 chars, cl100k 17,094 tokens, o200k 13,834 tokens
  - skills/source/prompts/ 原本は段階 5 まで残す (二重化過渡、fail-safe)
  - pytest test_step9_docs.py 15 passed
- **Codex 横断レビュー 1 回目完了** (`codex_ctx_p5_step5a-2-2c_review_r1_20260628-105714.txt`):
  - 必須 code fix 5 件 + 推奨 code fix 2 件 + spec fix 3 件を受領
  - A1' の方向性は妥当、ただし段階 4 / 5 着手前に修正が必要
  - 6 段階を 8 段階に分割 (段階 3.5 + 4.5 を追加、段階 5 は不可分 commit)
- **段階 3.5 完了** (commit `c9c2a09`, 2026-06-28):
  - body.md §2 trigger 表を mode-neutral 化 (full/split 別の読み替え原則を明示)
  - 「本ファイル §12 / §13」cross-reference を実在見出し名 (「段階設計プロンプト」「レビュー観点プロンプト」) ベースに修正
  - §6 / §7 / §12 / §13 のメタ説明と include marker 内 sister reference も mode-neutral 化
  - Codex r1 必須 code fix #1, #2 反映
  - pytest 15 passed
- **段階 4 完了** (commit `5532bfb`, 2026-06-28):
  - metadata.schema.json source_files description を「過渡記述」から「永続的最終契約」に書き換え
  - source_files items pattern を path 安全性強化 (`..` / `./` / 連続 `//` / 先頭末尾スラッシュ / バックスラッシュ拒否)
  - 境界ケース 22 件全 PASS、現状 metadata.yaml は更新 schema で valid
  - Codex r1 必須 code fix #4, #5 反映
- **段階 4.5 完了** (commit `17498d6`):
  - body.md include marker 内容と prompts/* 原本の欠落比較を実施
  - design-stages: 見出し 30/30 identical, code blocks 5/5, table rows 21/21
  - review-policy: 見出し 30/30 identical, code blocks 3/3, table rows 0/0
  - mode-neutral 化分の +225 / +233 chars 差は意図通り
  - Codex r1 code fix #6 反映、段階 5 削除前検証完了
- **Codex 横断レビュー 2 回目完了** (`codex_ctx_p5_step5a-2-2_review_r2_20260628-131141.txt`):
  - 追加必須 fix 4 件 (C1 body.md line 128 / S1 framework-shape 9 箇所 / S2 requirements 6+3 箇所 / S3 README / S4 progress journal)
  - 推奨 S5 (converter design docs 3 ファイル) を段階 5 に含める判断
  - helper 4 件削除そのものによるコード/テスト破綻なしを Codex が静的検証で確認
  - 段階 5 着手可、不可分 commit 維持
- **段階 5 完了** (本 commit、不可分):
  - skills/source/workflow.md / references.md / prompts/design-stages.md / prompts/review-policy.md を `git rm`
  - metadata.yaml `source_files` を `[body.md]` に縮小 (A1' = body.md 単一正本完成)
  - body.md line 128 cross-reference mode-neutral 化 (Codex r2 C1)
  - skills/source/README.md を A1' 完成形に更新 (Codex r2 S3)
  - framework-shape.md §5 全面改訂 + 関連 4 箇所訂正 (Codex r2 S1)
  - requirements_and_development.md F-019 / C-008 / Phase 5 概要 + 関連 5 箇所訂正 (Codex r2 S2)
  - progress journal §2 に SUPERSEDED admonition + §7 へのポインタ追加 (Codex r2 S4)
  - converter design 3 ファイル (skill-converter/README.md / acceptance-matrix.md / agent-codex.md) を A1' 補足訂正 (Codex r2 S5)
  - 機械検証: marker 集合 4/4 / metadata schema valid / 欠落比較 60/60 / README keyword test / 全 pytest 緑 / 削除後 git grep
  - **次: 段階 6** (5.a-2 完結 journal で旧→新対応表を作成、Codex r1 spec fix #1 反映)
