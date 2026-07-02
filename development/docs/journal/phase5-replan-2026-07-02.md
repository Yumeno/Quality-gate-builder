# Phase 5 実装計画修正案 (Fable 5 横断レビュー反映)

- 作成日: 2026-07-02
- 作成者: Claude Fable 5 (レビュー実施者本人による計画化)
- 前提文書: `phase5-fable5-cross-review.md` (レビュー本体、Part F に全 13 アクション)
- 実行者想定: **Opus 4.7** (Fable 5 はコーディングタスクでフォールバックの可能性があるため、実装は Opus 4.7 へ引き継ぐ。本書はその引き継ぎを成立させるための計画書)
- 本書の位置づけ: 提案。採否は user 判断。採用後は本書の Track 構成が Step 5.a-2-4 完結〜5.b 着手の正式な作業順序になる

## 0. 設計判断の要約 (なぜこの構成か)

1. **レビュー反映を「5.b をブロックするもの / しないもの」で二分した。** 判断基準は「初回 dist に乗ると実害があるか」。pip install 記述 (供給網リスク) と lint PS 実装の未検証 (完結判定の根拠の穴) は乗ると実害がある → Track 1 (完結処理に合流)。憲章改訂系は乗らなくても実害がない → Track 2 (独立、非ブロッキング)。
2. **憲章改訂を 5.b の前提にしない根拠**: A1' 設計 (body.md 単一正本 + converter 再生成) により、憲章改訂後のスキル再ビルドは安価。改訂を待つ機会費用の方が高い。これは A1' アーキテクチャ自身が保証している性質であり、「憲章改訂 → skill version bump で吸収」が正規経路。
3. **D-2 (lint PS 実装の fixture 検証) を Step 5.a-2-4 完結の前に置く根拠**: 完結判定の論理は「実機証跡による運用基準達成」だが、現状の実機証跡は Python 実装のみを検証している。Windows native 利用者が実際に走らせるのは PS 実装であり、**検証されていない側を含んだまま「実機で担保」を宣言すると完結判定の根拠が崩れる**。K=2 の歴史 (r2 fix #1 = PS 空配列 collapse、r3 fix #3 = casing parity) が示すとおり parity バグはこの二重実装の主要欠陥クラス。

## Track 1: Step 5.a-2-4 完結処理 (拡張版) — Opus 4.7 の最初の作業

順に実行。1→2 はコード + 文書、3〜5 は文書のみ。

### 1-1. D-2: 実機 fixture を lint PS 実装にも適用 (コーディングタスク)

**対象**: `tests/fixtures/lint_command_contract/run-tests.ps1`

**要件**:
- 各 fixture (A1〜A4 / B1〜B3 の 7 件) を **Python 実装と PowerShell 実装の両方**に流す
- 両実装で (a) exit code が期待値と一致、(b) 期待 substring (lintMustContain / lintMustNotContain) を満たす、(c) **両実装の exit code が互いに一致** することを assert
- Summary 表を `lint-py / lint-ps / real` の 3 列に拡張

**実装ガイド (Fable 5 から Opus への具体的申し送り)**:
- PS 実装の呼び出し形: `powershell -ExecutionPolicy Bypass -NoProfile -File skills/source/lint/check-command-contract.ps1 -Contract <contract.json>` (cwd を fixture root にして呼ぶ点は Python 側と同じ。`Invoke-Lint` を `-Implementation py|ps` パラメータ化するか、`Invoke-LintPs` を並置)
- **既知の罠 1**: PS5 は native command の stderr 行を ErrorRecord 化する。既存 `Invoke-Lint` が使っている temp file 経由の stderr 分離 (`2>$tmpErr`) をそのまま踏襲する
- **既知の罠 2**: message text の実装間差異。Python は `§6.5`、PS は `sec 6.5` と表記が割れている (PS1 ファイルは pure ASCII 維持のため)。expectations の substring は両実装に共通する部分 (`C3:` / `FAIL` / `OK` 等) に限定するか、実装別 expectation を持つ。**メッセージ完全一致は要求しない** (ASCII 制約は意図的なので、一致必須は誤り)
- **既知の罠 3**: fixture B 系での -File 前後判定・排他判定は位置依存ロジック。両実装の finding **種別** (C2/C3 の別) が一致することまで確認する
- 完了基準: `run-tests.ps1` 1 回の実行で 7 fixture × 2 実装 × 実機 = 21 判定が全 PASS
- ずれが出た場合: それは本物の parity バグ。lint 実装側を修正する (fixture 側を緩めない)。修正は Python/PS 両方に同時適用 (Step 5.a-2-4 K=2 の教訓)

### 1-2. D-1 + D-3: body.md 修正 (文書タスク、1 commit)

**対象**: `skills/source/body.md`

- **§10.1 の `pip install quality-gate-builder` を撤去**。書き換え案:

  ```markdown
  ### 10.1 「qgb がない」「python -m qgb で動かない」

  利用者プロジェクトに qgb が installed されていない可能性。**qgb は利用者プロジェクトに同梱されず、PyPI にも公開されていない。** リポジトリを取得して editable install する:

  ```bash
  git clone https://github.com/Yumeno/Quality-gate-builder.git
  pip install -e ./Quality-gate-builder
  ```

  `pip install quality-gate-builder` は **実行しない** (PyPI 未公開のため、同名パッケージが存在した場合それは qgb ではない)。
  ```

  最後の一文が重要 (squatting 防御を利用者 agent に教える)。将来 PyPI 公開したらこの節を更新する。
- **line 713 の typo `chcek` → `check`**
- **PyPI 名の防衛的確保**は repo 外の作業 (user のアカウント操作が必要)。user 判断事項として残す。確保する場合、空の placeholder package を上げるのが通例

### 1-3. 完結 journal 更新

**対象**: `development/docs/journal/phase5-step5-a-2-4.md`

- §3 commit chronology に追記: `b29ceef` (実機 fixture + lint bug 修正)、Track 1-1/1-2 の commit
- §1 確立した境界に追加: 「実機 fixture 検証による運用基準担保」— 机上 K=2 が収束しないまま (5→5→4→1→2→2)、実機証跡で決着した経緯と、それが P6/P7 に忠実である論理を明記
- Fable 5 横断レビュー (`phase5-fable5-cross-review.md`) への参照を追加 (D-1/D-2/D-3 が本 Step の完結前 fix として合流した経緯)

### 1-4. memory 更新

- ✅ `review-process` への「実機 fixture 先行の原則」追記は **Fable 5 が 2026-07-02 に実施済み**
- Opus は追加で「PS5 test runner の罠」(null array / ErrorRecord 化 / stdout+stderr 分離) を `windows-bom-encoding-rules` 拡張または新規 memory として記録するか判断 (run-tests.ps1 のコメントに既に書いてあるので、memory 化は任意)

### 1-5. Step 5.a-2-4 完結 commit + 進行中 journal の削除

- `phase5-step5-a-2-4-progress.md` (compact 跨ぎ用) は完結時に削除する (framework-shape「一度限りの引き継ぎ資料を残さない」に従う。git 履歴には残る)
- 完結 commit で task #96 / #104 を completed 化

## Track 2: spec-review (憲章改訂) — user 判断先行、5.b を待たせない

**対象 3 件** (レビュー Part A-3 由来):

| 件 | 改訂種別 | 内容 |
|---|---|---|
| P12 候補 (validation 限界の明示) | **メジャー** | 「要求の妥当性は人間の責務、qgb は床を提供しない」を不易として追加 |
| P6 根拠の付け替え | マイナー | 揺らぎ論 → P7 (監査可能性・再現性) からの導出に書き換え |
| 3〜7 レンジの降格 | 要影響評価 | P10 適用節から stage-design.md へ移動 |

**進め方**:
1. user が採否と時期を判断 (本書はスケジュールに含めない)
2. 採用する場合、philosophy.md §6 の改訂手続き (Issue 起票 + 影響評価 + 版番号 v1.1 or v2.0)
3. **影響先の目録** (影響評価の初期リストとして): `philosophy.md` 本体 → `requirements_and_development.md` §3.2/§5.4 の対応表 → `skills/source/body.md` §3 (絶対遵守 4 原則) と §7.3 / prompts 内の P 番号引用 → `qgb/core/proposal.py` の philosophy_anchors → `examples/*/design-notes.md` の P 参照 → CLAUDE.md
4. 改訂後、5.b 完了済みなら skill version bump + 再ビルドで吸収 (A1' の正規経路)

## Track 3: Step 5.b (build_skill.py) — 従来計画 + 追加 2 点

前提: Track 1 完了 (Track 2 は前提にしない)。

従来計画 (5.a-2 完結 journal §6.3 の 16 項目 + lint 同梱 + digest 8 カテゴリ + golden fixture) に以下を追加:

- **#13**: full/split モードのコスト差 (full SKILL.md ≈ 63K = 発火ごと約 16k tokens) を dist の利用者ガイドに明示、split を実質推奨として書く
- **fixture 流用**: `tests/fixtures/lint_command_contract/` を 5.b の golden/regression に流用 (従来計画どおり)。Track 1-1 完了後は両実装 parity 検証込みで流用できる

## Track 4: バックログ優先度更新 (記録のみ、着手しない)

| 項目 | 記録先 | 優先度変更 |
|---|---|---|
| waiver expiry / contract-hash 変更検知 | Phase 3 Step 3.3 バックログ | 「Phase 5 実需待ち」→「Phase 5 中に評価」へ昇格 (レビュー A-3-3: 規律の網で唯一時間軸に無防備) |
| `human_attestation` 型 | stage-design §13 バックログ | 同上 (manual_check の受け皿不在の解消) |
| human_reviewed 承認時の提示内容 digest 記録 | proposal/adopt 経路バックログ | 新規登録 (レビュー A-3-4) |
| qgb 自身の dogfooding (REQ-QGB-XXX) | Phase 5 後半以降の構想 | 新規登録 (レビュー A-4。5.b の build 検証を REQ 化する形が有力) |
| テストファイル命名の機能ベース化 | 低優先 | 新規登録 (レビュー D-4) |

記録先の実体: 本書 + cross-review journal で足りる (要件定義書 §13 Step 3.3 の項目列挙は「Phase 5 実需で取捨」と既に書かれており、優先度の詳細まで spec に書くのは過剰)。

## 5. Opus 4.7 引き継ぎチェックリスト

**切替後の最初のセッションで読むべきもの (順)**:
1. 本書 (`phase5-replan-2026-07-02.md`)
2. `phase5-fable5-cross-review.md` Part F (アクション一覧) — 詳細根拠が必要なら該当 Part
3. `phase5-step5-a-2-4-progress.md` (compact 跨ぎ journal、現在地の確認)

**動作確認を兼ねた最初のタスク**: Track 1-1 (D-2)。理由: (a) スコープが 1 ファイルに閉じている、(b) 完了基準が機械的 (21 判定 PASS)、(c) 実機 PowerShell 操作 + Edit + expectations 調整という質の異なる操作を含むため、Opus 4.7 の作業成立性の確認材料として適切。

**注意事項の引き継ぎ**:
- pytest の Bash/PowerShell 背景化問題 (memory `pytest-bash-bg-pattern`)
- git は add / commit / push 個別呼び出し (memory `bash-permission-patterns`)
- BOM 付きファイルは Write tool でなく PowerShell `[System.IO.File]::WriteAllText` + `UTF8Encoding($true)` (memory `windows-bom-encoding-rules`)
- run-tests.ps1 は `$ErrorActionPreference = 'Continue'` 必須 (Stop だと native stderr で停止する — ファイル冒頭コメント参照)

## 6. 本書自身の扱い

Track 1〜4 がすべて消化された時点で、本書は役目を終える。cross-review journal (レビュー本体) は歴史記録として恒久保存、本書 (計画) は完結時に削除するか「完結済み」注記を付ける — Step 5.b 完結処理時に判断。
