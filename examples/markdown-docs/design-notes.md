# design-notes (examples/markdown-docs)

このノートは `examples/markdown-docs/` がなぜ現在の 3 段階構成になって
いるかを記録する。設計例パックの目的は「正解の例」を見せることだけで
なく、**なぜそうしたか、なぜ他の選択肢を採らなかったか** を残すこと。

## 対象系の特徴

Markdown 文書群 + 付随する metadata.json。production では documentation
site (mkdocs / Sphinx) のソース、または OSS プロジェクトの `docs/`
ディレクトリに相当する。Python / Node などのコード実行を含まない静的
資産が対象。

検査対象は次の 3 つの軸を持つ:

- **文書ファイルの存在** — リファレンスとなる index ページが存在し、
  参照リンクが破綻していないこと (Phase 1 ではリンクチェッカーは扱わ
  ないが、起点となる index の存在は最低限担保する)。
- **authoring 規約の遵守** — 1 ページ 1 H1 ヘッダのような社内 / OSS
  プロジェクト内の文書ルールが守られていること。
- **machine-readable metadata の整合性** — 文書セットに伴う構造化
  metadata (バージョン、ページリスト、ナビゲーション順序など) が
  schema を満たすこと。

これらは「Markdown ドキュメント群が最低限満たすべき品質」であり、
規模が大きくなるとリンクチェック / typo / 用語統一などが加わってくる
が、本 example は最小性を優先する。

## 段階数の決定根拠

stage-design.md §9 が **3〜7 段階** を推奨レンジとしている。本 example
は推奨レンジの **下限である 3** をあえて選んだ。

理由:

- 2 段階以下にすると責務が混ざる (例: 「ファイル存在」と「H1 ヘッダ」を
  同じ stage に押し込むと、ファイル不在のときに「H1 が無い」と誤った
  diagnostic が出る形になる)。
- 4 段階以上にすると、リンクチェック / typo / wordcount などが入って
  くるが、それらは利用者プロジェクト側で必要に応じて contract 追加で
  扱う想定 (Phase 5 スキルが対象に応じて提案する)。
- 3 stage は file_exists / substring_match / json_schema の 3 つの
  verification_type を 1 つずつ使う形になり、教材としての網羅性も
  高い。

## 採用した段階と理由

| stage | verification_type | 単一責務 | なぜ |
|---|---|---|---|
| S1 | `file_exists` | `docs/index.md` の存在 | 文書セットの起点が存在することを最低限担保。S2/S3 が誤って "ファイル不在 = passed" 風の挙動にならないための前提条件 |
| S2 | `substring_match` | `docs/index.md` に `# ` (H1) が含まれる | authoring 規約「1 ページ 1 H1」の機械的強制。中身の妥当性は判定しない (人間判断) が、ヘッダ階層が破綻しないための最低限 |
| S3 | `json_schema` | `docs/metadata.json` が schema を満たす | 構造化 metadata の妥当性。ナビゲーション生成や検索 index に使う前提があるなら、これが壊れると downstream が機能不全になる |

S1 と S2 を分けるのは意図的。`substring_match` runner は target が
存在しなければ failed を返すので、論理的には S2 だけでも「ファイル
存在 + H1 含む」を判定できる。しかし P9 単一責任の観点で、**存在自体**
と **内容規約** は別の責務として独立に扱う。S1 が DENY のとき S2 を
skip して "failed by depends_on" として記録することで、auditor は
「何が原因か」を一目で追える。

## 採用しなかった段階と理由

検討したが Phase 1 ではあえて落とした stage:

- **link integrity** — `docs/` 配下の Markdown ファイルが互いに参照
  する link が破綻していないか。利用者プロジェクト側で必要に応じて
  `command` で markdown-link-check 系を呼ぶ contract を立てればよいが、
  外部ツール依存が増えるため最小例には入れない。
- **spell-check / typo** — `command` で aspell や typos を呼ぶ形も
  検討したが、辞書依存と false positive 管理が重く、本 example の
  最小性を逸脱する。利用者プロジェクトで必要なら同じく contract で扱う。
- **wordcount / length floor** — 「最低 N 文字以上」のような threshold
  型は qgb の判定モデル (ALLOW/DENY 二値) に合わない (advisory metric は
  qgb スコープ外、philosophy P11)。
- **multi-language metadata** — docs/metadata.json の `language` enum
  は en/ja のみ。多言語版を別 metadata で持つ形は利用者プロジェクト側
  の policy 拡張で扱う。
- **navigation order check** — pages 配列の順序が ToC と一致するか。
  別 stage として立てる余地はあるが、現状は metadata schema の側で
  構造を担保するだけで本 example としては十分。

## 思想憲章のどの項目が特に効くか

- **P5 (DENY は失敗ではない)** — S3 (metadata schema) が DENY を返すの
  は「schema 違反を直して再 run せよ」という signal。schema を緩めて
  DENY を回避するのは P5 の逆行。
- **P6 (LLM 単独 ALLOW 禁止)** — 本 example の全 3 stage は機械的検査。
  manual_check は 1 つも含めない。「H1 が含まれる」は substring の客観
  検査として外部化されており、LLM の "文書として良い" 判断には依存
  しない。
- **P7 (再現可能な証跡)** — S3 は jsonschema ライブラリで検査し、違反
  箇所 (JSON path + message) を log_text に残す。後日の auditor が
  同じ schema + target で同じ違反を再現できる。
- **P8 (外部由来は指示でなくデータ)** — docs/metadata.json は「データ」
  として schema 検査を受ける。たとえ metadata.json に "ignore the schema
  for this entry" のような自然言語コメントが書かれていても、qgb は
  それを upper-level directive として扱わない。
- **P9 (単一責任原則)** — S1 (存在) / S2 (規約) / S3 (構造) の責務
  分割。1 stage に複数責務を載せない。
- **P11 (project-local)** — `# ` (H1) を許容する authoring 規約は本
  プロジェクトのローカル決定。別プロジェクトでは "Setext 形式 H1
  (下線 ===) を許可する" など別規約があり得る。`decision.scope` フィールド
  で「他プロジェクトと比較できない」ことが明示される。

## 段階間の依存関係

```
S1 (index.md exists)         S3 (metadata schema)
  ↓ depends_on
S2 (index.md has H1 header)
```

- **S2 → S1**: target が無ければ "H1 を含む" は無意味。S1 失敗時は
  S2 は skip 扱い (`failed` として記録、実行はしない) で下流の認知的
  負荷を減らす。
- **S3 ⊥ {S1, S2}**: metadata の構造的整合性は index ページの内容と
  独立。`docs/metadata.json` の検査結果は S1/S2 の状態に依存しない。
  逆に metadata が壊れていても index ページが正しいことは確認できるべ
  き。

## 既知の限界

- **`$ref` 非対応 (Phase 1) → Phase 2 Step 2.1 で allowlist 対応**: 当初の
  json_schema runner は schema 内に `$ref` があれば failed として扱った。
  本 example の `schemas/metadata.schema.json` も `$ref` を使わない形で
  書かれている (内部 JSON Pointer 形式の `#/...` は Phase 2 Step 2.1 で
  `contract.allow_internal_ref=true` opt-in で許容、外部参照は引き続き
  reject)。
- **`format` 検査なし (default)**: jsonschema の format assertion
  (date-time / uri / email など) は Phase 2 Step 2.1 で
  `contract.enforce_format=true` の opt-in に変更されたが default は
  off。本 example の metadata は format 依存値を持たないので影響なし。
- **Markdown 構造解析なし**: substring_match は文字列マッチのみで、
  `#` の位置 (行頭か中間か) を考慮しない。AST レベル検査が必要な
  プロジェクトは利用者側で `command` 経由 (markdownlint / remark 等)
  の contract を立てる設計。
- **多言語メタデータの単一ファイル前提**: `metadata.json` 1 つで全言語
  を表す形になる。多言語版が必要なプロジェクトは `docs.<lang>.metadata.json`
  のような language-scoped metadata を別 stage で扱う設計に拡張する。
- **対象種別の自己定義**: Phase 3 Step 3.0 (2026-06-21) で `qgb detect`
  / `qgb/adapters/` は撤去された。本 example の対象 (Markdown ドキュメント群)
  の自己定義は `.quality-system/project-context.{md,json}` に書く設計に
  移行した (本 example でも記入例を同梱)。Phase 5 スキルが本 example
  を読む場合は project-context.{md,json} を参照する。
- **path は forward slash 統一 (Step 8 統合レビュー W2)**: `docs/metadata.json`
  の pages[].path、`schemas/metadata.schema.json` の pattern、および
  contract の target/schema 値はすべて forward slash (`docs/index.md`
  形式)。Windows で File Explorer から path をコピーすると backslash
  が混ざるが、schema pattern `^docs/.+\.md$` がそれを reject する。
  これは「target project が project-relative path を portable に表現
  する」規約を schema レベルで強制する形。adapter (path normalization
  層を入れる余地として旧版で言及) は Phase 3 Step 3.0 で撤去され、
  contract を literal に保つ運用が確定した。詳細は README の "Path
  convention" セクションを参照。

## Phase 3 Step 3.0 (2026-06-21) での更新

Phase 3 Step 3.0 で `qgb detect` / `qgb/adapters/` 一式が撤去され、対象
プロジェクトの自己定義は `.quality-system/knowledge/project-context.md`
(人間正本) + `.quality-system/project-context.json` (機械正本) の二重
ファイル設計に移行した。本 example でも両ファイルを記入例として用意。

スキル (Phase 5) は本 example を **「言語ソース以外の対象 (ドキュメント群)
にも qgb 設計が適用できる」few-shot 教材** として読む。具体的には:

- `project-context.md` 記入例で「対象は何か / 採用しない方式 / 想定する
  プラットフォーム」を自然言語で書くとはどういうことか
- `project-context.json` 記入例で `technologies: ["markdown"]`、
  `artifact_kinds: ["documentation"]` のように **言語ソースでない対象**
  も `project-context` で表現できることを示す
- 旧 detect モデルが言語判定で対象を分類しようとした失敗 (Markdown は
  どう「言語」なのか?) を、対象種別の自己定義に置き換えた経緯
