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

### 2.4 Step 5.a-2-3 + K=2 r1 横断レビュー反映 (2026-06-28、9 件)

Step 5.a-2-3 (hooks テンプレ実装) commit `a7234e6` の後、5.a 全体完結 K=2 r1 横断レビューで必須 / 推奨 fix 9 件を追加受領。すべて K=2 r1 fix commit (本表更新後の commit、§3.2 commit chronology 末尾参照) で反映済:

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 (K=2 r1 source) |
|---|---|---|---|---|
| 14 | `framework-shape.md` line 266 (commit `c416345` 時点) | `dist/skills/{claude,codex,gemini}/` の旧 3-agent 想定 | `dist/skills/{full,split}/{claude,codex}/` の 4 成果物 | K=2 r1 spec fix #4: 段階 5 不可分 commit で見落とした残ドリフト、§5 訂正 + 関連 9 箇所と一致しない記述 |
| 15 | `skills/source/body.md` 冒頭コメント + `skills/source/README.md` + 本 journal §6.3 | split モード残置「marker 行の代わりに『@see <helper_filename>』程度の参照だけが残る」(body.md) vs 「trigger 参照行だけ残す」(README + journal、表現がブレ) | **正確に 1 行 `@see <helper-path>` を marker 1 組の位置に残す** (body.md コメントの contract が正本、README + journal もこの表現に統一) | K=2 r1 spec fix #3: 実装可能な変換規則として一意化。golden 作成前の必須確定 |
| 16 | `skills/source/hooks/{claude-code,codex}/settings.example.json` (commit `a7234e6`) | hook config 階層の `matcher` フィールドに qgb 関連 keyword の正規表現 | matcher フィールドは silently ignored のため**意図的に書かない**、command を PowerShell script (`scripts/check-relevance.ps1`) 起動に変更、script 内部で stdin JSON `.prompt` を正規表現判定 | K=2 r1 code fix #1: Claude Code + Codex CLI 両方の UserPromptSubmit event で matcher が機能しない実装上の事実を反映。「README 説明と逆になっていた」誤りを修正 |
| 17 | `skills/source/hooks/{claude-code,codex}/README.md` (commit `a7234e6`) | matcher 直接試行手順 + 未確定の `claude/codex config validate` 等の検証手順 | script 動作確認 3 ケース (match / no-match / empty stdin) + `/hooks` コマンド (source / trust / enable 状態確認) に書き換え | K=2 r1 code fix #2: hook README の検証手順が実体と一致していなかった誤りを修正 |
| 18 | `skill-converter/acceptance-matrix.md` 生成物 header 「生成日時」 | 生成日時を埋め込み + golden byte 一致を要求 | **生成日時は埋め込まない** (deterministic build) + `SOURCE_DATE_EPOCH` 環境変数で utility build に固定値を埋め込む規律 + `source_commit_hash` の dirty tree / archive / 非 Git 環境での挙動明文化 + encoding / newline / sort 順序の固定 | K=2 r1 spec fix #1: 「golden byte 一致と生成日時の矛盾」を解消、reproducible-builds.org 規約に整合 |
| 19 | 本 journal §6.3 「5.b 責務 9 項目」 | 9 項目で確定扱い (Step 5.a-2-2 段階 6 commit `acbd64f`) | **16 項目に拡張**: converter_min_version 比較 / generator header / INSTALL.md 生成 / hooks 同梱 / 構文検証 / deterministic ordering+encoding+newline / stale output 除去 or clean build を追加 | K=2 r1 spec fix #2: acceptance matrix を網羅できていなかった |
| 20 | `skills/source/README.md` 機械検証フロー step 3 (commit `c416345`) | unsupported/missing は「error、build_modes 別生成を skip」(部分成功あり) | **build 全体 fail-closed で停止** (部分成功を許さない、A1' 契約と整合) + 本 journal §6.3 にも反映 | K=2 r1 spec fix #5: agent status 失敗動作の矛盾を解消 |
| 21 | `skill-converter/agent-codex.md` line 168-172 (commit `c416345`) | hook 提供を「判断点」「暫定方針」と古い記述、`hooks.example.json` 内の `matcher` フィールド | Step 5.a-2-3 で実装済の状態を反映 (commit `a7234e6` + K=2 r1 fix #3 PowerShell script) + Codex `UserPromptSubmit` matcher silently ignored + stdin filtering + `/hooks` trust review の運用知見を追加 | K=2 r1 推奨 #1: agent-codex.md を最新化 |
| 22 | 本 journal §6.3 marker grammar 仕様 (commit `acbd64f`) | marker syntax の基本のみ明文化 | **完全固定**: helper_end 行頭完全一致 (末尾空白なし) / CRLF/LF 許容 / Unicode NFC normalization 後重複検出 / marker 内本文の先頭末尾空行を converter が trim せず保存 / symlink/hardlink/外部 path 経由の出力先逸脱防止 (`os.path.realpath` 確認) を追加 | K=2 r1 推奨 #2: marker grammar 完全固定 (golden fixture 作成前の必須確定) |

### 2.5 K=2 r2 横断レビュー反映 (2026-06-28、4 件)

K=2 r2 横断レビュー (Codex `codex_ctx_p5_step5a_completion_kappa2_r2_20260628-182541.txt`) で K=2 未達と判定、新規 spec finding 4 件を受領:

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 (K=2 r2 source) |
|---|---|---|---|---|
| 23 | `acceptance-matrix.md` deterministic build 契約 (commit `dd58cd6`) | 生成物 header に `source_commit_hash` (`git rev-parse HEAD`) を埋め込み + golden byte 一致を要求 | **`source_commit_hash` は生成物に埋め込まない**、代わりに `source_content_digest` (`skills/source/` 配下 authored source の sha256 hex digest) を埋め込み | K=2 r2 spec fix #1: golden 更新 commit で HEAD が変わると hash が自己参照になり byte 一致を維持できない問題を構造的に回避。「どの commit で build されたか」は release notes / SOURCE_DATE_EPOCH 経由で提供 |
| 24 | 本 journal §6.3 step 11 (commit `dd58cd6`) | 「`skills/source/hooks/<agent>/*` を `dist/skills/{full,split}/<agent>/hooks/` に copy」 | `<agent>` (= `claude` / `codex`) と source の hook dir 名 (= `claude-code` / `codex`) のずれを **`AGENT_TO_HOOK_DIRNAME = {"claude": "claude-code", "codex": "codex"}` mapping** で明示 | K=2 r2 spec fix #2: target agent 名と実 hook dir 名の不一致を converter 実装契約として明確化 |
| 25 | 本 journal §6.3 step 5 marker grammar (commit `dd58cd6`) | symlink / hardlink 防御を `os.path.realpath` で実現 | symlink 防御は realpath で OK、**hardlink 防御は別経路**: (a) clean build を default 採用 (`dist/.../` を build 冒頭で rmtree + 新規作成)、(b) target が存在しないことを `os.lstat` で確認、(c) `os.open(O_CREAT \| O_EXCL)` の exclusive create で書き込み、(d) POSIX で `O_NOFOLLOW` 併用、(e) 作成後 `st_nlink == 1` 確認 (検査のみ、真の防御線は (c)) | K=2 r2 spec fix #3 + K=2 r3 spec fix #1: 初版の「親 dir の `st_nlink == 0`」は誤り (既存 dir の link count は 0 にならない、全 build 失敗) → exclusive create を主防御に修正、検査のみは TOCTOU 防御にならない事実を明記 |
| 26 | `skill-converter/README.md` line 43 + line 66 (commit `c416345`) | line 43: `dist/skills/{claude,codex}/full/` 旧順序 / line 66: 「Codex CLI 用 hook は 5.a-0 後の判断、Phase 5 後送りも可」 | line 43: `dist/skills/full/{claude,codex}/` 正順序に訂正 / line 66: 「Step 5.a-2-3 (commit `a7234e6`) + K=2 r1 fix #3 で Claude Code + Codex CLI 両方の hook テンプレを実装済」と現状反映 | K=2 r2 spec fix #4: 段階 5 不可分 commit + Step 5.a-2-3 + K=2 r1 fix の累積結果と converter README の旧記述の不整合を解消 |

### 2.6 K=2 r3 / r4 横断レビュー反映 (2026-06-28、計 6 件)

#### K=2 r3 反映 (2 件)

K=2 r3 横断レビュー (Codex `codex_ctx_p5_step5a_completion_kappa2_r3_20260628-183143.txt`) で K=2 未達と判定、新規 spec finding 2 件を受領:

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 (K=2 r3 source) |
|---|---|---|---|---|
| 27 | 本 journal §6.3 step 5 marker grammar (commit `ee7cdc6`) + §2.5 #25 | hardlink 防御の sanity check として「親 dir の `st_nlink == 0`」を要求 | **実装可能な形に修正**: (a) clean build (rmtree + 新規作成)、(b) target が存在しないことを `os.lstat` で確認、(c) **exclusive create** (`os.O_CREAT \| os.O_EXCL`) で書き込み (TOCTOU 防御の主防御線)、(d) POSIX で `O_NOFOLLOW` 併用 (最終 component のみ)、(e) 作成後 `os.fstat(fd).st_nlink == 1` 確認 (`os.stat(path)` でなく `os.fstat(fd)` で TOCTOU 緩和、検査のみで完全防御にはならない)、(f) **脅威モデル限定明記**: 親 dir の symlink race は本防御範囲外 (POSIX `openat()` 相当が必要、Phase 5 では out of scope)、Windows native は `O_NOFOLLOW` 相当なしで防御弱化 | K=2 r3 spec fix #1 + K=2 r4 spec fix #1: 親 dir の `st_nlink == 0` は既存 dir で常に成立せず全 build 失敗、かつ親 dir の link count は target が hardlink かどうかと無関係。exclusive create を主防御に修正 + 親 dir symlink race / Windows native 防御弱化の脅威モデル限定を明文化 (`O_NOFOLLOW` は最終 component のみ保護) |
| 28 | `acceptance-matrix.md` deterministic build 契約 + 本 journal §6.3 step 9 (commit `ee7cdc6` / `786fdca`) | `source_content_digest` は body.md (source_files) のみを digest 対象としていたが、「build 入力の完全性証跡」と主張 | **`build_input_digest` に rename + 範囲拡張 (r3) + 更に範囲拡張 (r4)**: digest 対象を build 結果を決定する全入力に拡張: (1) `metadata.yaml` 全体、(2) `metadata.schema.json` 全体、(3) source_files の authored source、(4) 同梱対象 hook 関連ファイル (`AGENT_TO_HOOK_DIRNAME` mapping 適用)、(5) target_agents 各 agent の `agent-{name}.md` 全体、**(6) converter 実装自身 (`tools/build_skill.py` または `tools/build_skill/**/*.py` 全 source)** (K=2 r4 spec fix #2)、**(7) 環境変数 `SOURCE_DATE_EPOCH` (設定値または `unset`)** (K=2 r4 spec fix #3)。canonical 順 (番号順 + 各カテゴリ内辞書順 ASCII sort) で連結 sha256 計算 | K=2 r3 spec fix #2 + K=2 r4 spec fix #2/#3: 旧 source_content_digest は hook / metadata 変更で build 結果が変わっても digest が変わらない範囲不整合 (r3 で 6 カテゴリ拡張) + converter_version 文字列のみでは version bump 忘れで build 挙動変化を捉えられない (r4 で converter 実装自身を追加) + `SOURCE_DATE_EPOCH` 設定で生成物 header が変化するが digest manifest に含まれていなかった矛盾 (r4 で環境変数カテゴリ追加で解消) |

#### K=2 r4 反映 (4 件、上記 #27/#28 の追記 + 新規 #29/#30)

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 (K=2 r4 source) |
|---|---|---|---|---|
| 29 | `.gitattributes` (commit `57e11fe` 以前から既存) | `requirements*.lock text eol=lf` のみ、`*.md` / `*.json` 等は LF 強制なし | digest 対象拡張: `*.md` / `*.json` / `*.yaml` / `*.yml` / `*.ps1` / `*.sh` / `*.py` すべてに `text eol=lf` を追加 | K=2 r4 code fix #1: Windows の `core.autocrlf` で digest 対象が CRLF に変換され、build が環境依存になる問題を構造的に防止。converter 実装も `.py` で digest 対象 (#28 カテゴリ 6) のため `*.py` も含める |
| 30 | 本 journal §6.3 step 5 marker grammar (commit `786fdca`) | symlink/hardlink 防御の脅威モデル限定が未記述 | **脅威モデル限定明文化**: (a) `O_NOFOLLOW` は最終 component のみ保護、親 dir symlink race は POSIX `openat()` 相当が必要だが Python 標準 `os.open()` に API なし、Phase 5 では out of scope、(b) `os.stat(path)` → `os.fstat(fd)` への変更で TOCTOU 緩和、(c) Windows native は `O_NOFOLLOW` 相当機能なしで防御弱化、install ガイドで明示 | K=2 r4 spec fix #1: 「TOCTOU 主防御線」の主張範囲を明確化、Phase 5 accept 範囲と Phase 6+ 再評価項目を分離 |

#### K=2 r5 反映 (1 件、r4 契約と旧文言の整合)

| # | 旧記述の場所 | 旧記述 (要約) | 訂正後 | 訂正理由 (K=2 r5 source) |
|---|---|---|---|---|
| 31 | `acceptance-matrix.md` 生成物 header セル (line 12) + 設計上の主張 (line 86) + 本 journal §6.3 step 9 (commit `7e47f29`) | r4 で SOURCE_DATE_EPOCH 契約を導入したが、3 箇所に旧文言が残存: (a) header セル「生成日時は埋め込まない」(無条件記載) / (b) 設計主張「環境変数では digest が変化しない」/ (c) 完結 journal step 9 で digest 対象を旧 6 カテゴリ相当に記述 | r4 契約 (未設定時 = 日時なし、設定時 = 日時埋め込み + カテゴリ 7 で digest 化) に 3 箇所統一: (a) header セル「`SOURCE_DATE_EPOCH` 設定時のみ埋め込み」、(b) 設計主張「7 カテゴリの input のいずれが変わっても digest 変化」+ release build 系統 golden の運用記載、(c) step 9 で 7 カテゴリ列挙を明示 | K=2 r5 spec fix #1: r4 契約と旧文言の整合を取らないと 5.b 実装・テストの期待値が二通り (旧 vs 新) になる |

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
| `acbd64f` | 5.a-2-2 段階 6 | 5.a-2 完結 journal 初版 (Codex r1 spec fix #1 反映) |
| `a7234e6` | 5.a-2-3 | hooks テンプレ実装 (Claude Code + Codex CLI) — UserPromptSubmit hook 初版 |
| K=2 r1 fix commit (本書更新後) | K=2 r1 fix #1〜#9 | framework-shape line 266 Gemini 残ドリフト訂正 (#1) + split 残置規則 @see 統一 (#2) + hook PowerShell script + JSON 起動変更 (#3) + hook README script 動作確認 + /hooks 確認 (#4) + acceptance-matrix deterministic build 規則明示 (#5) + 完結 journal §6.3 を 9→16 項目拡張 (#6) + agent status fail-closed 統一 (#7) + agent-codex.md hook 実装済 + matcher 非対応 + /hooks 反映 (#8) + marker grammar 完全固定 (#9) |

### 3.3 Codex 横断レビュー履歴

| ラウンド | context file | 主要指摘 | 反映 |
|---|---|---|---|
| r0 (段階 2 前) | `codex_ctx_5a22_helper_decision.txt` → `codex_ctx_p5_step5a-2-2_review_20260628-012308.txt` (rename) | A1+ 推奨、spec fix #5 (full/prompts 矛盾) 発見、9 件指摘 | user 確定 (Q2-pre) で full モードでも prompts embed = A1' に拡張 |
| r1 (段階 3 後) | `codex_ctx_p5_step5a-2-2c_review_r1_20260628-105714.txt` | 必須 code fix 5 件 + 推奨 2 件 + spec fix 3 件 | 段階 3.5 / 4 / 4.5 / 段階 5 で全件反映 |
| r2 (段階 5 前) | `codex_ctx_p5_step5a-2-2_review_r2_20260628-131141.txt` | 追加必須 4 件 (C1 / S1 / S2 / S3 / S4) + 推奨 S5 | 段階 5 不可分 commit で全件反映、5.b 必須契約 (marker parser コメント内例示除外) は 5.b 着手時に反映予定 |
| K=2 r1 (5.a 全体完結 = 5.a-0 + 5.a-1 + 5.a-2 + 5.a-2-3) | `codex_ctx_p5_step5a_completion_kappa2_r1_20260628-172902.txt` | 必須 code fix 2 + 必須 spec fix 5 + 推奨 2 | K=2 r1 fix commit 群で全件反映 (本 §3.2 commit chronology 末尾参照)。`#3` PowerShell script + matcher 非対応対策、`#6` 5.b 責務 16 項目化、`#1` Gemini 残ドリフト、`#5` deterministic build、`#7` fail-closed、`#9` marker grammar 等を集約 |
| K=2 r2 (K=2 r1 fix 反映後の整合性確認) | `codex_ctx_p5_step5a_completion_kappa2_r2_20260628-182541.txt` | 新規 spec fix 4 件 (K=2 未達判定) | K=2 r2 fix commit で全件反映: `#1` source_commit_hash 自己参照問題 → source_content_digest に置換 (後に r3 で build_input_digest に再修正)、`#2` hook agent 名 mapping 明示、`#3` hardlink 防御を clean build + sanity check に分離 (後に r3 で実装可能な形に再修正)、`#4` skill-converter/README.md 旧 path + 旧 hook 方針残存訂正。本 §2.5 旧→新対応表 #23〜#26 参照 |
| K=2 r3 (K=2 r2 fix 反映後の整合性確認) | `codex_ctx_p5_step5a_completion_kappa2_r3_20260628-183143.txt` | 新規 spec fix 2 件 (K=2 未達判定) | K=2 r3 fix commit で全件反映: `#1` hardlink sanity check の親 dir `st_nlink == 0` が実装不能 → exclusive create (`O_CREAT \| O_EXCL`) を主防御に修正、`#2` source_content_digest 範囲不整合 (body.md のみ対象、build 結果に影響する hook / metadata 変更を捉えられない) → build_input_digest に rename + 範囲拡張。本 §2.6 旧→新対応表 #27〜#28 参照 |
| K=2 r4 (K=2 r3 fix 反映後の整合性確認) | `codex_ctx_p5_step5a_completion_kappa2_r4_20260628-183741.txt` | 新規 code fix 1 + spec fix 3 (K=2 未達判定) | K=2 r4 fix commit で全件反映: `#1` `.gitattributes` に digest 対象 LF 強制を追加 (`*.md` / `*.json` / `*.yaml` / `*.yml` / `*.ps1` / `*.sh` / `*.py`)、`#2` 親 dir symlink race の脅威モデル限定明記 (`O_NOFOLLOW` 最終 component のみ保護、`os.fstat(fd)` で TOCTOU 緩和、Windows native の防御弱化)、`#3` build_input_digest に converter 実装自身 (カテゴリ 6) を追加、`#4` `SOURCE_DATE_EPOCH` 環境変数 (カテゴリ 7) を追加で「全入力」主張との矛盾解消。本 §2.6 旧→新対応表 #27/#28/#29/#30 参照 |
| K=2 r5 (K=2 r4 fix 反映後 + 運用基準 / 5.b 送り判定明示で初実施) | `codex_ctx_p5_step5a_completion_kappa2_r5_20260628-195032.txt` | 新規必須 spec fix 1 件 + 5.b 送り 3 件 + Phase 6+ 送り 1 件 (K=2 未達判定、極めて収束) | K=2 r5 fix commit で必須 fix 1 件反映: `#1` `SOURCE_DATE_EPOCH` 契約 (r4) と旧文言の整合 (3 箇所統一: acceptance-matrix 生成物 header セル + 設計上の主張 + 完結 journal §6.3 step 9 の 7 カテゴリ列挙)。本 §2.6 #31 参照。**5.b 送り (3 件)**: single-file/package converter source 列挙の境界テスト / `SOURCE_DATE_EPOCH` 形式・範囲検証 / golden 系統具体化。**Phase 6+ 送り (1 件)**: 親 dir symlink race と Windows native の防御強化 (脅威モデル限定は十分明示) |
| **K=2 r6 = 達成判定ラウンド** | `codex_ctx_p5_step5a_completion_kappa2_r6_20260628-195525.txt` | **新規必須 fix 0 件、K=2 達成と Codex 明示判定** | 5.b 送り 3 件 + Phase 6+ 送り 1 件は r5 から継続、新規発見なし。Codex 補足: 将来の Phase 6+ 再評価時に「`os.open(..., dir_fd=...)` で `openat` 相当が利用可能」を再確認 (現行 Phase 5 の運用成立に影響しないため必須 fix にしない判定)。**収束系列: 9 → 4 → 2 → 4 → 1 → 0** (K=2 r1〜r6)。Step 5.a 全体 (5.a-0 + 5.a-1 + 5.a-2 + 5.a-2-3 + K=2 r1〜r5 fix) が運用基準で **完結** |
| 設計再検討 (K=2 r1 fix 進行中、user 提起) | `codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt` | 「日本語文書執筆プロジェクトの .ps1 契約」を append 章でなく構造的に解決すべき、と user 指摘 → Codex 推奨 `(η改) = θ command authoring protocol + ι capability-based dispatch + β-lite + ζ + γ-lite + κ mojibake sentinel` | 既存 K=2 r1 fix 完了後、別 Step `5.a-2-4` で θ/ι 設計判断を独立実装する方針確定 (Codex「混ぜるな」指摘)。本 Step の影響は body.md §6/§12 構造変更 (中〜大)、examples/japanese-docs-pwsh 新設 (中)、qgb core/schema 改修なし |

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

### 6.3 Step 5.b (build_skill.py 実装) で必要になる前提 (Codex K=2 r1 で 16 項目に拡張)

A1' 確定 + Codex K=2 r1 必須 / 推奨 fix 反映により build_skill.py の責務が明確化。**16 項目すべて 5.b の acceptance に含める**:

1. `metadata.yaml` を `metadata.schema.json` で validate
2. **`converter_min_version` と実装側 converter version の比較**、旧版 (実装 version が `converter_min_version` 未満) は build を refuse (Codex K=2 r1 spec fix #2)
3. `target_agents` の各 agent について `development/docs/skill-converter/agent-{name}.md` の front matter `status: supported` を確認。**1 件でも欠ければ build 全体を fail-closed で停止** (部分成功を許さない、Codex K=2 r1 spec fix #5)
4. `source_files` (= `[body.md]`) が skills/source/ 配下に存在することを確認
5. `body.md` 内の include marker (`<!-- split:helper_start NAME --> ... <!-- split:helper_end -->`) を parse:
   - **行頭が `<!-- split:helper_start <NAME> -->` である marker のみ実 marker と判定** (行末は LF/CRLF いずれも許容、行頭は完全一致、末尾の `-->` 直後は EOL のみ、HTML コメント内例示は除外、Codex K=2 r1 推奨 #2 + r2 5.b 必須契約)
   - `<!-- split:helper_end -->` も **行頭完全一致** (末尾空白なし、Codex K=2 r1 推奨 #2)
   - start / end の対応 (各 start に対応する end が存在、入れ子禁止、未閉鎖禁止)
   - marker name の重複禁止
   - marker name の **Unicode NFC normalization 後**で重複検出 (case collision 含む、Codex K=2 r1 推奨 #2)
   - marker name の path 安全性 (`..` / `./` / 連続 `//` / 先頭末尾スラッシュ / バックスラッシュ拒否、schema regex と同等)
   - marker name と `source_files` の集合分離 (collision detection で fail-closed)
   - marker 内容の先頭末尾空行は **converter が trim せずそのまま保存** (helper 単独利用時の Markdown 構造を保つ、Codex K=2 r1 推奨 #2)
   - **symlink / hardlink / 外部 path を介した出力先逸脱防止** (Codex K=2 r1 推奨 #2 + K=2 r2 spec fix #3 + K=2 r3 spec fix #1 + K=2 r4 spec fix #1):
     - **path traversal 防御**: helper file path を `os.path.normpath` で正規化、dist root 配下に収まることを literal path compare で確認
     - **symlink 防御 (最終 component)**: `os.path.realpath` で symlink を解決後、dist root の `realpath` の prefix 配下にあることを確認 (symlink で外部 path を指すケースを reject)
     - **hardlink 防御**: `os.path.realpath` では hardlink の別名関係は **検出できない**ため、別経路で対処:
       (a) **clean build を default 採用**: 各 build run の冒頭で `dist/skills/{mode}/{agent}/` を `shutil.rmtree` + `os.makedirs` で完全に作り直し、既存ファイル (hardlink 含む) を削除してから新規作成。これにより既存 hardlink 経由で外部 inode が書き換わる経路を構造的に潰す (K=2 r1 spec fix #2 step 14 「stale output 除去 or clean build」と統合)
       (b) **clean build 後の存在確認**: 書き込み前に target path が存在しないことを `os.lstat` (symlink を解決しない stat) で確認。存在すれば clean build が機能していない兆候として error
       (c) **exclusive create で書き込み**: `open(target, "xb")` または `os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY)` で書き込み。既存ファイルがあると `FileExistsError` で失敗、これにより TOCTOU 経由の置換攻撃の余地を最小化
       (d) **POSIX 環境では `O_NOFOLLOW` も併用**: 書き込み中に **最終 component の** symlink race で外部 path にすり替えられる経路を防御 (Windows native では `O_NOFOLLOW` 相当機能なし、accept)
       (e) **作成後の sanity check**: 作成直後に `os.fstat(fd).st_nlink == 1` を確認 (新規作成ファイルなので link count は 1 のはず、それ以外なら hardlink で既存 inode に結合した兆候)。**`os.stat(target)` ではなく `os.fstat(fd)` を使う**ことで、open 後 stat 前の再 link 攻撃を防ぐ (TOCTOU 緩和)。ただし検査のみで TOCTOU 完全防御にはならず、(c) の exclusive create が真の防御線
     - **脅威モデル限定 (K=2 r4 spec fix #1 で明文化)**:
       - 本防御は **dist root 配下の最終 component (= helper file 自体)** の不正書き換えを防ぐ。`O_NOFOLLOW` も `os.fstat(fd).st_nlink` も最終 component のみを保護する
       - **親ディレクトリ (`dist/skills/{mode}/{agent}/` 内の中間 dir) の symlink race は本防御範囲外**: open 前に親 dir が symlink へ置換されると `O_NOFOLLOW` では検出できない。完全防御には POSIX の `openat()` 相当 (信頼済み dir fd からの相対 open + 各親 component の `O_NOFOLLOW` 検証) が必要だが、Python 標準 `os.open()` には `openat` 公開 API がなく実装難度が高い
       - **本 Step での accept 範囲**: converter 実行中に dist tree の親 dir が攻撃者によって動的に書き換えられる脅威モデルは **out of scope** (利用者が信頼できる開発環境で build する前提)。利用者プロジェクトを target にした外部攻撃シナリオ (例: CI ランナー上で他プロセスが dist tree を mutate) は Phase 6+ で再評価
       - **Windows native の脅威モデル制限**: `O_NOFOLLOW` 相当機能がないため symlink race の防御は (a) clean build + (b) lstat + (c) exclusive create のみ。シナリオによっては POSIX 環境より防御が弱い、利用者には install ガイドで明示
6. **full モード生成**: marker tag (start / end コメント行 2 行) を converter が除去、marker 内本文はそのまま `SKILL.md` 本文として埋め込み
7. **split モード生成**: marker 内本文を helper file (`workflow.md` / `references.md` / `prompts/<name>.md`) に切り出し、本体 (`SKILL.md`) には marker 1 組の位置に **正確に 1 行 `@see <helper-path>`** という置換行を残す (Codex K=2 r1 spec fix #3、`<helper-path>` は marker name そのまま)
8. agent 別変換:
   - Claude Code: SKILL.md frontmatter (`allowed-tools` 等を追加)、`~/.claude/skills/qgb/` 配置想定
   - Codex CLI: SKILL.md frontmatter (Agent Skills 標準準拠、`agent-codex.md` の確定キーのみ)、`~/.agents/skills/qgb/` 配置想定
9. **生成物 header の埋め込み**: 全成果物の先頭に generator comment (`converter_version` + `build_input_digest` (sha256 短縮表記、build 結果を決定する全入力 7 カテゴリ = (1) metadata.yaml + (2) metadata.schema.json + (3) source_files + (4) 同梱 hook + (5) target agent docs + (6) converter 実装 (`tools/build_skill.py`) + (7) `SOURCE_DATE_EPOCH` 値 (未設定なら `unset`) の canonical hash) + 「これは生成物。`skills/source/body.md` を編集すること」)。**source commit hash は埋め込まない** (golden 自己参照問題回避、Codex K=2 r1 spec fix #1 + K=2 r2 spec fix #1)。**生成日時は `SOURCE_DATE_EPOCH` 設定時のみ埋め込み**、未設定時は埋め込まない (K=2 r3 spec fix #2 + K=2 r4 spec fix #2/#3)。`build_input_digest` 構成 (digest 対象 + canonical 順 + 計算手順) は `acceptance-matrix.md` 「build_input_digest の構成」節を参照
10. **`INSTALL.md` 生成**: 各 `dist/skills/{mode}/{agent}/INSTALL.md` を converter が生成 (配置 path / 任意 hook 有効化手順を含む、Codex K=2 r1 spec fix #2)
11. **hooks の成果物同梱**: `skills/source/hooks/<hook-dirname>/*` を `dist/skills/{full,split}/<agent>/hooks/` 配下に **そのまま copy** (Codex K=2 r1 spec fix #2 + K=2 r2 spec fix #2)。**`<hook-dirname>` は `<agent>` と異なる**ため明示 mapping が必要:
    - `agent=claude` → `<hook-dirname>=claude-code` (`skills/source/hooks/claude-code/` を `dist/skills/{full,split}/claude/hooks/` へ copy)
    - `agent=codex` → `<hook-dirname>=codex` (`skills/source/hooks/codex/` を `dist/skills/{full,split}/codex/hooks/` へ copy)
    - converter は内部に `AGENT_TO_HOOK_DIRNAME = {"claude": "claude-code", "codex": "codex"}` mapping を持ち、source の hook dir 構造 (`agent-claude.md` 等の docs 命名と一致した「Claude Code」「Codex CLI」風の dir 名) と target_agents の短縮名 (`claude` / `codex`) のずれを吸収する
12. **構文検証**: 生成された SKILL.md の YAML frontmatter parse 成功 + Markdown parse 成功 (helper file も同様、Codex K=2 r1 spec fix #2)
13. **deterministic ordering / encoding / newline**:
    - 出力 encoding: **UTF-8 BOM なし**、改行 **LF 固定**
    - frontmatter YAML キー順序: schema 定義順 (alphabetical でなく宣言順)
    - helper file 列挙順序: body.md 内 marker の出現順序に従う (re-sort しない)
    - `SOURCE_DATE_EPOCH` 未設定時は生成日時を埋め込まない (Codex K=2 r1 spec fix #1)
14. **stale output 除去 or clean build**: `dist/skills/<mode>/<agent>/` を build 前に空にする (clean build を default、stale file が残らない、Codex K=2 r1 spec fix #2)
15. `dist/skills/{mode}/{agent}/` に成果物を書き出し
16. `tools/_golden/{agent}/{mode}/` と byte 一致を CI で検証 + `tests/fixtures/build-skill/` の異常系で fail-closed 動作確認

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
