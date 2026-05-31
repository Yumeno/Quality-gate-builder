# examples/python-cli-pytest

A minimal Python CLI + pytest project used by qgb to demonstrate the
`command` and `substring_match` verification types.

## What this example checks

Three stages, one per Phase 1 quality dimension that an executable CLI
project usually has:

| stage | verification_type | what it verifies |
|---|---|---|
| S1 | `command` | `python -m pytest -q` passes (functional correctness) |
| S2 | `command` | `python -m demo_cli --help` exits 0 (CLI surface starts) |
| S3 | `substring_match` | README documents installation (developer onboarding) |

`design-notes.md` explains why these three. Together they exercise
qgb's `command` runner with two different argv shapes (pytest, module
invocation) and `substring_match` for documentation evidence.

## Installation

```powershell
# from this example directory
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[test]"
```

## Running the demo CLI

```powershell
python -m demo_cli greet --name world
# -> hello, world!
```

## Running the qgb quality-gate

From a checkout of the qgb repository:

```powershell
# from the qgb repo root
python -m qgb run REQ-APP-001 --yes --path examples/python-cli-pytest
```

The expected outcome is `ALLOW` because all three stages pass. The
canonical evidence (gate.json, summary.md, stage logs) is committed at
`evidence-reference/REQ-APP-001/latest/`; running qgb against this
example produces an equivalent gate after timestamps and `run_id` are
normalised.

### Windows note: `python` must resolve from PATH

The S1 and S2 contracts invoke `["python", "-m", ...]`. This assumes
the executable `python` (or `python.exe` on Windows) is present on
`PATH` at qgb run time. On a Windows install that only exposes `py`
(the Python Launcher) — for example a stock Microsoft Store install
with no PATH addition — `python.exe` may not be reachable and S1
will fail with "command not found".

**This is intentional.** qgb's `command` verification_type executes
the argv declared in the contract literally; the contract is the
target project's promise about what it can run, not something qgb
rewrites per platform. Mixing `py -3` into the contract would break
non-Windows hosts (where `py` does not exist), and substituting
`sys.executable` would couple the contract to whichever Python qgb
itself runs under.

On a Windows host where only `py` is available, edit the local copy
of `.quality-system/contracts/REQ-APP-001/S1.json` and `S2.json` to
use `["py", "-3", "-m", ...]` for the duration of your work. Do not
commit that change; the reference contract stays as `python` so the
example is portable to POSIX hosts (Linux, macOS) where `python`
is the canonical resolver. Phase 2 may introduce contract aliases or
launcher policies; Phase 1 keeps the contract literal.
