# quality-gate-builder

[![test](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml)

`quality-gate-builder` (`qgb`) generates trace-based quality gates for arbitrary target projects: REQ documents, machine-checkable contracts, layered verification stages, evidence, and ALLOW/DENY decisions.

Stable behaviour is not yet guaranteed.

## Skill releases (use qgb from an agent)

The qgb skill — a guided workflow for Claude Code / Codex agents that sets up and operates quality gates in your project — is distributed via **[GitHub Releases](https://github.com/Yumeno/Quality-gate-builder/releases)** ([latest](https://github.com/Yumeno/Quality-gate-builder/releases/latest)).

Each `skill-v*` release ships 4 zips: `{claude,codex}` × `{full,split}`. For Claude Code, download `claude-full`, unzip it into your project's `.claude/skills/qgb/` (so `SKILL.md` sits at that root), then follow the bundled `INSTALL.md` — the included `setup-qgb.ps1` / `setup-qgb.sh` create a project-local `.venv` and install the qgb CLI pinned to the release tag. All zips are built deterministically from `skills/source/` by `tools/build_skill.py`; CI verifies the build output against the committed golden on every push and rebuilds (never transfers) the artifacts at release time.

## Status

- Phase 1 (Python CLI MVP) and Phase 2 (編集を安全にする) completed.
- **Phase 3 (機械責務側の最終整備) completed 2026-06-26**:
  - Step 3.0 (`detect` 廃止 + project-context 二重ファイル設計): ✅ completed 2026-06-22
  - Step 3.1 (command runner 強化 + CI 雛形): ✅ completed 2026-06-24
  - Step 3.2 (依存解決固定 / lock + hash + lock-integrity CI): ✅ completed 2026-06-26
  - Step 3.3 (Phase 2 繰越実需回収): optional, deferred to Phase 5 实需待ち
- **Phase 5 (Skill Creator 化) in progress**: philosophy charter v2.0 (P12 added), skill single-source (`skills/source/body.md`) + deterministic converter (`tools/build_skill.py`) + release pipeline completed; skill releases `skill-v0.1.0` … `skill-v0.1.2` published (2026-07-04). Remaining: dogfood pass (5.e) and further canary runs.
- See `development/docs/journal/` for the latest Step's record.
- Windows PowerShell is a first-class environment (NF-004); CI verifies on `windows-latest` and `ubuntu-latest` with Python 3.10 and 3.12, plus a `lock-integrity` job validating that committed `requirements.lock` / `requirements-dev.lock` stay consistent with `pyproject.toml`.

## Documentation

- [`development/docs/philosophy.md`](development/docs/philosophy.md) — Philosophy charter (the constants `qgb` fixes).
- [`development/docs/requirements_and_development.md`](development/docs/requirements_and_development.md) — Requirements and design (v0.3).
- [`development/docs/stage-design.md`](development/docs/stage-design.md) — Stage design phase specification.
- [`development/docs/framework-shape.md`](development/docs/framework-shape.md) — Framework / user-project boundary.
- [`development/docs/ci-examples.md`](development/docs/ci-examples.md) — Sample CI patterns for downstream qgb operators (non-prescriptive; artefact retention, SBOM, vuln scan, etc.).
- [`development/docs/project-background.md`](development/docs/project-background.md) — Project background.
- [`development/docs/wakaba-talk-summary.md`](development/docs/wakaba-talk-summary.md) — Summary of the originating talk.
- [`development/docs/yaoyorozu-system-references.md`](development/docs/yaoyorozu-system-references.md) — Reference implementation notes.
- [`SECURITY.md`](SECURITY.md) — Action SHA pin policy + dependency lock policy + vulnerability reporting.

## Installation (development)

The convenient path uses `pyproject.toml` ranges (matches what most contributors run day-to-day):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m qgb --help
```

Or on bash / zsh:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
python -m qgb --help
```

### Reproducible (hash-verified) install

The hash-pinned path matches CI exactly — every dependency comes from the committed lock files and `--no-build-isolation` keeps the build step within the hash-verified env (the dev lock pins `setuptools` / `wheel` too):

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install --require-hashes --only-binary :all: -r requirements-dev.lock
python -m pip install --no-deps --no-build-isolation -e .
python -m qgb --help
```

Use this path for security-sensitive contributor environments or to reproduce CI conditions locally. The lock policy (when it is regenerated, what the trust boundary is) is documented in [`SECURITY.md`](SECURITY.md) "Dependency Lock Policy".

## Development

```bash
pytest
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
