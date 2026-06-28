# 日本語文書プロジェクト sample

本 docs/ は `examples/japanese-docs-pwsh/` の検査対象 sample。

## このフォルダの構成

- `README.md` (本ファイル): 起点ファイル、qgb stage S4 で存在 + H1 を検査
- `glossary.json`: 用語表、stage S2 で禁止用語の検査に使用
- (実プロジェクトではここに章ごとの `.md` ファイルが並ぶ)

## 関連リンクの例 (stage S1 link 整合性検査の対象)

- [用語表](./glossary.json)

## 用途

skill (Claude Code / Codex CLI) が本 example を few-shot として参照、利用者プロジェクトの `.quality-system/` 生成に活用する。
