<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  converter_version: 0.1.0
  build_input_digest: 14924a4088439977
-->

## 7. 参照集

(本セクションは full モード: SKILL.md 内の埋め込み見出し / split モード: `references.md` 別ファイル。)

### 7.1 qgb 本体の正本

- `development/docs/philosophy.md` — 思想憲章 (12 不易、最上位)
- `development/docs/requirements_and_development.md` — 要件定義書・基本設計書
- `development/docs/detailed-design.md` — 詳細設計
- `development/docs/framework-shape.md` — Layer 1〜4 境界
- `development/docs/stage-design.md` — 段階設計フェーズ仕様

### 7.2 利用者向け資料

- `development/docs/phase1-manual.md` — Phase 1 で確立した利用者マニュアル
- `examples/` — 6 例の設計パック
  - `generic-minimal/` (汎用最小、language-agnostic)
  - `python-cli-pytest/` (Python CLI + pytest)
  - `markdown-docs/` (ドキュメント群)
  - `python-fastapi-pytest/` (Python Web)
  - `go-cli/` (Go CLI)
  - `node-cli-vitest/` (Node CLI + Vitest)
- `development/docs/ci-examples.md` — 利用者運用 CI 5 patterns (artifact / SBOM / vuln scan / JUnit / Dependabot)

### 7.3 重要な ALLOW 解釈

**ALLOW = 「このプロジェクトの定義済み検査に通過した」** だけ。

- プロジェクト間で ALLOW を比較してはならない (P11)
- マーケティング目的の対外品質指標として使ってはならない
- 「他のプロジェクトでも qgb で ALLOW が出ているから同じ水準だ」は誤り
- 各 ALLOW の意味は `gate.json.basis[]` と `decision.meaning` を読んで個別解釈する

