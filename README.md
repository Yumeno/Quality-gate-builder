# quality-gate-builder

[![test](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml/badge.svg?branch=main)](https://github.com/Yumeno/Quality-gate-builder/actions/workflows/test.yml)

`quality-gate-builder` (`qgb`) generates trace-based quality gates for arbitrary target projects: REQ documents, machine-checkable contracts, layered verification stages, evidence, and ALLOW/DENY decisions.

Stable behaviour is not yet guaranteed.

## Status

- Phase 1 (Python CLI MVP) and Phase 2 (編集を安全にする) completed.
- Phase 3 (機械責務側の最終整備) in progress:
  - Step 3.0 (`detect` 廃止 + project-context 二重ファイル設計): ✅ completed 2026-06-22
  - Step 3.1 (command runner 強化 + CI 雛形): ✅ completed 2026-06-24
  - Step 3.2 (依存解決固定 / lock + hash): next
- See `development/docs/journal/` for the latest Step's record.
- Windows PowerShell is a first-class environment (NF-004); CI verifies on `windows-latest` and `ubuntu-latest` with Python 3.10 and 3.12.

## Documentation

- [`development/docs/philosophy.md`](development/docs/philosophy.md) — Philosophy charter (the constants `qgb` fixes).
- [`development/docs/requirements_and_development.md`](development/docs/requirements_and_development.md) — Requirements and design (v0.3).
- [`development/docs/stage-design.md`](development/docs/stage-design.md) — Stage design phase specification.
- [`development/docs/framework-shape.md`](development/docs/framework-shape.md) — Framework / user-project boundary.
- [`development/docs/project-background.md`](development/docs/project-background.md) — Project background.
- [`development/docs/wakaba-talk-summary.md`](development/docs/wakaba-talk-summary.md) — Summary of the originating talk.
- [`development/docs/yaoyorozu-system-references.md`](development/docs/yaoyorozu-system-references.md) — Reference implementation notes.
- [`SECURITY.md`](SECURITY.md) — CI action SHA pin policy + vulnerability reporting.

## Installation (development)

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

## Development

```bash
pytest
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
