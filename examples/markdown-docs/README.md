# examples/markdown-docs

A minimal Markdown documentation set used by qgb to demonstrate the
`file_exists`, `substring_match`, and `json_schema` verification types.

## What this example checks

Three stages, each covering one dimension of "documentation quality":

| stage | verification_type | what it verifies |
|---|---|---|
| S1 | `file_exists` | `docs/index.md` exists |
| S2 | `substring_match` | `docs/index.md` contains an H1 header (`# `) |
| S3 | `json_schema` | `docs/metadata.json` validates against `schemas/metadata.schema.json` |

`design-notes.md` explains why these three. Together they exercise
qgb's `file_exists` and `substring_match` runners and the Step 8
`json_schema` runner (Phase 1 `$ref` is intentionally unsupported, so
the schema is written without `$ref`).

## Layout

```
README.md
design-notes.md
docs/
  index.md        # documentation set entry point (S1, S2 target)
  api.md          # additional documentation page
  metadata.json   # machine-readable doc metadata (S3 target)
schemas/
  metadata.schema.json   # the schema docs/metadata.json must satisfy (S3)
.quality-system/
  config.json
  policy.json
  req/REQ-DOC-001.{md,meta.json}
  contracts/REQ-DOC-001/{S1,S2,S3}.json
evidence-reference/REQ-DOC-001/latest/   # frozen reference gate
```

## Running the qgb quality-gate

From a checkout of the qgb repository:

```powershell
# from the qgb repo root
python -m qgb run REQ-DOC-001 --yes --path examples/markdown-docs
```

The expected outcome is `ALLOW`. The canonical evidence (gate.json,
summary.md, stage logs) is committed at
`evidence-reference/REQ-DOC-001/latest/`. There is no Python dependency
on the target side. Phase 3 Step 3.0 (2026-06-21) で adapter / `qgb detect`
は撤去された (理由: 対象プロジェクトの広がりに adapter 抽象が追いつかない、
詳細は `requirements_and_development.md` §6.2.2 / §14)。Markdown ドキュメント
群のような non-code プロジェクトの自己定義は `.quality-system/project-context.md`
(人間正本) と `.quality-system/project-context.json` (機械正本) に書く。本
example でも両ファイルを記入例として用意している。

### Path convention: forward slash, project-relative

All path-typed fields in this example use **forward slashes** and are
**project-root relative**:

- `docs/metadata.json` pages[].path entries: `"docs/index.md"`,
  `"docs/api.md"`
- `schemas/metadata.schema.json` pages[].path pattern: `^docs/.+\.md$`
  (forward slash only)
- `.quality-system/contracts/REQ-DOC-001/*.json` target/schema fields

This is the same convention qgb itself uses for `gate.json` paths (POSIX
forward slash) so the same path strings can be compared across machines.
Windows users authoring `docs/metadata.json` should write
`"path": "docs/index.md"` even though File Explorer renders it with
backslashes. The schema pattern intentionally rejects
`"docs\\index.md"` so the convention is enforced at validation time.

Phase 1 keeps the contract literal (forward-slash, project-relative).
adapter は Phase 3 Step 3.0 で撤去されたため、path 正規化は contract
記述者 (人間 / Phase 5 スキル) の責務として固定。schema pattern が
`^docs/.+\\.md$` で backslash を reject するので、ここで規律が機械的
に強制される。
