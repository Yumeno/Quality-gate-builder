# プロジェクトコンテキスト (記入例: Markdown ドキュメント群)

これは Phase 3 Step 3.0 で `project-context.md` の **記入例** として作成
した non-code プロジェクトのサンプル。実プロジェクトに `qgb init` した
直後はもっと簡素な雛形が生成され、利用者が中身を書いていく。
`examples/python-cli-pytest/project-context.md` がコードベースの記入例
だったのに対し、本 example は **ドキュメント群 (言語ソースを含まない対象)**
で qgb 設計がどう成立するかを示す。

補佐 Agent (Claude Code / Codex CLI / Gemini CLI 等) は本ファイルを読んで
構造化し、`.quality-system/project-context.json` (機械正本) を生成または
更新する。`json` の `human_reviewed: true` は人間がレビューしてから付ける。

## 目的

このプロジェクトに quality-gate-builder を導入したのは、`docs/` 配下の
Markdown ドキュメント群に対して、「文書セットの起点が存在する / 規約
通りの構造を持つ / metadata が壊れていない」ことの証跡を機械的に残す
体験を Phase 1〜2 設計例として示すため。実プロダクトのドキュメント
ではなく `qgb` の使い方 (特に **言語ソースでない対象** への適用) を
学ぶための例。

## 対象範囲

### in scope

- `docs/` 配下の Markdown ファイル (`docs/index.md`, `docs/api.md`)
- `docs/metadata.json` の構造 (pages 配列、各 page の path / title / language)
- ナビゲーション生成や検索 index の入力となる metadata の妥当性

### out of scope

- 文章の意味的妥当性 (typo / 文法 / 用語ぶれ)
  - これらは人間レビューや別ツール (markdownlint / aspell / textlint 等)
    の責務で、qgb の ALLOW/DENY 判定の根拠にしない (P6 整合)
- リンク先の生存確認 (404 検出など)
- 多言語版の翻訳整合性
- パフォーマンス指標 (ページサイズ / 読了時間など)

## 既知の制約・前提

### 技術スタック (technologies)

- markdown (CommonMark / GitHub Flavored Markdown 想定だが構文厳密性は
  qgb の検査対象外)
- json (metadata 用)
- プログラミング言語ソースは **使わない**

### 成果物の種類 (artifact_kinds)

- ドキュメント (`documentation`)
- 構造化 metadata (`structured-metadata`)

### 対象プラットフォーム

- platform-agnostic (Markdown は OS 非依存、qgb 自体は Windows
  PowerShell first-class)

### 採用しないテスト方式

- **link checker (markdown-link-check 系)**: 外部ツール依存が増えるため
  本 example の最小性を逸脱する。実プロジェクトで必要なら `command`
  verification_type で立てる
- **spell checker (aspell / textlint 等)**: 辞書依存と false positive
  管理が重い、本 example のスコープ外
- **wordcount / length floor**: threshold 型は qgb の ALLOW/DENY 二値判定
  モデルに合わない (philosophy P11、advisory metric は qgb のスコープ外)
- **Markdown AST レベル検査**: substring_match は文字列マッチのみ。
  AST レベルが必要なプロジェクトは利用者が `command` 経由 (markdownlint /
  remark 等) で contract を立てる設計
- **多言語整合性検査**: docs.<lang>.metadata.json 形式の多言語版管理は
  本 example のスコープ外、必要なら別 stage / 別 REQ で扱う

## 「言語ソースでない対象」での qgb 設計のポイント

ドキュメント群のような対象では、コードベース向けの adapter 抽象
(Phase 3 Step 3.0 で撤去) は機能しない。本 example が示すパターン:

### 1. file_exists で起点を担保

`docs/index.md` のような「文書セットの起点」の存在を S1 (file_exists)
で機械的に確認する。これが DENY だと S2/S3 を skip して「不在が原因」
を一目で判別できる (P9 単一責任)。

### 2. substring_match で authoring 規約を強制

「1 ページ 1 H1」のような単純な authoring 規約は substring_match で
機械的に強制できる。文章の意味的妥当性は判定しないが、構造ぶれを
ゼロにする最低限。

### 3. json_schema で構造化メタデータを担保

`docs/metadata.json` のような構造化メタデータは json_schema で厳密に
担保。ナビゲーション生成や検索 index の入力になる場合、ここが壊れる
と downstream が機能不全になるため必須段階。

### 4. path は forward slash 統一 (Windows/POSIX portable)

`pages[].path` は `"docs/index.md"` のように forward slash で書き、
schema pattern `^docs/.+\.md$` で backslash を reject する。これは
旧 adapter が path normalization 層を入れる余地として言及していたが、
Phase 3 Step 3.0 で adapter 撤去後は contract literal の規約として
固定された。

## Phase 5 スキルへの伝達事項

本 example を few-shot 教材として読む Phase 5 スキルへ:

- **対象が言語ソースとは限らない**: project_context.json の
  `technologies: ["markdown"]`、`artifact_kinds: ["documentation"]` の
  ような書き方を learn する。Python adapter 観察観点のような
  「言語固有のヒューリスティック」を非コード対象に強引に適用しない
- **stage 設計の小さな単位**: 3 stage / 3 verification_type の組合せが
  最小例として成立すること。利用者対象が複雑なら stage を増やすが、
  philosophy P10 の推奨範囲 (3〜7 stage) を超えない
- **採用しない方式の明示**: `non_adopted_methods` は LLM が新 stage を
  提案するときの重要な制約。本 example の wordcount / spell-check 等
  の reject 理由を learn する
- **path portability**: forward slash 統一は qgb が target system に
  toolchain を要求しないための規律 (Windows でも POSIX でも contract
  が同じ文字列で動く)。スキルが contract を起草するときも同じ規律
  を守る

## 補佐 Agent への伝達事項

本ファイルを読んで `project-context.json` を更新する補佐 Agent への
お願い:

- `human_reviewed: true` は **私 (利用者) が json を読んでレビューを
  終えてから手で書き換える**。あなたは false のまま残してよい
- `source_metadata.source_md_sha256` には本ファイルの SHA-256 を入れて
  ほしい。後で md だけ更新された場合の検出に使う
- `technologies` には `["markdown", "json"]` のように使われている形式を
  列挙する。「言語」フィールドに無理に詰め込まない (旧 adapter モデル
  の再来になる)
- `artifact_kinds` には `["documentation", "structured-metadata"]` の
  ように成果物の種類を書く。`source-code` 系を含めない
