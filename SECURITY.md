# Security Policy

This document covers three related but distinct topics:

1. **CI Action SHA pin policy** — how qgb's own CI workflow keeps its
   third-party-action surface small and pin-updated.
2. **Dependency Lock Policy** — how qgb pins its Python dependencies
   (jsonschema + transitives, plus dev tools) to specific versions
   and content hashes (Phase 3 Step 3.2).
3. **Reporting a vulnerability** — how to reach the maintainer with a
   security finding in qgb itself (the Python CLI / library).

The policy is **forward-looking only**. It governs maintenance from
Phase 3 Step 3.1 onward; pre-3.1 commits (which had no CI workflow)
are not retroactively in scope. Step 3.2 (dependency lock) builds
on the Step 3.1 SHA-pin discipline and uses the same update cadence.

## Action SHA Pin Policy

qgb's CI (`.github/workflows/test.yml`) uses third-party-action SHA
pins because:

- Tags are mutable on GitHub — a maintainer (or attacker with maintainer
  access) can move `v7` to point at arbitrary code.
- Commit SHAs are stable: once `actions/checkout@<SHA>` resolves, the
  bytes that run in our CI are fixed.
- NF-011 (サプライチェーンリスク管理) requires that every external
  artefact in qgb's build path be pinned to an immutable identifier.
  The CI surface is part of that.

The pinned actions, as of 2026-06-23:

| Action | Tag | SHA |
|---|---|---|
| `actions/checkout` | `v7.0.0` (2026-06-18) | `9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0` |
| `actions/setup-python` | `v6.2.0` (2026-01-22) | `a309ff8b426b58ec0e2a45f0f869d46889d02405` |

No third-party (non-`actions/*`) GitHub Actions are permitted in qgb's
CI. Adding one requires a documented rationale in the workflow file
**and** an entry here.

### Update Triggers

The maintainer reviews CI action pins on the following triggers,
listed by priority:

1. **Security advisory on the pinned action.** GitHub Security
   Advisories (GHSA), CVEs, or maintainer announcements affecting
   the running version. Updates may be expedited (within 7 days)
   when the advisory is rated High or Critical.
2. **GitHub hosted runner incompatibility.** When `ubuntu-latest`
   or `windows-latest` changes its default image in a way that
   breaks the pinned action, pin forward to the smallest fix.
3. **Python version support requirement.** When a new Python
   release crosses qgb's `requires-python` range and the existing
   `actions/setup-python` pin cannot resolve it.
4. **Scheduled review.** Once per quarter, on the last working
   week of January, April, July, and October. The review reads
   the GHSA feed for each pinned action and considers any
   accumulated upstream changes. Action: bump or document
   "reviewed, no change."
5. **Ad-hoc / opportunistic.** A maintainer may bump a pin for
   any documented reason (e.g. a useful feature in a newer
   release). Pure "latest is better" is **not** sufficient; the
   commit message must say what specifically improves.

"Completely ad-hoc with no documented reason" is **not** acceptable
under this policy — the goal is to keep human review of pin changes
non-zero so a compromised pin commit looks anomalous in `git log`.

### How To Update

1. Resolve the new tag to its commit SHA via the GitHub API:
   ```
   gh api repos/actions/<name>/git/refs/tags/<tag> --jq .object.sha
   ```
   Do not rely on the GitHub UI for the SHA — copy it from the API
   response or `git ls-remote`.
2. Edit `.github/workflows/test.yml` (and `release.yml`, which uses the
   same pins):
   - Replace the SHA in the `uses:` line.
   - Update the comment line above it with the new tag and date.
3. Update this file's pin table.
3b. Update the repository Actions allowlist to the new pins. The repo
   settings restrict runnable actions to exactly the pinned SHAs
   (`allowed_actions: selected` with `patterns_allowed`); a pin bump
   without this step will fail CI by design:
   ```
   gh api -X PUT repos/<owner>/<repo>/actions/permissions/selected-actions \
     -f "patterns_allowed[]=actions/checkout@<SHA>" \
     -f "patterns_allowed[]=actions/setup-python@<SHA>"
   ```
4. Commit as a **single-purpose commit** with the subject:
   ```
   CI: bump actions/<name> from <SHA1> to <SHA2> (<reason>)
   ```
   Reason is one of: `security advisory <ID>`, `runner image
   incompatibility`, `python <version> support`,
   `quarterly review`, or a short free-text explanation for ad-hoc
   updates.
5. Open a PR. CI will run with the new pin; if it passes, merge.
   If it fails, treat the new pin as suspect and investigate
   before retrying.

### Why no Dependabot / Renovate

qgb's editing philosophy (Phase 2: 編集は構造化された JSON Patch
経由、外部生成物は data であって命令ではない) is at odds with
auto-PR bots that periodically open code-changing pull requests
without human-initiated rationale. We intentionally keep the human
review loop in the path. See
`development/docs/journal/phase3-step3-1-prejournal.md`
§"3. なぜ supply-chain 厳格化" for the longer reasoning.

## Dependency Lock Policy

qgb pins its Python dependencies to specific versions **and** content
hashes via `pip-compile --generate-hashes` (Phase 3 Step 3.2). This
section defines the rules.

### Files and Layering

| File | Generated from | Constraint | Purpose |
|---|---|---|---|
| `requirements.lock` | `pyproject.toml` dependencies | (none) | Runtime supply-chain |
| `requirements-dev.lock` | `pyproject.toml` dev extras | `-c requirements.lock` | Development supply-chain |

`requirements-dev.lock` is generated with `--constraint=requirements.lock`,
so the dev resolution is forced to agree with the runtime resolution on
shared packages (jsonschema, attrs, …). This prevents the dev install
from silently upgrading or downgrading runtime pins.

The dev lock is generated with `--allow-unsafe` so that `pip`, `setuptools`,
and other build-time tooling pulled in by `pip-tools` are also pinned with
hashes. Without this flag, `pip install --require-hashes` would fail at
those packages.

### What the Lock Does and Does Not Cover

The lock is for **the qgb repository's own CI and contributor environments**.
It does NOT make `pip install qgb` from PyPI deterministic for arbitrary
users; that path resolves `jsonschema>=4.20,<5.0` afresh at install time.
What is reproducible is:

- The CI matrix install across Windows + Ubuntu × Python 3.10 + 3.12.
- A contributor or auditor running
  ```bash
  pip install --require-hashes --only-binary :all: -r requirements-dev.lock
  pip install --no-deps --no-build-isolation -e .
  ```
  The `--no-build-isolation` flag on the editable install is essential:
  without it, `pip` would spin up a fresh build venv and re-fetch
  `setuptools` / `wheel` from PyPI bypassing `--require-hashes`. With
  the dev lock already installed in the active env, build can reuse the
  hash-pinned `setuptools` / `wheel` instead.

For Phase 5 packaging, separate decisions will determine what (if any)
lock guarantees are extended to end users.

### Environment Used to Generate the Lock

The committed locks are regenerated **on Windows × Python 3.10**.
This matters because `pip-compile`'s resolution is per-(OS, Python),
and we want the lock to be the *superset* needed across the full
matrix (`windows-latest`/`ubuntu-latest` × Python 3.10/3.12):

- **Python markers** (`python_version<"3.13"`, `python_version<"3.11"`)
  gate transitives like `typing-extensions`, `exceptiongroup`, `tomli`.
  Generating on the lowest matrix Python (3.10) captures all of them.
- **OS markers** (`platform_system=="Windows"`,
  `sys_platform=="win32"`) gate transitives like `colorama` (pulled in
  by `click` + `pytest` on Windows only). Generating on Windows
  captures these.

A lock missing one of these transitives causes the corresponding
matrix cell to fail under `--require-hashes` because the install-time
resolver demands a pinned entry for every package the environment
markers select. A lock that contains the *superset* is safe everywhere:
unused entries are silently skipped by their environment markers on
platforms that do not need them.

The `lock-integrity` CI job runs on **`windows-latest` × Python 3.10**
for the same reason — it must regenerate under the same environment
the committer used, otherwise the diff against the committed lock is
spurious. The price is one extra Windows runner minute per push; the
benefit is that the integrity check is meaningful.

### Trust-Layer Boundary

The lock pins the **Python package supply chain** that ends up in the
qgb runtime / dev process. It does NOT control these adjacent layers,
which are pinned separately or treated as external trust:

| Layer | How it is controlled |
|---|---|
| GitHub Actions runners | `actions/checkout` + `actions/setup-python` SHA pins (see Action SHA Pin Policy above) |
| `pip` / `setuptools` / `wheel` (CI environment) | Whatever `actions/setup-python` ships, then overwritten by the dev lock install. The editable install runs with `--no-build-isolation` so that the build step reuses these hash-pinned versions instead of fetching fresh copies into an isolated build venv (which would bypass `--require-hashes`). |
| PEP 517 build backend (`setuptools>=68`, `wheel`) | `pyproject.toml [build-system].requires` — range, not lock at the package metadata level. But because we install with `--no-build-isolation`, the actual build invocation uses the hash-pinned `setuptools` / `wheel` from the dev lock. A future step may revisit pinning the metadata range itself. |
| Python interpreter itself | `actions/setup-python` resolution; not pinned to a patch version |
| PyPI artefact hashes | The lock pins this (the primary supply-chain control point for runtime / dev) |

The CI matrix is part of how this lock is validated: a single lock that
fails to install on any one of the four (OS, Python) combinations is a
sign the lock is overfit to one environment and the lock should be
regenerated. See `.github/workflows/test.yml` and the `lock-integrity`
job for the mechanical check.

The `lock-integrity` job answers a specific question: **"is the
committed lock consistent with the dependency ranges in the current
`pyproject.toml`?"** It does NOT answer "did upstream PyPI release a
newer compatible version since the lock was committed?" — the job
seeds pip-compile with the committed lock so existing pins are kept
unless `pyproject.toml` constraints force a change. Upstream releases
are picked up by the **periodic regenerate** flow under
"Update Triggers" below, not by this gate.

Detection of paid-out upgrade candidates (without changing the
committed lock) is intentionally out of scope; pin-bumping is a
human decision per `Why no Dependabot / Renovate`.

### Update Triggers

The maintainer regenerates locks on the following triggers, mirroring
the SHA pin policy above:

1. **Security advisory on a locked package.** GHSA / CVE on
   `jsonschema`, `attrs`, `referencing`, `rpds-py`,
   `jsonschema-specifications`, or any dev-side package. Updates may be
   expedited (within 7 days) when the advisory is rated High or Critical.
2. **`pyproject.toml` dependency change.** Adding, removing, or
   re-ranging a dependency requires regenerating locks in the same
   commit. The `lock-integrity` CI job enforces this mechanically.
3. **Python version support requirement.** A new Python release crossing
   qgb's `requires-python` range may move some transitive's resolution
   if the range was tight.
4. **Scheduled review.** Once per quarter, on the last working week of
   January, April, July, and October — same cadence as SHA pin review.
   Action: regenerate, diff, commit, or document "reviewed, no change."
5. **Ad-hoc / opportunistic.** A maintainer may regenerate for any
   documented reason. Pure "latest is better" is **not** sufficient;
   the commit message must say what specifically improves.

"Completely ad-hoc with no documented reason" is **not** acceptable
under this policy — the goal is to keep human review of lock changes
non-zero so a compromised lock commit looks anomalous in `git log`.

### How to Update

1. Update `pyproject.toml` if the trigger requires it (range bump,
   added/removed dependency, etc.).
2. Regenerate **on Windows × Python 3.10** (see "Environment Used to
   Generate the Lock" above). Use `py -3.10 -m piptools …`.
   Regenerating on POSIX is unsupported by this policy because the
   resulting lock will lack Windows-only transitives (`colorama`).
   Regenerate the runtime lock first, then the dev lock:
   ```powershell
   py -3.10 -m piptools compile --generate-hashes `
       --output-file=requirements.lock pyproject.toml
   py -3.10 -m piptools compile --generate-hashes --allow-unsafe `
       --extra=dev --constraint=requirements.lock `
       --output-file=requirements-dev.lock pyproject.toml
   ```
3. Verify locally before pushing:
   ```bash
   python -m pip install --require-hashes --only-binary :all: \
       -r requirements-dev.lock
   python -m pip install --no-deps --no-build-isolation -e .
   pytest -ra
   ```
   The `--no-build-isolation` flag mirrors what the `test` CI job does:
   without it, pip would bypass the hash-verified `setuptools` / `wheel`
   already in the env and re-fetch fresh copies into a build venv.
4. Commit `pyproject.toml`, `requirements.lock`, `requirements-dev.lock`
   together as a **single-purpose commit** with a subject like:
   ```
   deps: bump <package> from <old> to <new> (<reason>)
   ```
   Reason is one of: `security advisory <ID>`, `pyproject range change`,
   `python <version> support`, `quarterly review`, or a short free-text
   explanation for ad-hoc updates.
5. Open a PR. The `lock-integrity` job will refuse to merge if the
   committed locks disagree with what `pip-compile` regenerates from
   the current `pyproject.toml`.

### What This Policy Does NOT Manage (Out of Scope, User-Side Decision)

The following are **deliberately not** part of qgb's own CI surface;
they are decisions the downstream qgb operator makes per project. See
`development/docs/ci-examples.md` for non-prescriptive sample
configurations.

- **Lock artefact retention beyond git history.** qgb's locks are
  committed; `git show <sha>:requirements.lock` gives permanent access.
  Whether to also upload locks as 90-day CI artefacts, attach them to
  release tags, or push them to an external archive is the operator's
  call (and may be required by SOC2 / internal audit policy).
- **SBOM generation (CycloneDX / SPDX).** Same rationale: the lock plus
  `pip-tools`'s own metadata are enough for qgb's immediate supply-chain
  needs. SBOM tooling is for inventory / vulnerability workflows that
  belong to the operator.
- **Vulnerability scanning (pip-audit, safety, snyk, …).** Adding such
  a scan introduces a new external trust dependency (the vulnerability
  database) and a new failure mode (false positive blocks merges). The
  Phase 3 line is to keep qgb's CI a closed loop; vulnerability scans
  belong upstream of the qgb operator.
- **Private PyPI mirrors / proxies.** The lock is content-hash-pinned,
  so a mirror that serves the same bytes is acceptable; configuring
  one is operational, not qgb-side.

This non-coverage is intentional, not an oversight, and mirrors the
Phase 4 (CI 連携) withdrawal in `detailed-design.md` §14.3.

### Why pip-tools, Not uv / Poetry / pdm

`pip-tools` (Jazzband-maintained, not PyPA-official) was chosen because:

- It produces requirements files that the stock `pip` consumes natively;
  there is no separate resolver running inside `pip` at install time.
- It is dev-only; no runtime overhead, no new packaging style imposed
  on `pyproject.toml`.
- It is mature and narrowly scoped (compile + sync), so the surface
  added under NF-010 is small.
- `pip lock` is currently experimental and has platform-scope caveats
  that make it unsuitable for this step.
- `uv` (Rust, 2024+) is a strong contender but enlarges the toolchain
  beyond stdlib + pip. Revisitable in a future phase if the qgb-side
  trade-offs change.
- `poetry` / `pdm` would replace the build backend and the
  `pyproject.toml` schema; the cost of regression is not justified
  for one runtime dependency.

### SBOM History

An earlier review (Phase 2 close, 2026-06-13) initially marked SBOM as
WONTFIX, then reversed that judgement after a Codex second opinion
pointing out that `pip freeze` alone does not bind content hashes. The
current Step 3.2 landing — committed `requirements.lock` with
`--generate-hashes` + `--require-hashes` in CI — is the cheaper
substitute for the supply-chain control SBOM tools are usually adopted
to provide. SBOM proper remains out of scope.

## Reporting a Vulnerability

If you believe you have found a security issue in qgb itself
(command-injection vector, path-escape bypass, evidence-tamper path,
etc.), please **do not** open a public GitHub issue.

Instead, use GitHub's private vulnerability reporting:

- Repository: <https://github.com/Yumeno/Quality-gate-builder>
- Navigate to: *Security* → *Report a vulnerability*

Expected acknowledgement window: best-effort, within 14 days. The
project is maintained by a single developer; turnaround on
remediation depends on severity and complexity.

What to include in a report:

- A description of the issue and which qgb component is affected
  (CLI verb / module / schema).
- A reproducer: minimal `qgb` invocation, REQ files, contract.json,
  etc.
- Your assessment of severity (any of: data corruption, gate
  bypass, evidence tampering, host compromise).
- Optional: a proposed remediation or PR.

What is **out of scope**:

- Issues in PyPI itself or other dependencies' supply chains
  (file those with the upstream project; if a qgb-side mitigation
  is possible we will consider it under NF-011).
- Issues in the user's `contract.command` payloads that fail to
  meet the runner's documented contract (e.g. binaries that go
  rogue when run; that is the user's responsibility).
- Theoretical concerns without a reproducer.
