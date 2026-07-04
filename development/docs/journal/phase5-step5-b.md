# Phase 5 Step 5.b 完結ジャーナル: build_skill.py (converter) 実装

- 完結日: 2026-07-04
- 着手前判断: `phase5-step5-b-prejournal.md` (commit `81c3d15`)
- 編成: **Fable 5 指揮 + sonnet subagent 実装** (Fable 5 のコーディングタスク fallback 回避)。検収は毎段階で指揮役が diff 精読 + 独立再実行
- 上位仕様: `phase5-step5-a-2.md` §6.3 (16 項目) / `skill-converter/acceptance-matrix.md` / prejournal

## 1. 成果物

- `tools/build_skill.py` (~2000 行 single file): A1' 単一正本 → dist 4 成果物の決定的 converter。検証+parse (item 1-5) + 生成 (item 6-15) + path/delete 防御 + 構文検証
- `tools/regen_golden.py` + `tools/_golden/{claude,codex}/{full,split}/` (40 files、SOURCE_DATE_EPOCH unset 系統、最終 digest `6aa670dcc859780e`)
- `tests/test_build_skill.py` (81 tests) + `tests/test_build_skill_golden.py` (3 tests) + `tests/fixtures/build-skill/` (異常系 7 種 + valid-minimal)
- 全 suite 834 passed + 3 skipped、CI matrix (Windows/Ubuntu × 3.10/3.12) green

## 2. commit chronology

| commit | 段階 | 内容 |
|---|---|---|
| `81c3d15` | prejournal | 5 段階分割 + 設計判断 5 件 (single file / epoch 検証 / golden 1 系統 / exit code / テスト命名) |
| `9457a12` | 1 | pyyaml dev extras + requirements-dev.lock 再生成 (Windows × Py3.10.11) |
| `f2aa6d3` | 2 | 検証+parse フェーズ + 異常系 fixture 7 種 + 22 tests。前セッション CLI 異常終了からの transcript 復旧 + 検収 finding 4 件 (whitelist 最終ゲート / dead branch / docstring / bare CLI fail-closed) 反映 |
| `cdaf0f8` | 3 | 生成系 (render/frontmatter/digest 8 カテゴリ/INSTALL/copy/clean build/_safe_write_bytes) + 60 tests。検収で U+FFFD 由来判定 (κ 解説の正当データ) |
| (割込) `b7d401e` | — | philosophy v2.0 (P12 新設等) を段階 4 の前に実施 — golden 再生成の重複を回避する順序判断 |
| `6808764` | 4 | golden 40 files 初生成 ({agent}/{mode} layout) + regen script + 3 tests |
| `96830cd` | 5 r1 | 5 レンズレビュー + CI 赤の fix 一括 F1-F11 |
| `11eecc7` | 5 r2 | Codex 横断の必須 3 件 + 推奨 doc 2 件 |

## 3. 段階 5 レビューの記録 (実機 fixture 先行の原則の適用形)

### 収束構造

prejournal §5 のとおり「机上 K=2 多重ラウンドを要求せず、機械検証 (build 実行 + golden + 決定性 + 異常系) を収束判定の主根拠」とした。レビューは机上でしか見つからない欠陥に絞り、**段 1 (5 レンズ並列・自己反証義務付き) → 段 2 (指揮役集約・調停) → 段 3 (Codex 横断 1 回) → fix 2 round** で完結。

### 発見と修正 (要点)

| 発見者 | 重大度 | 内容 | 修正 |
|---|---|---|---|
| **CI 実機** | Critical | `Path.read_text(newline=)` は Python 3.13-only — ローカル venv (3.13) では green、CI matrix で全滅。**段階 2 push から 6 run 連続赤を検収が見逃していた** | F1 + 実 3.10 検証を手順化 |
| レンズ 3 | Critical | digest「全入力」主張が pyyaml/Python 版数を含まない (P7)。venv/lock の pyyaml drift も実在 | F2: frontmatter 出力を stdlib serializer 化 (toolchain が出力 byte に構造的に影響不能)。カテゴリ 9 案は multi-Python golden を壊すため棄却 |
| レンズ 1 | medium | digest 連結形式の境界偽装 (衝突を実証) | F3: length-prefix 形式 + acceptance-matrix 更新 |
| レンズ 2 | Major | 全失敗種別が単一 BuildError (dccfa4a 判例の再発) | F4: 3 階層化 (SourceValidation / GenerationVerification / WritePolicy) |
| レンズ 4/5 他 | minor/low | BOM 非対称 / subprocess cp932 / body.md §3.1 の propose-context 6 field 全不一致 等 | F5-F10 |
| **Codex 横断** | 必須 3 | (a) **delete 経路の containment 欠如** (write 側 5 層 vs rmtree 無検査 — レンズ間の隙間の典型)、(b) epoch 上限 2^63-1 が datetime 変換不能 (prejournal §3.2 の当初判断の誤り、253402300799 に訂正)、(c) argparse usage error が exit 2 | round 2 全反映 |

### 設計境界 (完結時点の確定事項)

- `--check` は source 検証専用であり SOURCE_DATE_EPOCH (build 時入力) を検証しない。上限超過は build 経路で exit 2
- 生成物 header は生成 md のみ、hooks/lint verbatim copy には注入しない (JSON コメント不可 + digest カテゴリ 4/5 被覆)
- 生成物中の U+FFFD 10 件はソース (κ 解説 + lint sentinel) の忠実コピー — κ を skill 自身の文書に naive grep すると誤検出 (5.e 申し送り)
- epoch 変換は timedelta 演算 (fromtimestamp の platform 依存排除)

## 4. acceptance 判定

§6.3 item 1-15: 実装 + テストで機械検証済み (レンズ 5 適合表で 27/27、Codex 横断で残ドリフト 2 件も doc 修正済)。item 16 の CI 統合は 5.b-ci。acceptance-matrix「5.b 実装」列の ✓ セル達成。**5.b 完結**。

## 5. 申し送り

### 5.b-ci へ
- golden 比較 CI job (regen + diff、lock-integrity job と同型)
- Codex 推奨の残 2 件: BuildError 境界の完全統一 (converter self-error / OSError の分類徹底) / regen_golden の cell 列挙を metadata 由来に

### 5.c へ
- release 系統 (SOURCE_DATE_EPOCH 設定 build) の self-check 設計 (prejournal §3.3)

### 5.e へ
- κ mojibake sentinel の既知 false positive (skill 自身の文書は U+FFFD を正当に含む)
- full SKILL.md ≈ 63K のコスト差ガイド (replan #13)

### プロセス教訓 (memory 反映)
- **ローカル検証の Python 版 ≠ support matrix**: venv 3.13 で green でも matrix 最小版 (3.10) で API 欠落があり得る。push 前に `py -3.10` での実 build 確認、push 後の CI 結果確認を検収手順に含める (今回は 6 run 連続赤の見逃しが実害)
- Codex 横断は「レンズ間の隙間」(write 防御 vs delete 無防備) に強い — 観点別並列と相補的である実例

## 6. 関連

- prejournal / progress journal (完結時削除) / cross-review (`phase5-fable5-cross-review.md`) / P12 draft (`phase5-track2-charter-p12-draft.md`) / Issue #26
