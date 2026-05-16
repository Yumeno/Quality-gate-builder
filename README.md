# quality-gate-builder

`quality-gate-builder` (`qgb`) generates trace-based quality gates for arbitrary target projects: REQ documents, machine-checkable contracts, layered verification stages, evidence, and ALLOW/DENY decisions.

This repository is the **Phase 1 MVP** of qgb. Stable behaviour is not yet guaranteed.

## Status

- Phase 1 implementation tracked in [Issue #14](https://github.com/Yumeno/Quality-gate-builder/issues/14).
- Current step: Step 0 (project skeleton).

## Documentation

- [`development/docs/philosophy.md`](development/docs/philosophy.md) — Philosophy charter (the constants `qgb` fixes).
- [`development/docs/requirements_and_development.md`](development/docs/requirements_and_development.md) — Requirements and design (v0.3).
- [`development/docs/stage-design.md`](development/docs/stage-design.md) — Stage design phase specification.
- [`development/docs/framework-shape.md`](development/docs/framework-shape.md) — Framework / user-project boundary.
- [`development/docs/project-background.md`](development/docs/project-background.md) — Project background.
- [`development/docs/wakaba-talk-summary.md`](development/docs/wakaba-talk-summary.md) — Summary of the originating talk.
- [`development/docs/yaoyorozu-system-references.md`](development/docs/yaoyorozu-system-references.md) — Reference implementation notes.

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
