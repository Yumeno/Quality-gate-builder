# project-context.md (人間正本) — japanese-docs-pwsh

## このプロジェクトは何か

日本語の技術文書 / 規約文書 / マニュアル等を Markdown で執筆する利用者向けの **qgb 設計例**。Windows native + 日本語 locale (ja-JP) + PowerShell 5 (Windows 同梱) を想定し、PowerShell 5 `.ps1` script による契約 command で品質ゲートを構築する。

## 採用環境の根拠

### なぜ Windows + PowerShell 5 か

- 利用者ベース (法務 / 行政 / 教育機関 / 国内エンタープライズ) は **Windows + PowerShell 5** がデフォルト
- PowerShell 7 (`pwsh`) は別途 install が必要、利用者の導入ハードルを上げる
- WSL / macOS / Linux 移行は本例の scope 外 (`examples/markdown-docs` を参照)

### なぜ PowerShell 5 + 日本語 `.ps1` に encoding 規律が必須か

PowerShell 5 (Windows 同梱) は BOM なし `.ps1` を **system code page (cp932 on 日本語 Windows)** として読む。日本語コメント / string を含む `.ps1` を BOM なしで保存すると:

1. PowerShell 5 が cp932 として誤読 → parse error
2. または cp932 文字化けで script の挙動が変わる

そのため本例の全 `.ps1` は **UTF-8 BOM 付き** で保存。`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8` を script 冒頭で設定して **stdout を UTF-8 化** し、qgb command runner の utf-8 decode と整合させる。

詳細規律は `skills/source/body.md` §6.5 「PowerShell 5 規律」+ §12.5.5 「PowerShell 5 / 7 (Windows native) checklist」を参照。

## 段階設計 (4 段階)

| stage | 名称 | verification_type | runtime |
|---|---|---|---|
| S1 | link 整合性 | command | powershell-5 |
| S2 | 用語統一 | command | powershell-5 |
| S3 | style 規約 | command | powershell-5 |
| S4 | 起点ファイル存在 + H1 | substring_match | - |

S1-S3 は PowerShell 5 `.ps1` 契約、S4 は qgb 内蔵の substring_match (script 不要、軽量)。
段階数 4 は本例の対象 (文書群) に対して適切 (philosophy P10、`policy.json` の 3-7 段階推奨範囲内)。

## runtime assumptions (β-lite: project-context md に記録)

本例が想定する利用者環境:

| 項目 | 値 |
|---|---|
| OS | Windows 10 / 11 (native、WSL ではない) |
| shell | PowerShell 5 (Windows 同梱、`powershell.exe`) |
| locale | ja-JP (cp932 system code page) |
| 改行コード (.ps1) | LF (`.gitattributes` で `*.ps1 text eol=lf` 強制済、qgb 本体規律と整合) |
| script encoding | UTF-8 BOM 付き (PowerShell 5 cp932 誤読防止) |
| Console.OutputEncoding | UTF-8 (script 冒頭で設定、qgb の utf-8 stdout decode と整合) |

利用者が PowerShell 7 (`pwsh`) を導入済なら、本例の `.ps1` script は **そのまま動く** (PS 7 は BOM なしでも UTF-8 を正しく読むが、BOM 付きでも問題ない)。

## 検査の意味と限界

### 含めること

- link 整合性 (内部 link 切れの検出)
- 用語統一 (旧称 / 禁止表記の検出)
- style 規約 (見出し階層、コードブロック構造等)
- 起点ファイルの存在 + H1 必須

### 含めないこと

- 日本語の意味的妥当性 (文法 / 自然さ / 読みやすさ) → 人間レビューの責務
- 外部リンク 404 (ネットワーク依存、flaky)
- 多言語整合性 (本例は ja-JP 単一)
- ALLOW を「文書品質が高い」と読み替えること (P5: ALLOW は機械検査通過のみ)

## 利用方法 (skill 経由)

skill (Claude Code / Codex CLI) に以下を依頼すると本例を few-shot として参照:

> 「Windows + PowerShell で日本語の技術文書プロジェクトに qgb を導入したい」
> 「日本語の規約文書を qgb で品質ゲート化したい」

skill agent は本 `project-context.md` + `policy.json` + `contracts/REQ-DOC-001/*.json` + `scripts/quality-checks/*.ps1` の構造を参考に、利用者プロジェクトに合わせた `.quality-system/` を生成する。

## 関連

- `README.md` (本 example の overview)
- `design-notes.md` (設計判断の詳細 + θ/ι 適用例)
- `skills/source/body.md` §6.5 command authoring protocol
- `skills/source/body.md` §12.5.5 capability-based dispatch checklist (PowerShell 5)
- `skills/source/lint/check-command-contract.{ps1,py}` (本 example の contract / script を機械検査する lint helper)
