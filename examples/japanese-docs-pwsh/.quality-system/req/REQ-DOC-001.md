# REQ-DOC-001: 日本語文書プロジェクトの品質ゲート

## 要求

`docs/` 配下の日本語 Markdown 文書群に対して、以下の品質特性を機械的に保証する:

1. **link 整合性**: 内部リンク (`[xxx](./yyy.md)` / `[xxx](#zzz)` 等) が壊れていない
2. **用語統一**: 用語表 (`docs/glossary.json`) で禁止された表記 / 旧称が文書に出現しない
3. **style 規約**: 見出し階層が連続している (H1 直後に H3 等のスキップなし)
4. **起点ファイル**: `docs/README.md` が存在し H1 見出しを持つ

## 段階対応

| stage | 名称 | 検査内容 |
|---|---|---|
| S1 | link 整合性 | scripts/quality-checks/check-link-integrity.ps1 |
| S2 | 用語統一 | scripts/quality-checks/check-glossary.ps1 |
| S3 | style 規約 | scripts/quality-checks/check-style.ps1 |
| S4 | 起点ファイル | substring_match (docs/README.md に `# ` 含む) |

## 採用判定 (ALLOW の意味)

ALLOW は **「上記 4 stage が機械的に通過した」** のみを意味する。**文書の意味的妥当性 / 自然さ / 読みやすさ** は保証しない (philosophy P5)。それらは人間レビューの責務。

## 関連

- `examples/japanese-docs-pwsh/README.md` (本 example overview)
- `examples/japanese-docs-pwsh/.quality-system/knowledge/project-context.md` (設計意図 + runtime 規律)
- `examples/japanese-docs-pwsh/scripts/quality-checks/*.ps1` (検査 script)
