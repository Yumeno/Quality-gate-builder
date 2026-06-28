# Phase 5 Step 5.a-2-4 着手前判断: command authoring protocol + capability-based dispatch

着手前判断確定: 2026-06-28
前提: Step 5.a 全体完結 K=2 達成 (commit `ebee96f`)
着手契機: K=2 r1 fix 進行中の user 提起「日本語文書執筆プロジェクトに qgb を適用したら .ps1 契約 command で日本語 + PowerShell 5 BOM + cp932 stdout 問題が発火」+ 「append 的章でなく構造的に解決すべき」

## 1. 経緯

K=2 r1 fix 進行中 (2026-06-28) に user が以下の論点を提起:

- philosophy P10 で「対象は必ずしもプログラミング言語のソースとは限らない (ドキュメント群 / プロンプト集 / 設定群 / 法務テンプレ)」を明示している
- それなら **日本語文書執筆プロジェクト** で qgb を導入したとき、利用者が `.ps1` 契約 command を書きたいケースが当然起きる
- そのとき PowerShell 5 + 日本語環境では BOM 必須 / Console.OutputEncoding 問題 / qgb command runner の utf-8 decode (cp932 文字化け) が発火
- 「日本語 .ps1 を使うときは BOM 付き UTF-8 + Console.OutputEncoding=UTF8」と章を増やす append 的対処では、利用者は依頼語 (「qgb 入れて」「契約段階の設計をやって」) からこの章にたどり着かない
- **設計時点で構造的に弾く / 誘導する仕組みが必要**

Claude (本対話の assistant) は Codex 設計再検討レビューを実施 (`codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt`)、Codex は以下の構成を推奨:

**(η改) = θ command authoring protocol + ι capability-based dispatch + β-lite + ζ + γ-lite + κ**

Codex の主要な視点転換:

1. **これは「日本語文書」固有問題ではない** — 「verification_type=command の生成時に runtime 規律を組み込む」という **すべての command contract 共通の invariant**。日本語 PowerShell はその 1 具体化
2. **キーワード trigger でなく、構造 trigger に変える** — 「contract が command を含む / 検査 script を新規作成する → command authoring protocol を必ず適用」
3. **「自然言語」でなく「組み合わせ」で一般化** — `script source encoding × runtime parser × process output encoding × qgb decode protocol × target OS`、runtime-specific preflight adapter で組合せ列挙でなく吸収
4. **「混ぜるな」** — K=2 r1 fix の既存 9 件には含めず、別 Step (5.a-2-4) として独立実装すべき

user が「OK」で Step 5.a-2-4 着手を承認。

## 2. 採用候補解と却下候補解 (Codex 設計再検討レビュー結果)

| 順位 | 候補 | 採否 | 評価 |
|---|---|---|---|
| 1 | **(η改): θ + ι + β-lite + ζ + γ-lite** | 採用 | 構造的、低認知負荷、A1' 整合 |
| 2 | β-lite | 採用 | context を入力に使う、利用者記入必須にしない |
| 3 | ζ | 採用 | fixture / few-shot として有効 |
| 4 | γ-lite | 採用 | design-stages の checklist として有効 |
| 5 | α-lite | 補助のみ | trigger 表は構造 trigger に統合 |
| 6 | ε (contract.encoding 追加) | 却下 | Phase 6+ 候補、Phase 5 では本体改修なし |
| 7 | δ (proposal.basis 必須化) | 却下 | proposal.basis の責務逸脱 |
| 8 | κ (mojibake sentinel) | 採用 (Codex 推奨追加) | `qgb check` 後 log の U+FFFD 検出 |

## 3. 各候補解の具体化方針

### 3.1 θ: command authoring protocol (中核)

**配置**: body.md §6 (workflow) に新節を追加

**内容**: `verification_type=command` のすべての contract に共通する生成規約:

```
1. context 取得 (対象プロジェクトの project-context.{md,json}、target OS、runtime)
2. verification type 選択 (command / file_exists / substring_match / json_schema /
   manual_check)
3. runtime 解決 (PowerShell 5 / 7 / bash / Python / Node 等を確定)
4. script / argv 生成 (runtime 規約に従う)
5. runtime-specific preflight (PowerShell なら BOM + Console.OutputEncoding 検証、
   bash なら executable bit + locale 検証 等)
6. qgb check 実行
7. evidence 確認 (stage log の U+FFFD 検出 (κ) を含む)
```

**PowerShell 5 規律 (1 具体化)**:

- argv は `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script>` 明示
- 非 ASCII を含む `.ps1` は **BOM 付き UTF-8** 必須
- stdout/stderr は qgb の utf-8 decode 契約に合わせる (`$OutputEncoding = [System.Text.Encoding]::UTF8` + `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`)
- `[Console]::OutputEncoding` 設定だけに依存せず、qgb stage log で実際に redirected stdout を byte-level または `U+FFFD` の有無で検証
- PowerShell 5 / 7 のどちらを対象にするか曖昧にしない

### 3.2 ι: capability-based dispatch (中核)

**配置**: body.md §12 (design-stages prompt) に新節を追加

**内容**: 自然言語キーワードでなく作成物性質で分岐:

| 作成物 | runtime adapter checklist |
|---|---|
| `.ps1` | PowerShell adapter checklist (BOM / OutputEncoding / argv / runtime version) |
| `.sh` | shell adapter checklist (shebang / executable bit / locale / runtime 存在) |
| Python script | interpreter / locale / PYTHONUTF8 mode / sys.stdout.reconfigure |
| Node script | runtime version / stdout encoding / locale |

adapter は **qgb 本体の対象検出として復活させない** (framework-shape §5 の境界「対象判定を qgb 本体へ戻さない」と整合)。skill 内の command authoring strategy として限定。

### 3.3 β-lite: project-context schema 拡張 (最小限)

**配置**: 既存 `.quality-system/project-context.json` schema を **拡張しない**

**方針**: 既存 `technologies` / `artifact_kinds` / `platform` フィールドで十分。skill が repo / 既存 script / runtime / 利用者回答から導出して `.quality-system/knowledge/project-context.md` に **人間可読** で runtime assumptions を記録。

JSON への新 field 追加は **out of scope** (利用者認知負荷増)。将来必要なら small optional `execution_environments[]` を Phase 6+ で検討。

### 3.4 ζ: examples/japanese-docs-pwsh/ 新設

**配置**: `examples/japanese-docs-pwsh/` 新規

**内容**:
- `design-notes.md` で encoding 規律 + θ/ι 適用例の解説
- `.quality-system/contracts/REQ-DOC-001/*.json` で `.ps1` 契約の正しい書き方
- `.quality-system/knowledge/project-context.md` で「Windows + 日本語 + 文書」対象自己定義
- `.quality-system/policy.json` で日本語文書向け段階定義 (file_exists / substring_match に加えて command 段階あり)

skill (LLM) が few-shot として参照、利用者プロジェクトに正しい設計が伝播。

### 3.5 γ-lite: review-policy 追加観点

**配置**: body.md §13 (review-policy prompt) に追加

**内容**: advisory review 時の補助確認として「command 契約の runtime 規律が proposal に組み込まれているか」を観点に追加。**主防御 ではない** (主防御は workflow + design-stages)。

### 3.6 κ: mojibake sentinel

**配置**: body.md §13 に追加 + 5.a-2 完結 journal §6.6 dogfood シナリオに追加

**内容**: `qgb check` 後に stage log の **U+FFFD (replacement character)** 検出を LLM レビュー観点 + dogfooding 確認項目として追加。安価で cp932→UTF-8 誤 decode の多くを検出可能。

### 3.7 α-lite: trigger 表は構造 trigger に統合

**配置**: body.md §2 trigger 表は **変更しない** (K=2 r1 fix #1 / #2 で mode-neutral 化済、改めて keyword 追加しない)

**方針**: 「日本語」「Windows」「.ps1」等のキーワード列挙でなく、利用者が「契約段階を作って」「policy.json を設計して」と依頼した時点で trigger 表 → design-stages (§12) → command authoring protocol (§6) → capability-based dispatch (§12 内 checklist) という構造 trigger で誘導。

## 4. 既存実装への影響度 (Codex 評価より)

| 対象 | 影響 |
|---|---|
| `body.md` §6 / §12 / §13 | 中〜大 |
| `metadata.yaml` / `metadata.schema.json` | なし |
| `agent hooks` | なし |
| converter / A1' | なし |
| `examples/` | 中 (新規 example 1 件追加) |
| qgb core / schema | **なし** (Phase 5 では本体改修しない、ε 候補は Phase 6+) |
| 5.b 着手前提 | 既存 K=2 達成済の 5.b 責務 16 項目に θ/ι 関連 lint 項目を追加する可能性あり |

## 5. サブステップ構成

| サブステップ | 内容 | 規模 |
|---|---|---|
| 段階 1 | prejournal 風設計判断記録 (本書) | 0.3 |
| 段階 2 | body.md §6 に command authoring protocol 追加 | 0.5 |
| 段階 3 | body.md §12 に capability-based dispatch checklist 追加 | 0.7 |
| 段階 4 | skill 内 lint helper script 新設 (PowerShell + cross-platform) | 0.5 |
| 段階 5 | examples/japanese-docs-pwsh/ 新設 | 1.0 |
| 段階 6 | body.md §13 に κ + 5.a-2 完結 journal §6.6 dogfood 更新 | 0.3 |
| 段階 7 | 5.a-2-4 完結 journal 作成 + 5.a-2 完結 journal §2 旧→新対応表に追記 | 0.5 |
| 段階 8 | 完結後 K=2 (5.a-2-4 単独レビュー、Step 5.a 全体 K=2 達成済なので別系統) | 0.5〜2.0 |

合計規模: 4.3〜5.8 (5.a-2 全体規模 2.0〜3.0 を超える、Step 5.a-2-4 単独で大きい)

## 6. 失敗時の rollback 方針

各段階で個別 commit + push、各段階完了で pytest 緑確認。失敗パターンと回復:

| 失敗 | 回復 |
|---|---|
| 段階 2 / 3 (body.md 構造変更) で test_step9_docs.py keyword 喪失 | keyword 追補で復旧、構造変更は維持 |
| 段階 4 (lint script) の動作不能 | script 修正、template として fall back |
| 段階 5 (examples 新設) の policy.json / contract 整合性破綻 | `qgb validate-policy` で blocker 確認、example 修正 |
| 段階 6 〜 段階 7 (journal 更新) で既存 journal の整合性破綻 | 該当 commit を git revert、journal 修正版を別 commit で再投入 |
| 段階 8 (K=2) で新規必須 fix 多数発見 | K=2 r1 〜 r6 と同じ流れで反映、収束まで継続 |

## 7. K=2 達成条件 (本 Step の完結基準)

Step 5.a 全体 K=2 r6 達成済の運用基準 (「実際のプロジェクトとして動かしたときに運用上問題ない / 複数実装あり得るがどちらでもよい」) を継承:

- Codex 横断レビューで **新規必須 fix 0 件**
- 5.b 送り / Phase 6+ 送りは新規 finding ゼロに含めて構わない (Codex 判定済)

Step 5.a 全体 + Step 5.a-2-4 が両方 K=2 達成した時点で **Step 5.a 系列完結**、Step 5.b 着手可。

## 8. 関連ファイル

- prejournal v4: `development/docs/journal/phase5-prejournal.md`
- Step 5.a-2 完結 journal: `development/docs/journal/phase5-step5-a-2.md`
- Codex 設計再検討レビュー context: `codex_ctx_p5_step5a-2-x_jp-docs-design_review_20260628-180821.txt`
- 中間表現: `skills/source/body.md` + `metadata.yaml` + `metadata.schema.json` + `README.md` + `hooks/`
- 上位仕様 (A1' 反映済): `framework-shape.md` §5 + `requirements_and_development.md` §F-019 / §C-008
- 既存 example: `examples/markdown-docs/`, `examples/python-cli-pytest/`, 他 4 件
