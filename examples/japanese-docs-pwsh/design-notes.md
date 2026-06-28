# design-notes.md — japanese-docs-pwsh

本 example が設計判断としてどのような選択をしたか、そして Phase 5 Step 5.a-2-4 で確立した **command authoring protocol (θ) + capability-based dispatch (ι)** をどう適用しているかを記録する。

## 設計判断の核

### なぜ 4 段階か (philosophy P10 段階数 3-7 推奨レンジ内)

- S1 link 整合性: 文書群の最低限の一貫性 (壊れた link が残らない)
- S2 用語統一: 旧称 / 禁止表記の排除 (用語表に基づく機械検査)
- S3 style 規約: 見出し階層の連続性 (H1 → H3 のスキップなし、H1 唯一)
- S4 起点ファイル存在: 起点 (`docs/README.md`) の存在 + H1

これは「文書群の最低限の構造 + 用語の一貫性」を 4 つの独立した責務で機械化したもの。philosophy P9 (単一責任) 遵守、各段階 1 文の `responsibility` で表現可能。

5 段階以上にする選択肢 (例: external link 404 検査、wordcount 下限、AST 検査) はあり得るが、本 example は **「最頻ケースの 4 段階」** を提示する fixture として最小性を維持。

### なぜ S1-S3 を command 種別 + PowerShell 5 で書くか

文書系の検査 (link 整合性 / 用語統一 / heading 階層) は qgb 内蔵の `file_exists` / `substring_match` / `json_schema` では機械化できない。**任意の logic を script で書く必要**。

PowerShell 5 (Windows 同梱) を採用する理由:

1. 利用者ベース (法務 / 行政 / 教育機関 / 国内エンタープライズ) は Windows + PowerShell 5 がデフォルト
2. Python install 強制を避けたい (qgb 本体は Python だが、利用者 script は別)
3. Phase 5 NF-004 (Windows PowerShell first-class) との整合

PowerShell 7 / Python / Node / bash を採用する選択肢もあるが、利用者の install 前提を最小化するため PS 5 を default。利用者が PS 7 や Python を既に install 済なら本 example の script はそのまま動く (PS 7 は BOM なし `.ps1` でも UTF-8 を正しく読む) か、`runtime` field を変更して再実装する。

## θ command authoring protocol の適用例

本 example の contract 起草は以下の流れ (body.md §6.5 の 7 step に従う):

1. **context 取得**: project-context.json で OS=Windows / shell=powershell-5 / locale=ja-JP を確定
2. **verification type 選択**: 文書検査ロジックが任意なので `command` 種別必須 (file_exists / substring_match では機械化できない)
3. **runtime 解決**: PowerShell 5 (Windows 同梱、`powershell.exe`) に確定
4. **script / argv 生成**: 各 `.ps1` を起草、argv は `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script>` 完全明示
5. **runtime-specific preflight (ι)**: body.md §12.5.5 PowerShell 5 checklist 適用
   - script の保存 encoding: **pure ASCII + Unicode escape**で書くことで BOM 不要
   - 各 script 冒頭で `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + `$OutputEncoding = [System.Text.Encoding]::UTF8` + `$ErrorActionPreference = 'Stop'`
   - 改行 LF (`.gitattributes` の `*.ps1 text eol=lf` 強制で自動適用)
6. **qgb check リハーサル**: `python -m qgb check REQ-DOC-001` で artifacts/REQ-DOC-001/checks/<ts>/ に揮発出力、stage log で `U+FFFD` (mojibake sentinel) 検出
7. **evidence 確認**: stage log を Read、日本語 stdout が正しく UTF-8 で読めることを目視確認

## ι capability-based dispatch checklist の PowerShell 5 セクション適用

本 example の `.ps1` script は body.md §12.5.5 「PowerShell 5 / 7 (Windows native)」checklist の各項目を以下のように満たす:

| checklist 項目 | 本 example の実装 |
|---|---|
| script 保存 encoding | **pure ASCII + Unicode escape** を採用 (BOM 付き UTF-8 の代替策)。日本語 string が必要な箇所は `[char]0x<codepoint>` で構築。これにより Write tool で書ける + PS 5/7 両対応 + BOM 不要 |
| script 改行コード | LF (`.gitattributes` で `*.ps1 text eol=lf` 強制済) |
| 冒頭設定 | `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` + `$OutputEncoding = [System.Text.Encoding]::UTF8` + `$ErrorActionPreference = 'Stop'` を全 script 冒頭で設定 |
| argv | `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <script>` 完全明示 (各 contract.json) |
| profile load 回避 | `-NoProfile` 指定 |
| execution policy | `-ExecutionPolicy Bypass` 指定 (CI 環境で利用者 policy 設定に依存しない) |
| 文字化け検出 | qgb check 後の stage log で `U+FFFD` を grep (skill が `skills/source/lint/check-command-contract.{ps1,py}` で機械検査) |

## pure ASCII + Unicode escape を採用する理由 (BOM 付き UTF-8 の代替)

PowerShell 5 + 日本語コメント / string の `.ps1` を書く方法は 2 つ:

1. **UTF-8 BOM 付きで保存** — 自然な日本語コメント / string をそのまま書ける、PowerShell 5/7 両対応
2. **pure ASCII script source + Unicode escape (`[char]0x<codepoint>`) で日本語 string を構築** — script ファイル自体は ASCII のみ、PS 5/7 両対応、BOM 不要

本 example は **(2) pure ASCII + Unicode escape** を採用。理由:

- Write tool (skill agent が script を起草する経路) は BOM なし UTF-8 で書き込む。BOM 付き UTF-8 で出力するには `[System.IO.File]::WriteAllText(..., UTF8Encoding(true))` 等の PowerShell 経由が必要 (二段階処理)
- pure ASCII script は **どの encoding でも parse 失敗しない** (cp932 / UTF-8 / UTF-16 すべて同一 byte 列)
- 日本語 string が必要な箇所は限定的 (本 example では label 文字列のみ)、Unicode escape の不便さは許容範囲

利用者プロジェクトで **大量の日本語コメント / string** を `.ps1` に含めたい場合は **(1) UTF-8 BOM 付き保存** を選ぶ。両選択肢は body.md §6.5 + §12.5.5 で明示済。

## skill 内 lint との関係

本 example の contract / script は `skills/source/lint/check-command-contract.{ps1,py}` で機械検査される (skill agent が proposal adopt 前に自動実行):

- C1 (extension match): contract.runtime=powershell-5 ↔ script .ps1 → OK
- C2 (BOM check): pure ASCII script なので BOM 不要 → OK
- C3 (argv invoker): contract.command が `powershell.exe -NoLogo -NoProfile -NonInteractive ...` → OK
- C4 (stdout init): 各 script 冒頭で `[Console]::OutputEncoding = UTF8` 設定 → OK
- C5 (runtime PATH): `powershell.exe` は Windows 同梱 → OK (skill 開発機が Windows なら確実)
- C6 (mojibake sentinel): qgb check 後の stage log を確認 (利用者環境で実行時)

## アンチパターン (本 example が避けていること)

1. **BOM 付き UTF-8 を Write tool で出力しようとする** → 一段の Write では不可能、PowerShell 二段階処理が必要 → 本 example は ASCII safe で回避
2. **`.ps1` を契約に直接書く** (`command: ["script.ps1"]`) → PowerShell invoker を経由しない、shell 関連付け依存 → 本 example は `powershell.exe -File <script.ps1>` 形式
3. **Console.OutputEncoding 設定なしで日本語 stdout** → qgb の utf-8 decode が cp932 出力を `U+FFFD` で誤 decode → 本 example は script 冒頭で必ず設定
4. **`runtime` field なしの contract** → capability-based dispatch checklist (ι) が適用できない → 本 example は全 contract で `runtime: powershell-5` 明示

## 関連

- `README.md` (本 example の overview)
- `.quality-system/knowledge/project-context.md` (人間正本、設計意図 + runtime 規律)
- `skills/source/body.md` §6.5 command authoring protocol (本 example が適用するプロトコル)
- `skills/source/body.md` §12.5.5 capability-based dispatch checklist (PowerShell 5 セクション)
- `skills/source/lint/` (本 example の contract / script を機械検査する lint helper)
- `development/docs/journal/phase5-step5-a-2-4-prejournal.md` (本 example 新設の設計判断)
