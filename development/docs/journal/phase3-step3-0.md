# Phase 3 Step 3.0 完結ジャーナル: detect 廃止 + project-context 二重ファイル設計

**完結日:** 2026-06-22
**規模実績:** 2.5 (Step 5 = 1.0 基準、計画 2.0〜2.5、補修サイクル込み)
**テスト:** Phase 2 完了時 731 → Step 3.0 完了時 700 (削除 60 + 新規 22 + 修正 9)

## Step 3.0 で確立した境界 (恒久記録)

### ライン引きの最終形 (philosophy / framework-shape との整合)

| ドメイン | 担い手 | 形式 |
|---|---|---|
| プロジェクトの自己定義 (何を作りたいか) | 人間 | `project-context.md` |
| md → json 構造化 | 補佐 Agent (利用者環境の LLM) | `project-context.json` |
| json の schema 検証 | qgb (機械) | `qgb validate` |
| json + .quality-system/ 現状を構造化して export | qgb (機械) | `qgb design-stages propose-context` |
| 段階設計の生成 | 本番 LLM (Phase 5 スキル) | `proposal.json` |
| proposal の schema + 整合性検証 + 適用 | qgb (機械) | `qgb design-stages adopt` |
| contract の検査実行 | qgb (機械) | `qgb run` |
| ALLOW/DENY 判定 | qgb (機械) | `gate.json` |

### 撤回した方針

- **adapter 量産方針**: Go / Rust / .NET / Java / PHP / Markdown adapter の計画を全撤回
- **qgb detect / qgb/adapters/ コマンドとモジュール**: 削除
- **Phase 4 (CI 連携)**: 廃止 (Phase 3 spec 改訂で確定)

### 撤回の決定打 3 点 (再掲、Phase 5 着手時の判断材料)

1. 対象プロジェクトの広がり (Markdown / プロンプト集 / 設定群 / 法務テンプレ等) に adapter 抽象が追いつかない
2. 検出結果は ALLOW/DENY 判定の根拠にならない (basis[] は REQ / CONTRACT / POLICY / WAIVER のみ)
3. 残存すると Phase 5 スキルへの悪い few-shot 教材になる (「対象判定 = 機械的検出モジュール」を学ぶ誘因)

## Step 3.0 のサブステップ構成

`review-process` memory の段 1〜段 5 サイクルを 4 サブステップ commit で吸収。

| サブステップ | commit | 内容 |
|---|---|---|
| Step 3.0 本体 | `59e6042` | detect 削除 + qgb/adapters/ 削除 + project-context.schema.json 新設 + loader/init/validate/proposal/design_stages/cli 改修 + tests 改修/新設 + examples/python-cli-pytest 記入例 |
| Step 3.0a | `6bf4a23` | CLAUDE.md を Phase 1 着手前文書から Phase 3 反映版に全面書き換え |
| Step 3.0b | `1507446` | canonical specs (requirements / detailed-design / framework-shape / stage-design) の spec-drift 解消 + B-1〜B-3 + 運用契約明文化 |
| Step 3.0c | `d70f5d5` | phase1-manual.md + tests/test_step9_docs.py 更新 + B-4 + B-5 + docs grep regression test 4 件追加 |
| Step 3.0d | `4ec20aa` | examples/markdown-docs/ に project-context.{md,json} 追加 + adapter 言及を Phase 5 スキル + project-context モデルに置換 |

前段 spec 改訂 (`ada386b`) と着手前判断 (`b0f8e4e`) も合わせて Step 3.0 サイクルは合計 7 commit。

## レビュープロセス完走

`review-process` memory の段 1〜段 5 をすべて実施:

- **段 1**: subagent 並列 5 観点 (correctness / P9 / philosophy / NF-004 / spec-drift) で重大漏れ 6 件 (spec-drift) + 中程度 5 件 + 軽微多数を発見
- **段 2**: 集約・調停で A 群 (blocker 6) / B 群 (改善推奨 5) / C 群 (修正不要 9) に整理、割れた論点 2 件を段 3 へ
- **段 3**: Codex 横断レビュー 1 周目で割れた論点 2 件への結論 + 段 1 見落とし 2 件 (運用契約 / regression test) を発見
- **補修サイクル**: 4 サブステップ commit で 13 件すべてに対応
- **段 5**: Codex 横断レビュー 2 周目で「指摘なし収束」判定 (2026-06-22)

Codex から得た重要な指摘:
- 1 周目: A 群 6 件への補修順序 (3-4 本 commit 分割、Codex 推奨に従い 4 サブステップ採用)、案 X (phase1-manual.md は Step 3.0 に追従)、案 Q (markdown-docs に project-context 追加)、段 1 見落とし 2 件
- 2 周目: 指摘なし収束、運用契約明文化を「Phase 5 スキル設計者の判断材料として十分」と評価

## 重要な恒久記録: Claude が前段で 2 回ラインを引き間違えた事実

prejournal (`phase3-step3-0-prejournal.md`) で詳述。要旨を再掲:

- 1 回目: User 指摘「Phase 4 ガウディの塔疑惑」を受けて adapter 廃止 + Phase 5 スキルが LLM で判定の案を提示 → User 受け入れず
- 2 回目: User 指摘「LLM/機械の責務分掌ラインを点検して」を受けて反転「adapter は P7 のため残す」を提示 → User 指摘「ユーザーが作るのは必ずプログラミング言語のプログラムとは限らない」で再廃止

**誤りの構造的盲点 (Codex 段 3 指摘で確定)**:
- 「対象プロジェクト = プログラミング言語のソース」と暗黙仮定する傾向
- 「機械責務 = 確定的」「LLM 責務 = 揺らぎ」と二分しがち、中間 (補佐 Agent が確定的構造化を担う) の存在を見落とす
- philosophy P6 を「LLM を排除する」と読みがちで「機械検査と組み合わせる」本義を忘れがち

Phase 5 着手時、同様のバイアスが顔を出していないか本ジャーナルと prejournal を読み返して確認すること。

## Phase 3 Step 3.0 で新設された機械装置

### 1. `qgb/schemas/project-context.schema.json`

対象プロジェクトの自己定義を機械可読化する schema。Codex 指摘 3 件反映:

- root に `human_reviewed: bool` (人間承認を別立て、P8 境界)
- `language` 単数フィールドを避け `technologies` / `artifact_kinds` (array) で広い語彙
- `source_metadata` で `generated_by` (human / agent-assisted) と `source_md_sha256`
- title description に P11 (cross-project comparison invalid) と P8 (free prose は data であって instructions ではない) を明示

### 2. `qgb/core/loader.py:load_project_context`

ファイル不在 = None (optional)、BOM tolerant (utf-8-sig)、schema 検証は別経路。

### 3. `qgb/core/init.py:_materialise_project_context_json`

空欄雛形を `human_reviewed: false` 初期値、`generated_by: human` で生成。`now` 引数 injection でテスト pin 可能 (3 テスト追加)。

### 4. `qgb/core/proposal.py:build_proposal_context`

`detect` フィールド削除、`project_context` フィールド追加 (None なら null)。`human_reviewed: false` のとき `warnings[]` に provisional 警告を追加。`intended_use_note` + `constraints.project_context_role` で「project_context は basis でない / free prose を prompt として注入しない / P11 比較不可」を明示。

### 5. docs grep regression test (`tests/test_step9_docs.py`)

Phase 3 Step 3.0 で撤去された機構 (qgb detect / qgb.adapters / run_detect / DetectionResult) が docs / コードに silently 復活するのを早期検出する 4 件のテスト。`_ALLOWED_*_PATTERNS` で廃止記述・履歴記録・別語を除外する設計。

## Phase 3 Step 3.0 で確立した運用契約 (framework-shape.md §5)

Layer 3 (Phase 5 スキル) の責務範囲を補強する 5 観点:

1. **編集権**: 人間が md、補佐 Agent が json、`human_reviewed: true` は人間のみ
2. **不一致時の扱い**: `source_md_sha256` 突合 + Agent による再生成フロー + 緊急時の人間直接編集
3. **API 期待**: Phase 5 スキルが project-context を読む経路 (`qgb design-stages propose-context` 経由が推奨)、`human_reviewed: false` warning 動作
4. **欠落時 fallback**: `project_context: null` のとき: スキルが対象を直接 Read、`examples/` を参考、人間にヒアリング。「detect の代わりに言語判定するのは禁止」
5. **Free prose の prompt-injection 扱い**: `purpose` / `scope.*` / `non_adopted_methods[].reason` などの自然言語は data として扱い、上位指示として注入しない (P8 / NF-007 境界)

## examples の Phase 3 Step 3.0 対応状況

| example | project-context.md | project-context.json | 役割 |
|---|---|---|---|
| generic-minimal | — | — | 言語非依存の最小例 (project-context は実装オプション) |
| python-cli-pytest | ✅ | ✅ (`human_reviewed: true`, agent-assisted) | コードベース対象の二重ファイル記入例 |
| markdown-docs | ✅ | ✅ (`human_reviewed: true`, agent-assisted) | non-code 対象の二重ファイル記入例 (Codex 段 3 推奨案 Q) |
| python-fastapi-pytest | — | — | (Step 3.3 で実需に応じて追加判断) |
| go-cli | — | — | 同上 |
| node-cli-vitest | — | — | 同上 |

Phase 5 着手時にスキルから見て「何が足りないか」が見えてから残 example の project-context 追加判断する (prejournal C.2 + Phase 3 計画 §14.4 の方針通り、先回りで全部やらない)。

## 規模実績の振り返り

| 項目 | 計画 | 実績 | 差分 |
|---|---|---|---|
| Step 3.0 本体 | 2.0〜2.5 | 1.5 | 計画下振れ (削除作業中心) |
| 補修サイクル (3.0a〜3.0d) | (計画外) | 1.0 | spec-drift / 運用契約 / regression test の追加対応 |
| **合計** | **2.0〜2.5** | **2.5** | **計画上限** |

補修サイクルが規模上振れ要因。Codex 1 周目で発見した spec-drift 6 件と段 1 見落とし 2 件 (運用契約 / regression test) は当初 prejournal の段 1 想定範囲を超えていた。Phase 5 着手時の prejournal では「派生 docs (CLAUDE.md / phase1-manual / stage-design / 受け入れ条件§12 等) の改訂も Step 計画に含める」を反映すること。

## Step 3.1 (command runner 強化 + CI 雛形) への申し送り

- `qgb/core/runner.py` の `_run_command` を `qgb/core/command.py` に切り出す改修は本 Step では触っていない (Step 3.1 のスコープ)
- Step 3.0 で確立した運用契約 (framework-shape.md §5) は Step 3.1 の `command.py` 設計でも参照される (Phase 5 スキルが contract を起草するときの判断材料)
- CI 雛形 (`.github/workflows/test.yml`) は本 Step では作成していない (Step 3.1 のスコープ、Step 3.0 で立てた regression test は CI 動作確認の最初の対象になる)
- Step 3.0 で追加した regression test 4 件は Step 3.1 以降の commit でも CI 経由で機械的に検査される (Phase 3 Step 3.1 の CI 雛形が立てば自動化される)

## Phase 5 への申し送り (Step 3.0 由来)

- adapter なし設計でスキル本体を作る (`framework-shape.md` §5 改訂版 + 本 Step §5 運用契約)
- `project-context.md` (人間正本) → `project-context.json` (機械正本) の変換責務はスキルの補佐 Agent 経路で担う (qgb 本体は schema 検証のみ)
- 言語ソース以外の対象 (Markdown / プロンプト集 / 設定群 / 法務テンプレ等) でもスキルが動くことを `examples/markdown-docs/project-context.{md,json}` が few-shot として示す
- スキルは対象を Read で読み、`project_context.human_reviewed=false` のときは人間に確認を求める運用にする (P8 境界)
- ALLOW/DENY の根拠に LLM 評価を絶対に入れない (P6、`basis[]` は REQ / CONTRACT / POLICY / WAIVER のみ)

## 関連ファイル

- prejournal: `development/docs/journal/phase3-step3-0-prejournal.md`
- spec 改訂: `development/docs/{requirements_and_development,detailed-design,framework-shape,stage-design,phase1-manual}.md`、`CLAUDE.md`
- 新設 schema: `qgb/schemas/project-context.schema.json`
- 新設テスト: `tests/test_project_context.py` (23 件) + `tests/test_step9_docs.py` の regression test 4 件
- 記入例: `examples/python-cli-pytest/.quality-system/{project-context.json,knowledge/project-context.md}` + `examples/markdown-docs/.quality-system/{project-context.json,knowledge/project-context.md}`

## 作業プロセス記録 (timeline)

本 Step は 1 セッションで完了。リポジトリ移送 (OneDrive → Desktop) 直後の状態確認から Step 3.0 完結まで連続で進めた。後続 Step / Phase 5 着手時に時系列を遡れるように記録する。

### Timeline

| 時刻 (JST) | 出来事 | コミット |
|---|---|---|
| 2026-06-20 20:30 頃 | セッション開始、リポジトリ把握 (731 件テスト確認) | — |
| 2026-06-20 21:00 頃 | メモリ移送 (OneDrive → Desktop、7 ファイル) | — |
| 2026-06-20 22:00 頃 | チャットログ移送 (46MB jsonl + サブディレクトリ、同名コピー) | — |
| 2026-06-20 23:00 頃 | Phase 3 着手順 Codex 相談 (1 周目) → Step 3.1 推奨確定 | — |
| 2026-06-21 02:00 頃 | Step 3.1 設計境界 Codex 相談 (2 周目) → memory cap WONTFIX 確定 | — |
| 2026-06-21 03:00 頃 | **user 指摘「Phase 4 ガウディの塔疑惑」**で計画再点検開始 | — |
| 2026-06-21 03:30 頃 | Claude 1 回目誤判断: adapter 廃止 (Phase 5 LLM 判定案) → user 受け入れず | — |
| 2026-06-21 03:40 頃 | Claude 2 回目誤判断: adapter 残す (P7 のため機械側) → user 「ユーザーが作るのは必ずしもプログラミング言語のプログラムとは限らない」で再廃止 | — |
| 2026-06-21 04:00 頃 | user 提案で project-context.{md,json} 二重ファイル設計に到達 | — |
| 2026-06-21 04:15 頃 | Phase 3 全面再構築 Codex 横断レビュー (3 周目) → 案 D + Codex 指摘 3 件確定 | — |
| 2026-06-21 04:30 頃 | spec 改訂 commit | `ada386b` |
| 2026-06-21 05:00 頃 | prejournal commit | `b0f8e4e` |
| 2026-06-21 06:00 頃 | Step 3.0 本体実装 commit | `59e6042` |
| 2026-06-21 23:00 頃 | 段 1 subagent 並列 5 観点レビュー → 重大 spec-drift 6 件発見 | — |
| 2026-06-21 23:20 頃 | 段 3 Codex 横断レビュー (4 周目) → 4 commit 分割推奨 + 案 X / 案 Q + 段 1 見落とし 2 件 | — |
| 2026-06-21 23:40 頃 | **user 指摘「作業量増えたから Step 分けるな」** → サブステップ分割でなく commit サイクル分割で対応 | — |
| 2026-06-22 00:00 頃 | Step 3.0a (CLAUDE.md) commit | `6bf4a23` |
| 2026-06-22 00:20 頃 | Step 3.0b (canonical specs + 運用契約) commit | `1507446` |
| 2026-06-22 00:40 頃 | Step 3.0c (user manual + tests + regression) commit | `d70f5d5` |
| 2026-06-22 00:55 頃 | Step 3.0d (markdown-docs example) commit | `4ec20aa` |
| 2026-06-22 01:03 頃 | 段 5 Codex 2 周目 (1 回目タイムアウト → context 圧縮版で再送) → 「指摘なし収束」 | — |
| 2026-06-22 01:30 頃 | Step 3.0 完結 commit + push | `cccc9d7` |

### Codex セカンドオピニオン 4 周の内訳

各 round の決定打を別途記録する (memory `codex-context-files` の運用ログ補強として)。

| Round | 目的 | 主要決定打 |
|---|---|---|
| 1 | Phase 3 着手順 (2026-06-20) | Phase 3a 独立 Phase 案を撤回し「Phase 3 内の前提基盤 Step 群」呼称に修正。Step 3.1 を Phase 3 最初の Step として支持 |
| 2 | Step 3.1 設計境界 (2026-06-21) | memory cap WONTFIX 妥当、CI 立てない判断妥当。Codex 指摘 3 件 (Job Object ctypes 実装最小境界、.bat quoting cmd.exe メタ文字を別扱い、temporary .bat fixture で実証) |
| 3 | Phase 3 全面再構築 (2026-06-21) | adapter 廃止 + Phase 4 廃止 + project-context 二重ファイル設計を承認。Codex 指摘 3 件 (`human_reviewed: bool` 別立て / `constraints.language` を `technologies` array に / スキル責務文言「対象判定を全て LLM に委ねる」→「対象理解は LLM、ALLOW/DENY は qgb の contract 実行結果」) |
| 4 (1 周目) | Step 3.0 補修方針 (2026-06-21) | 補修順序 3-4 commit 分割支持、案 X (phase1-manual.md は Step 3.0 に追従) 支持、案 Q (markdown-docs に project-context 追加) 支持、段 1 見落とし 2 件発見 (運用契約 / docs grep regression test) |
| 4 (2 周目) | Step 3.0 段 5 収束 (2026-06-22) | 「指摘なし収束」判定。1 回目タイムアウト → 簡略版 context で再送 → 4 質問すべて簡潔回答で収束 |

### 段 1 subagent 並列 5 観点レビューで発見した内容 (簡略)

5 subagent 並列で実施。各観点で発見した中程度以上の指摘:

- **correctness**: M-1 (`references[].path` 形式拘束なし、現実害なし) / M-2 (`is not True` 比較の意図) / M-3 (`now` injection テスト欠落) / M-4 (`datetime.now(timezone.utc)` deprecated でない確認) / M-5 (空ファイル / 空 object のテスト不足) / M-6 (`references[].path` の path-escape 検証なし)。**blocker なし**
- **P9 (単一責任)**: 責務分離は適正。中程度 2 件 (warnings 切り出しタイミング判断 / `_pick_template()` dead-weight 判断)。**blocker なし**
- **philosophy 整合**: 5 観点すべて理念整合。中程度 5 件は schema description / docstring レベルの軽微な明示強化 (B-1〜B-3 として補修反映)。**blocker なし**
- **NF-004 (Windows / BOM / cp932)**: 5 観点で適合。情報レベル 1 件のみ (schema description 内の em dash、stdout 経路ない)。**blocker なし**
- **spec-drift**: 整合事項を確認した上で **重大漏れ 6 件発見** (A 群 = blocker): CLAUDE.md / 受け入れ条件§12 / stage-design §3 / detailed-design §5.1+§9 / phase1-manual / markdown-docs example

**判明したパターン**: spec-drift 観点のレビュー価値が他観点より圧倒的に高かった。本体実装が「正しく動く」だけでなく、**「派生 docs / few-shot 教材が新仕様を反映している」** ことが Phase 5 着手前提の必須条件であることを再確認した。

### 段 5 Codex タイムアウト事故 + フォールバック

段 5 Codex 2 周目を投げたところ **2 連続で 120s タイムアウト**。コンテキストファイルが過大 (1 周目の指摘リストを全部再掲した形) だった可能性。

**フォールバック**: context file を要点のみに圧縮して再送 → 200-300 字回答で「指摘なし収束」判定を得た。

**教訓**: Phase 2 Step 2.4 で確立した「Codex sandbox 失敗時の 2 周目フォールバック」の延長として、本 Step では「**コンテキスト過大時の簡略化フォールバック**」も追加で踏んだ。memory `codex-context-files` への記録候補。

## ユーザー判断の重要転換点 4 件

本 Step は user の鋭い問いかけで方向が複数回大きく変わった。判断の系譜を記録する (Phase 5 着手時の判断スタイル再現用)。

### 転換点 1: 「Phase 4 ってほんとにいるんだろうか。ガウディの塔みたいになってないか?」

- 文脈: Step 3.1 設計境界 Codex 相談直後、CI 雛形を入れるべきか議論中
- 効果: Phase 4 (CI 連携) 全項目を WONTFIX / Phase 5 吸収 / Step 3.2 吸収に分解、Phase 4 自体を廃止する判断に至った
- Claude 学習: 「先送りされた Phase」が積み重なると本来やるべきことが見えなくなる。**実装上不要なら廃止する勇気**

### 転換点 2: 「いまやってるのは LLM と機械の責務分掌ラインを作る作業のはず。あなたが今引いたラインは妥当か?」

- 文脈: Phase 4 廃止議論で Claude が「POSIX 経路は論証で済ます」と提案した直後
- 効果: 「論証で済ます = LLM (Codex) 主観評価で qgb 品質を担保する = qgb 自身の P6 違反」と判明、CI 雛形を Step 3.1 に取り込む方向に修正
- Claude 学習: **qgb が解こうとしている問題 (LLM 主観評価で品質判定しない) を qgb 開発プロセスで自分が踏まないか** を常に点検する

### 転換点 3: 「adapter (言語判定)、ほんとにいる? ユーザーが作ろうとするものは、極端な話、プログラミング言語で構築するプログラムではないかもしれない」

- 文脈: Claude が「adapter は機械的検出だから P7」と提案した直後
- 効果: 「対象プロジェクト = プログラミング言語のソース」の暗黙仮定が崩れ、adapter 抽象自体が機能しないことが判明、Step 3.0 = detect 廃止に至った
- Claude 学習: **対象プロジェクトの広がり (ドキュメント群 / プロンプト集 / 設定群 / 法務テンプレ等) を常に念頭に置く**。philosophy P10 (段階の可変性) で既に書かれていたが Claude は読み飛ばしていた

### 転換点 4: 「作業量が増えたからという理由だけでステップを分けるんですか?」

- 文脈: Codex 4 周目が「補修 3-4 commit に分けよ」と推奨した直後、Claude が「Step 3.0.5」のような小数 Step を提案した瞬間
- 効果: **commit サイクルの分割は OK、Step 番号の分割はダメ** と境界が確定。Step 3.0a〜3.0d はサブステップでなく commit サイクルの内訳として整理
- Claude 学習: **Step は計画上の単位 (1 つの設計判断のサイクル)、commit は実装上の単位 (1 つのレビュー / push できる塊)**。両者を混同すると Step が無際限に増殖する

## memory 更新候補 (本 Step で得た知見)

`review-process` / `parallel-strategy` / `codex-context-files` への反映候補を列挙。実装は別タイミング (memory ファイル直接編集) で。

### `review-process` 候補

- **spec-drift 観点の重要度を昇格**: 5 観点並列レビューで他 4 観点が blocker なし / spec-drift だけ blocker 6 件、というケースが本 Step で発生。実装が動くことと spec / docs / 派生資料が整合していることは別、特に Phase 5 スキルが few-shot として読む対象 (CLAUDE.md / examples / stage-design 等) は重点的に見る規律を memory に追記
- **段 5 タイムアウト時のフォールバック**: Codex CLI 120s タイムアウト → 簡略版 context で再送のパターン。「実コード同梱 (Step 2.4 確立) + コンテキスト圧縮 (本 Step 確立)」を 2 系統のフォールバックとして並べる

### `parallel-strategy` 候補

- 本 Step は段 1 subagent 並列 5 観点を「重複なく回せた」(申請ゼロ、reject ゼロ)。冒頭テンプレ v3 + hook 注入 + デフォルト agent_type の組合せが安定運用フェーズに入った確認。追記は最小限で OK
- **regression test を sufficient な防衛線として組み込む観点**を追加: 本 Step の docs grep regression test は段 1 見落とし指摘から生まれたが、今後の Step (Step 3.1 process tree kill / Step 3.2 依存解決固定など) でも regression test を最初から組み込む規律にすると、段 1 で同様の盲点が起きても自動的に防衛できる

### `codex-context-files` 候補

- **コンテキスト過大時のタイムアウト対策**を追記: 1 周目で広範な指摘リストを全部入れた context は 120s 内で Codex が回答しきれない可能性がある。要約版を別途用意するパターンを 2 番目のフォールバックとして書き残す
- **「指摘なし収束」判定用の簡略 context フォーマット**: 1 周目の指摘 + 補修 commit を要点だけ並べる形 (本 Step `codex_ctx_p3_step30_cross_r2b_*.txt` が成功例)

## 本セッションの context 使用パターン

参考記録 (次セッション計画用):

- セッション開始: 0%
- リポジトリ把握 + メモリ/ログ移送完了: 8% 前後
- Phase 3 計画再構築 + Codex 相談 3 周完了: 30% 前後
- Step 3.0 本体実装 + commit: 38% 前後
- 段 1 subagent 並列 5 観点: 段 1 だけで 5〜8% 消費 (subagent 出力を Claude が読む分)
- Step 3.0a CLAUDE.md commit: 42%
- Step 3.0b〜3.0d (canonical / user manual / examples): 47% 前後
- 段 5 Codex 2 周目 + 完結ジャーナル + push: 50% 前後

**1 Step + 段 1〜5 完走 + 4 サブステップ commit を 1 セッションで完結できることが確認できた** (Opus 4.7 1M context、消費約 50%)。Step 3.1 (command runner 強化 + CI 雛形) は新規実装中心で context 消費が大きい可能性があるため、別セッションで余裕を持って着手する判断が妥当。

## Step 3.0 で確立した「再混入防止規律」(運用記録)

- **docs grep regression test 4 件** (`tests/test_step9_docs.py`): detect / adapters / run_detect / DetectionResult の現役記述を検出
- **`_ALLOWED_*_PATTERNS` 設計**: 廃止記述・履歴記録・別語 (detected_at / _detect_cycle 等) を除外して false-positive を最小化、新仕様追加時は許容リスト更新でカバーできる構造
- **CLAUDE.md 全面更新**: 次セッション以降の Claude が conversation 開始時に正しい設計を踏襲

これらは Step 3.1 以降の commit が CI 雛形 (Step 3.1 で立てる) で自動検査される土台になる。Phase 5 着手時に「いつの間にか adapter モデルに戻っていた」事故を機械的に防止する。
