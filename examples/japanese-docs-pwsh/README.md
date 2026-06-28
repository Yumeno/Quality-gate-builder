# examples/japanese-docs-pwsh — 日本語文書執筆プロジェクトの設計例 (Windows PowerShell 5 契約)

Phase 5 Step 5.a-2-4 で新設。**日本語文書執筆プロジェクトに qgb を適用し、Windows PowerShell 5 で `.ps1` 契約 command を回す** ときの設計例。

## このプロジェクトが想定するもの

- 利用者: 日本語の技術文書 / 規約文書 / マニュアル等を Markdown で執筆する個人 / チーム
- 環境: Windows native + 日本語 locale (ja-JP) + PowerShell 5 (Windows 同梱)
- 検査対象: 日本語含む Markdown 文書群、用語統一、見出し構造、リンク整合性等

## なぜ Windows + PowerShell 5 か

- 日本語環境の利用者ベース (法務 / 行政 / 教育機関 / 国内エンタープライズ) は **Windows + PowerShell 5** がデフォルト
- PowerShell 7 install を強制すると利用者導入のハードルが上がる
- PowerShell 5 で **日本語含む `.ps1`** を書くには **UTF-8 BOM 必須** + **`[Console]::OutputEncoding = UTF8`** が必須 (cp932 誤読防止 + qgb の utf-8 stdout decode 整合)

qgb skill (`skills/source/body.md` §6.5 command authoring protocol + §12.5.5 capability-based dispatch checklist) はこの組み合わせの規律を構造的に強制する。本 example はその適用例。

## 設計例の構造

```
.quality-system/
├── config.json                    # qgb 全体設定
├── policy.json                    # 段階定義 (4 stage: link / glossary / style / structure)
├── project-context.json           # 機械正本 (Windows + ja-JP + 文書)
├── req/
│   ├── REQ-DOC-001.md             # 要求文書 (日本語、本マニュアル品質)
│   └── REQ-DOC-001.meta.json      # メタ
├── contracts/REQ-DOC-001/
│   ├── S1-link.json               # link integrity (command, PowerShell 5)
│   ├── S2-glossary.json           # glossary check (command, PowerShell 5)
│   ├── S3-style.json              # style check (command, PowerShell 5)
│   └── S4-structure.json          # heading structure (substring_match)
├── knowledge/
│   ├── project-context.md         # 人間正本 (設計意図 + runtime 規律 + design-notes)
│   └── knowledge.jsonl            # 空 (初期状態)
└── (evidence/ / artifacts/ は qgb run 後生成)

scripts/quality-checks/             # contract.command が呼ぶ script
├── check-link-integrity.ps1       # BOM 付き UTF-8、Console.OutputEncoding 設定済
├── check-glossary.ps1             # 同
└── check-style.ps1                # 同
```

## design-notes.md (設計判断)

`design-notes.md` で本 example の設計判断 + θ/ι 適用例を解説:

- なぜ 4 段階か (link / glossary / style / structure)
- なぜ `command` 種別を 3 つ使うか (PowerShell 5 で機械化可能)
- 各 `.ps1` script の規律 (BOM / Console.OutputEncoding / argv / 改行 LF)
- 検査失敗時の対処 (例: glossary 違反は文書修正 or knowledge.jsonl で例外宣言)

## 利用方法 (skill 経由)

skill (Claude Code / Codex CLI) に以下を依頼すると本 example を few-shot として参照:

> 「Windows + PowerShell で日本語の技術文書プロジェクトに qgb を導入したい」
> 「日本語の規約文書を qgb で品質ゲート化したい」

skill agent は:

1. `examples/japanese-docs-pwsh/.quality-system/` の構造を参照
2. body.md §6.5 command authoring protocol を適用
3. body.md §12.5.5 PowerShell 5 checklist を確認
4. 利用者プロジェクトに合わせて `.quality-system/` を生成
5. 各 `.ps1` script を **BOM 付き UTF-8** で起草
6. `skills/source/lint/check-command-contract.{ps1,py}` で proposal を機械検査
7. `python -m qgb check` で stage log の U+FFFD を確認

## 関連

- `skills/source/body.md` §6.5 command authoring protocol (本 example が適用するプロトコル)
- `skills/source/body.md` §12.5.5 capability-based dispatch checklist (PowerShell 5 セクション)
- `skills/source/lint/` (本 example の contract / script を機械検査する lint helper)
- `development/docs/journal/phase5-step5-a-2-4-prejournal.md` (本 example 新設の設計判断)
- 既存 `examples/markdown-docs/` (英語前提の汎用 markdown 例、本 example の前駆)
