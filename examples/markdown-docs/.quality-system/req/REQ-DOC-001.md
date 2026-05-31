# REQ-DOC-001 — 文書群が存在し、見出し規約と metadata schema を満たす

このプロジェクト (examples/markdown-docs) が満たすべき品質要求。

## ALLOW の条件

| stage | 検査内容 |
|---|---|
| S1 | `docs/index.md` が存在する |
| S2 | `docs/index.md` に H1 ヘッダ (`# `) が含まれる |
| S3 | `docs/metadata.json` が `schemas/metadata.schema.json` を満たす |

S1 は文書ファイル自体の存在、S2 は authoring 規約 (1 ページ 1 H1)、
S3 は metadata の構造的整合性をそれぞれ独立に検査する。

詳細な責務分割の根拠は `../design-notes.md` を参照。
