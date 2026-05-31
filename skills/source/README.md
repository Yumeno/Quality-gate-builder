# skills/source/ — Phase 5 reserved

This directory is **reserved for Phase 5** of qgb's development plan.
Phase 1 through Phase 4 do not produce any skill artifacts; only the
top-level directory exists so the repository layout is stable from day
one.

## What goes here (Phase 5)

qgb's skill is provided as **agent-neutral** content: one canonical
intermediate representation under `skills/source/`, which a converter
(`tools/build_skill.py`, also Phase 5) translates into Claude Code,
Codex CLI, and Gemini CLI deliverables.

Planned intermediate layout (F-019):

```text
skills/source/
  metadata.yaml         # skill id, version, per-agent bindings
  body.md               # neutral Markdown body
  workflow.md           # step-by-step instructions
  references.md         # pointers into philosophy.md, stage-design.md, ...
  prompts/
    design-stages.md
    review-policy.md
```

`metadata.yaml` carries per-agent placement details (filename,
frontmatter keys, how auxiliary files are pulled in). The exact schema
is finalised in Phase 5 (not now — see "Why no sketch" below).

## Why no sketch yet

Codex 計画レビュー (Step 9) explicitly recommended *not* shipping a
half-formed `metadata.yaml` example during Phase 1. A partial schema
example would constrain Phase 5 in ways that are hard to unwind, and
the converter cannot be tested against it. We document the planned
structure here, then build the actual schema and converter together
in Phase 5.

## Spec references

The full specification for agent-neutral skill delivery lives in:

- `development/docs/requirements_and_development.md` §F-019 — primary
  contract (intermediate representation, converter, phase plan).
- `development/docs/framework-shape.md` — the intermediate-format
  details and per-agent binding pointers.

## Phase plan (verbatim from §F-019)

> Phase 1〜4: スキル成果物は作らない。`skills/source/` のディレクトリ
> 構造のみ予約。
> Phase 5: 中間表現とコンバータを本実装、3 エージェント向けリリースを
> CI で生成。

## Per-agent deliverables (Phase 5)

| Agent | Output | Install location |
|---|---|---|
| Claude Code | `SKILL.md` (YAML frontmatter) + auxiliary files | `~/.claude/skills/<skill-id>/` or `.claude/skills/<skill-id>/` |
| Codex CLI | `AGENTS.md` (auxiliary files concatenated at the end) | Project root |
| Gemini CLI | `GEMINI.md` (uses `@import`) + `.gemini/commands/<command>.toml` | `~/.gemini/` or project root |

Artifacts are emitted to `dist/skills/{claude,codex,gemini}/` and
attached to GitHub Releases via CI. `dist/` is gitignored; the
intermediate representation under this directory remains the source of
truth (Phase 5 P7 reproducibility).
