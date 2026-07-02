# Phase 5 Step 5.b Prejournal: build_skill.py (converter) 実装

- 作成日: 2026-07-03
- 作成者: Claude Fable 5 (指揮役。実装は sonnet subagent に委任する編成 — Fable 5 のコーディングタスク fallback 回避のため)
- 前提: Step 5.a 系列全完結 (5.a-0 / 5.a-1 / 5.a-2 / 5.a-2-3 / 5.a 全体 K=2 / 5.a-2-4 実機証跡完結 `1449e5e`)、Fable 5 横断レビュー Track 1 消化済 (`44159cd` / `a65c6c5`)
- 上位仕様: `phase5-step5-a-2.md` §6.3 (16 項目) / `development/docs/skill-converter/acceptance-matrix.md` (deterministic build 契約 + digest 構成) / `framework-shape.md` §5 / F-019 / C-008

## 1. スコープ

`tools/build_skill.py` を本実装し、`skills/source/` (A1' 単一正本) から `dist/skills/{full,split}/{claude,codex}/` の 4 成果物を決定的に生成する。golden fixture + 異常系 fixture + テストを同時に整備する。

**含めない** (別 Step):
- CI への golden 比較 job 統合 (5.b-ci)
- GitHub Releases へのアタッチ (5.c)
- canary / dogfood (5.d / 5.e)

## 2. 確定済み設計判断 (上位仕様から継承、再議論しない)

1. **acceptance は §6.3 の 16 項目すべて** (metadata validate / converter_min_version 比較 / agent status fail-closed / marker grammar 完全固定 / full・split 生成 / agent 別 frontmatter / 生成物 header / INSTALL.md / hooks 同梱 (AGENT_TO_HOOK_DIRNAME mapping) / 構文検証 / deterministic ordering / clean build / 出力 / golden 検証)
2. **build_input_digest は 8 カテゴリ** — 正本は `acceptance-matrix.md` 「build_input_digest の構成」節。**5.a-2 journal §6.3 item 9 の「7 カテゴリ」記載は stale** (5.a-2-4 K=2 r1 fix #5 でカテゴリ 5 = lint 同梱ファイルが acceptance-matrix に正本化された後、journal 側は歴史記録として未更新)。実装は 8 カテゴリに従う: (1) metadata.yaml (2) metadata.schema.json (3) source_files (4) 同梱 hook (5) 同梱 lint (6) agent docs (7) converter 実装自身 (8) SOURCE_DATE_EPOCH
3. **source_commit_hash は埋め込まない** / 生成日時は SOURCE_DATE_EPOCH 設定時のみ (golden 自己参照回避 + reproducible-builds 規約)
4. **path 防御**: clean build default + lstat 存在確認 + exclusive create (`O_CREAT|O_EXCL`) + POSIX では `O_NOFOLLOW` 併用 + `fstat(fd).st_nlink == 1` sanity。親 dir symlink race は脅威モデル外 (Phase 6+ 再評価)
5. **fixture 二系統**: `tools/_golden/{claude,codex}/{full,split}/` (byte 一致) と `tests/fixtures/build-skill/` (異常系 7 種: duplicate-marker / unclosed-marker / nested-marker / path-traversal / case-collision / source-output-collision / empty-helper)
6. **pyyaml>=6,<7 を dev extras に追加** (converter は開発/CI 文脈のツール、qgb runtime 依存には加えない = NF-010 維持)。`requirements-dev.lock` の再生成が必要 (Phase 3 Step 3.2 規律、Windows × Python 3.10、`SECURITY.md` "How to Update" 手順)

## 3. 本 prejournal での新規設計判断

### 3.1 converter は single file (`tools/build_skill.py`)

digest カテゴリ 7 は「single file または package」の両様を許すが、**Phase 5 は single file で確定**。理由: (a) digest 境界が自明になり、K=2 r5 で 5.b 送りになった「single-file/package converter source 列挙の境界テスト」が「`tools/build_skill.py` 1 ファイルを読む」に縮退して解消する、(b) 依存は stdlib + pyyaml のみで package 化の必然がない、(c) Phase 5 skill への few-shot として「1 tool = 1 file」が読みやすい。将来 package 化する場合は digest カテゴリ 7 の列挙規則 (`tools/build_skill/**/*.py` 辞書順) を同時に有効化し golden を再生成する。

### 3.2 SOURCE_DATE_EPOCH の形式検証 (K=2 r5 5.b 送りの解消)

設定されている場合: 10 進非負整数文字列のみ受理 (先頭 +/-、空白、小数、16 進を reject)。範囲は 0 〜 2^63-1。違反は build refuse (fail-closed、exit 2)。digest カテゴリ 8 には検証通過後の正規化値 (int → str) を記録する。

### 3.3 golden 系統は通常 build (SOURCE_DATE_EPOCH unset) の 1 系統のみ commit (K=2 r5 5.b 送りの解消)

acceptance-matrix は「通常系統 = standard、release 系統 = release artifact 検証用」の 2 系統を許すが、**repo に commit する golden は unset 系統のみ**。release 系統 (epoch 設定) は 5.c の release CI 内で「build 直後に同一入力で再 build して byte 一致」の self-check で検証する (golden の二重保守を避ける)。5.c prejournal で再確認。

### 3.4 exit code 規約

qgb 本体 CLI と同型: 0 = build 成功、2 = 入力不正 / 検証失敗 (fail-closed)、64 = usage error。DENY 相当 (1) は converter に存在しない。

### 3.5 テスト配置

`tests/test_build_skill.py` (単体: parser / digest / 変換) + `tests/test_build_skill_golden.py` (golden byte 一致 + 異常系 fixture)。命名は機能ベース (Fable 5 レビュー D-4 の方針を新規ファイルから適用)。

## 4. 実装段階分割 (additive-first、各段階 = subagent 1 走 + 指揮役検収 + commit)

| 段階 | 内容 | 完了基準 |
|---|---|---|
| **1** | pyyaml dev extras 追加 + `requirements-dev.lock` 再生成 (Windows × Py3.10、SECURITY.md 手順) + lock-integrity テスト green | `pytest tests/test_lock_integrity.py` 全 pass + `pip install -e .[dev]` 成立 |
| **2** | converter 骨格 + metadata validate + marker parser (§6.3 item 5 の grammar 全規則) + 異常系 fixture 7 種 + parser 単体テスト | 異常系 7 種すべて fail-closed (exit 2 + 明確な error message)、正常 parse で 4 marker 抽出 |
| **3** | 生成系: full/split render + agent 別 frontmatter + 生成物 header (digest 8 カテゴリ) + INSTALL.md + hooks/lint copy + clean build + path 防御 + 構文検証 | ローカル build で 4 成果物生成、同一入力 2 回 build で byte 一致 (決定性の自己検証) |
| **4** | golden fixture 生成 (`tools/_golden/`) + golden byte 一致テスト + SOURCE_DATE_EPOCH 検証テスト | 全 pytest green (既存 753+ 件も回帰なし) |
| **5** | レビュー (下記 §5) + fix + 完結 journal | レビュー消化 + journal commit |

段階 1 が最も環境依存 (Python 3.10 + pip-tools)。subagent には「py -3.10 が無い場合は生成せず報告して停止」を明示する (誤環境 lock は supply-chain 規律違反)。

## 5. レビュー計画

- **実機 fixture 先行の原則の適用**: converter は決定的な純 Python ファイル変換であり、「実機」に相当するのは **実際に build を走らせて golden / 決定性 / 異常系を機械検証すること**。これを段階 2〜4 の完了基準に組み込み済み (テストが先、レビューが後)
- 段 1 (観点別 subagent 並列) は段階 5 で実施: correctness / P9 / philosophy (P7 再現性・C-008) / NF-004 (Windows path・encoding) / spec-drift (acceptance-matrix / §6.3 16 項目との突合) の 5 レンズ
- 段 3 Codex 横断: 1 回 + 必要 fix。**机上 K=2 の多重ラウンドは要求しない** (5.a-2-4 の教訓: 機械検証可能な領域では実機証跡が上位。golden + 異常系 + 決定性テストが green である事実を収束判定の主根拠とする)
- 削除を含まない additive Step のため codex-review-multi-round (r0/r1/r2) は不適用

## 6. リスクと手当て

| リスク | 手当て |
|---|---|
| lock 再生成の環境不一致 (Py3.10 不在) | 段階 1 で fail-fast、user に報告して環境判断を仰ぐ |
| marker grammar の解釈ずれ | §6.3 item 5 を prompt に全文引用して委任、検収で仕様条項と 1:1 突合 |
| digest の canonical 順ずれ | acceptance-matrix の連結フォーマット (`<cat>\n<path>\n<content>\n`) を prompt に引用、テストで「入力 1 byte 変更 → digest 変化」を検証 |
| Windows で `O_NOFOLLOW` 不在 | 仕様どおり accept (clean build + lstat + exclusive create のみ)、INSTALL.md に明示 |
| body.md 63K の header 挿入位置 | 生成物 header は frontmatter の後・本文の前に HTML コメントで挿入 (YAML parse を壊さない)。段階 3 で構文検証により機械確認 |

## 7. 5.b 完結条件

- §6.3 16 項目のうち 5.b 担当分 (1〜15) が実装 + テストで機械検証済み (16 の CI 統合は 5.b-ci)
- acceptance-matrix の「5.b 実装」列の ✓ セルすべて達成
- 全 pytest green (回帰なし)
- 完結 journal (`phase5-step5-b.md`) 起草
