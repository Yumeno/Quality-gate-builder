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
