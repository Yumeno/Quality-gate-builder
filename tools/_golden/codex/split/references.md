<!--
  GENERATED FILE - DO NOT EDIT.
  これは生成物。skills/source/body.md を編集すること。
  skill_version: 0.1.7
  converter_version: 0.1.1
  build_input_digest: 817b442b8348de30
-->

## 7. 参照集

(本セクションは full モード: SKILL.md 内の埋め込み見出し / split モード: `references.md` 別ファイル。)

> **注意**: 本節の `development/docs/` / `examples/` は **qgb repo (github.com/Yumeno/Quality-gate-builder) 内の資料**であり、skill 配布物 (zip / pip パッケージ) には同梱されない。参照できない環境では、本 SKILL.md 内の要約 (§3 の 4 原則、段階設計プロンプトの設計指針) で運用が成立する設計になっている。

### 7.1 qgb 本体の正本

- `development/docs/philosophy.md` — 思想憲章 (12 不易、最上位)
- `development/docs/requirements_and_development.md` — 要件定義書・基本設計書
- `development/docs/detailed-design.md` — 詳細設計
- `development/docs/framework-shape.md` — Layer 1〜4 境界
- `development/docs/stage-design.md` — 段階設計フェーズ仕様

### 7.2 利用者向け資料

- `development/docs/phase1-manual.md` — Phase 1 で確立した利用者マニュアル
- `examples/` — 6 例の設計パック (qgb repo 内のみ、配布物には同梱されない)
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
- ALLOW は**実行時点の**検査通過であり、その後のソース変更を検出しない。evidence とソースの対応づけは利用者運用の責務 (§6.1 step 9 の設計分岐で方針を決める)

