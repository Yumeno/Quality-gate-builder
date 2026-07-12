# CI examples for qgb operators (non-prescriptive)

This document is a **reference**, not a specification. The decisions
shown below are intentionally **out of scope** for qgb's own CI
(`.github/workflows/test.yml`), per the line drawn in Phase 3 Step 3.2:

> qgb's own CI is the mechanical-check device for the qgb codebase
> itself (P6, P7 against qgb's own test suite). How a downstream qgb
> operator preserves evidence, scans for vulnerabilities, or fans out
> reports is **operator-side** and varies with the host project's
> compliance, audit, and tooling stack.

Use the snippets below as starting points. None of them are required
for qgb to function; qgb works fine in environments without any CI at
all (a local checkout + `pip install -r requirements.lock --require-hashes`
is enough).

For the canonical, scoped-down qgb CI surface, see
`.github/workflows/test.yml` and `SECURITY.md`'s
"Dependency Lock Policy" / "Action SHA Pin Policy" sections.

The expectation is that **Phase 5 Skill Creator** will eventually
generate richer, project-shape-aware CI templates for users. The
samples here are a much smaller stopgap: enough to illustrate the
"there are many valid choices here" point, not enough to be a finished
template library.

---

## When does any of this matter?

If you, the qgb operator, need to:

- Hold a snapshot of "what dependencies were resolved on day X" past
  90 days, or past the lifetime of GitHub-hosted artefact retention.
- Produce an SBOM for SOC2, internal procurement, vendor risk review,
  or supply-chain reporting.
- Run third-party vulnerability databases against the dependency set.
- Re-publish qgb's results in a JUnit / SARIF / OSV format that some
  upstream system consumes.

…then one or more of the patterns below may apply. None of them are
the qgb runtime's responsibility; all of them are wrappers around the
qgb invocation.

---

## Pattern A — Long-term lock-file retention via CI artefact

If the operator's audit policy requires preserving the exact
dependency resolution beyond `git show <sha>:requirements.lock`
(which is in principle permanent, but only as permanent as the host
git repository), upload the lock as a CI artefact:

```yaml
# Append this to a CI job that already has the locks checked out.
# This sample uses GitHub Actions; adapt to GitLab CI, Buildkite, etc.
#
# IMPORTANT: This is YOUR workflow, not qgb's. If you adopt it, you
# also adopt the supply-chain implications of upload-artifact (one more
# external action surface to track for security advisories, per
# qgb's own SHA-pin policy if you wish to mirror that discipline).
- name: Upload locks as evidence artefact
  uses: actions/upload-artifact@<COMMIT_SHA>  # Pin to SHA, not tag.
  with:
    name: dependency-locks-${{ github.sha }}
    path: |
      requirements.lock
      requirements-dev.lock
    retention-days: 365  # Per your audit policy.
```

**Why qgb does not do this in its own CI:** `git` already preserves
the locks per commit forever (as long as the repo is preserved); a
90-day or 365-day artefact is purely an operator's convenience for
audit-tool consumption. Adding `upload-artifact` to qgb's own CI
would expand the SHA-pinned third-party-action surface for no
qgb-internal benefit.

---

## Pattern B — SBOM generation as a side artefact

If the operator's downstream toolchain expects CycloneDX or SPDX
inventory documents, generate them from the lock files:

```yaml
# Sample only — verify the chosen SBOM tool is itself trustworthy
# (this is the same supply-chain question one step up).
- name: Install SBOM tool
  run: python -m pip install --require-hashes --only-binary :all: \
       -r your-operator-side-sbom-tool.lock

- name: Generate CycloneDX SBOM from runtime lock
  run: |
    cyclonedx-py requirements requirements.lock \
        --output-format json --output-file sbom-runtime.json

- name: Upload SBOM
  uses: actions/upload-artifact@<COMMIT_SHA>
  with:
    name: sbom-${{ github.sha }}
    path: sbom-runtime.json
```

**Why qgb does not do this:** SBOM is inventory-for-downstream-tools.
qgb's supply-chain risk is already addressed by `--require-hashes`
on the lock; SBOM proper exists to feed vulnerability scanners and
procurement workflows, which are operator concerns.

---

## Pattern C — Vulnerability scanning

If the operator runs a vulnerability database against the dependency
set as part of merge gating:

```yaml
- name: Install pip-audit
  run: python -m pip install --require-hashes --only-binary :all: \
       -r your-operator-side-pip-audit.lock

- name: Audit runtime lock
  run: pip-audit --requirement requirements.lock --strict

- name: Audit dev lock
  run: pip-audit --requirement requirements-dev.lock --strict
  # The --strict flag is intentional: a vulnerability in the dev
  # toolchain is still a supply-chain finding worth blocking on,
  # even if it doesn't ship to users.
```

**Why qgb does not do this:** A vulnerability scan introduces a
dependency on an external advisory database (PyPI Advisory DB,
GitHub Advisory DB, Sonatype OSS Index, …). Each database has
different update cadences, different false-positive rates, and
different blocking semantics. Choosing one is an operator-policy
decision; qgb's own CI keeps a closed loop.

---

## Pattern D — JUnit-style reports for upstream CI integration

If the operator wants pytest results in JUnit XML for an external CI
dashboard (Jenkins, Bamboo, internal reporting):

```yaml
- name: Run pytest with JUnit output
  run: pytest -ra --junitxml=test-results.xml

- name: Upload JUnit report
  uses: actions/upload-artifact@<COMMIT_SHA>
  with:
    name: junit-${{ github.sha }}
    path: test-results.xml
```

**Why qgb does not do this:** `gate.json` (qgb's own evidence
format) is intentionally scoped to qgb's per-REQ decision model,
not to generic CI report formats; trying to be both is a Phase 4
withdrawal (see `detailed-design.md` §14.3). JUnit XML and
gate.json answer different questions.

---

## Pattern E — Operator-side dependency-update bot (Dependabot / Renovate)

qgb's own repository deliberately does not run Dependabot or Renovate
(see `SECURITY.md` "Why no Dependabot / Renovate"). Downstream
operators who depend on qgb as a library may choose differently for
their own repositories:

- If you re-publish qgb on a private index (PyPI mirror), pinning to a
  specific qgb release tag and updating that pin on a human-reviewed
  cadence is more aligned with qgb's own discipline than auto-PR bots.
- If you must use a bot, configure it to update qgb's pin but **not**
  to auto-update qgb's transitive dependencies in your operator-side
  lock; let qgb's release process (with refreshed locks) drive that.

This is operator policy, not qgb policy.

---

## Pattern F — Evidence-to-source binding snapshot (short-term answer to Issue #32)

qgb's `gate.json` records what was executed and what passed, but it does
NOT self-describe *which revision of the sources it judged* (no
provenance block yet — Issue #32 tracks the design space). The binding
is an operational discipline: run the gate, then immediately fix the
evidence and the sources in the same commit. Nothing detects it when
that discipline slips.

This pattern converts the discipline into a recorded snapshot: a sidecar
JSON next to the curated evidence, capturing the VCS revision and a
digest of the gate's configuration files. A later auditor can then check
what HEAD and which contract/policy bytes the run saw.

Two caveats, stated plainly:

- The sidecar is written by YOUR wrapper, not by qgb — its integrity is
  your responsibility, and it proves nothing about files it does not
  hash. The digest below covers the gate *configuration*
  (contract + policy), not the full input closure of your checks.
- This is a **git-specific reference profile**. qgb itself does not
  assume git (a target project may use no VCS at all). A manifest-based
  variant for non-git projects follows.

The sidecar is written NEXT TO `latest/` (not inside it) because qgb
owns the contents of `latest/` and replaces the whole directory
atomically on the next run.

The sidecar shape is shared across all three variants below:

```json
{
  "snapshot_kind": "git",
  "taken_at": "2026-07-12T03:15:00+09:00",
  "qgb_exit_code": 0,
  "vcs": {
    "kind": "git",
    "revision": "b1c2d3e4f5a6...",
    "dirty": false
  },
  "configuration_digest": {
    "algorithm": "sha256",
    "files": {
      ".quality-system/policy.json": "9f2c...",
      ".quality-system/contracts/REQ-APP-001/L1-static.json": "3a7e..."
    }
  }
}
```

(non-git projects use `"vcs": {"kind": "none"}` — see F-3.) The field is
named `configuration_digest`, not `input_digest` or `source_digest` —
it deliberately does not claim to cover every file your checks read.

### F-1 git snapshot wrapper (PowerShell)

```powershell
# run-with-provenance.ps1
# Usage: .\run-with-provenance.ps1 -ReqId REQ-APP-001 [-RequireClean]
param(
    [Parameter(Mandatory = $true)][string]$ReqId,
    [switch]$RequireClean
)

$ErrorActionPreference = 'Stop'

if ($RequireClean) {
    $status = git status --porcelain
    if ($status) {
        Write-Error "Working tree is dirty; -RequireClean was requested. Commit or stash first."
        exit 1
    }
}

# Run qgb; capture its exit code without letting PowerShell's own
# error preference mask it.
& .venv\Scripts\python.exe -m qgb run $ReqId --yes
$qgbExitCode = $LASTEXITCODE

$revision = (git rev-parse HEAD).Trim()
# Exclude paths that the gate run itself (and this wrapper) legitimately
# mutates -- evidence, volatile artifacts, and the sidecar. Without the
# exclusion, dirty would be true after every run and the field would
# carry no information about the SOURCES the gate judged.
$dirty = [bool](git status --porcelain -- ':(exclude).quality-system/evidence' ':(exclude).quality-system/artifacts')

$configFiles = @()
$configFiles += Get-ChildItem -Path ".quality-system\contracts\$ReqId" -Filter *.json -File -ErrorAction SilentlyContinue
if (Test-Path ".quality-system\policy.json") {
    $configFiles += Get-Item ".quality-system\policy.json"
}

$digest = [ordered]@{}
foreach ($f in $configFiles) {
    $relPath = (Resolve-Path -Relative $f.FullName) -replace '^\.\\', '' -replace '\\', '/'
    $hash = (Get-FileHash -Path $f.FullName -Algorithm SHA256).Hash.ToLower()
    $digest[$relPath] = $hash
}

$sidecar = [ordered]@{
    snapshot_kind = "git"
    taken_at = (Get-Date).ToString("yyyy-MM-ddTHH:mm:sszzz")
    qgb_exit_code = $qgbExitCode
    vcs = [ordered]@{
        kind = "git"
        revision = $revision
        dirty = $dirty
    }
    configuration_digest = [ordered]@{
        algorithm = "sha256"
        files = $digest
    }
}

$outPath = ".quality-system\evidence\$ReqId\latest.provenance.json"
$json = $sidecar | ConvertTo-Json -Depth 10
# Write BOM-less UTF-8 explicitly; PowerShell 5's default Out-File
# encoding is not UTF-8-without-BOM.
[System.IO.File]::WriteAllText((Resolve-Path -Path (Split-Path $outPath -Parent)).Path + "\" + (Split-Path $outPath -Leaf), $json, (New-Object System.Text.UTF8Encoding($false)))

exit $qgbExitCode
```

### F-2 git snapshot wrapper (bash)

```bash
#!/usr/bin/env bash
# run-with-provenance.sh
# Usage: ./run-with-provenance.sh REQ-APP-001 [--require-clean]
set -euo pipefail

req_id="$1"
require_clean="${2:-}"

if [ "$require_clean" = "--require-clean" ]; then
    if [ -n "$(git status --porcelain)" ]; then
        echo "Working tree is dirty; --require-clean was requested. Commit or stash first." >&2
        exit 1
    fi
fi

# Run qgb; capture its exit code without letting `set -e` short-circuit
# the rest of the snapshot logic.
qgb_exit_code=0
.venv/bin/python -m qgb run "$req_id" --yes || qgb_exit_code=$?

revision="$(git rev-parse HEAD)"
# Same exclusion rationale as the PowerShell variant above.
if [ -n "$(git status --porcelain -- ':(exclude).quality-system/evidence' ':(exclude).quality-system/artifacts')" ]; then
    dirty=true
else
    dirty=false
fi

taken_at="$(date -u +%Y-%m-%dT%H:%M:%S+00:00)"

files_json="{}"
config_files=(".quality-system/policy.json")
if [ -d ".quality-system/contracts/$req_id" ]; then
    while IFS= read -r -d '' f; do
        config_files+=("$f")
    done < <(find ".quality-system/contracts/$req_id" -name '*.json' -print0)
fi

entries=()
for f in "${config_files[@]}"; do
    [ -f "$f" ] || continue
    hash="$(sha256sum "$f" | cut -d' ' -f1)"
    entries+=("\"$f\": \"$hash\"")
done
files_json="{$(IFS=,; echo "${entries[*]}")}"

cat > ".quality-system/evidence/$req_id/latest.provenance.json" <<EOF
{
  "snapshot_kind": "git",
  "taken_at": "$taken_at",
  "qgb_exit_code": $qgb_exit_code,
  "vcs": {
    "kind": "git",
    "revision": "$revision",
    "dirty": $dirty
  },
  "configuration_digest": {
    "algorithm": "sha256",
    "files": $files_json
  }
}
EOF

exit "$qgb_exit_code"
```

### F-3 non-git manifest variant

For projects that do not use git (or use a VCS qgb has no special
knowledge of), maintain a `provenance-manifest.txt` listing one path
per line (the files that matter for your judgment — typically the
contracts and policy, optionally extending to the checked sources
themselves). A small Python script reads that manifest and hashes each
listed file into the same sidecar shape:

```python
#!/usr/bin/env python3
# snapshot_provenance.py
# Usage: python snapshot_provenance.py REQ-APP-001 --exit-code 0
#
# Run this immediately AFTER `qgb run`, not before — the digest must
# reflect the files as they existed when qgb produced its evidence.
import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("req_id")
    parser.add_argument("--exit-code", type=int, required=True)
    parser.add_argument("--manifest", default="provenance-manifest.txt")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    files: dict[str, str] = {}
    if manifest_path.exists():
        for line in manifest_path.read_text(encoding="utf-8-sig").splitlines():
            rel = line.strip()
            if not rel or rel.startswith("#"):
                continue
            p = Path(rel)
            if p.is_file():
                files[rel] = sha256_of(p)

    sidecar = {
        "snapshot_kind": "manifest",
        "taken_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "qgb_exit_code": args.exit_code,
        "vcs": {"kind": "none"},
        "configuration_digest": {
            "algorithm": "sha256",
            "files": files,
        },
    }

    out_dir = Path(".quality-system/evidence") / args.req_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "latest.provenance.json"
    out_path.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

---

## What Phase 5 will likely add

Once `skills/source/` and `tools/build_skill.py` exist
(Phase 5 — Skill Creator), the Skill Creator will be able to read a
target project's `project-context.json` and generate a CI workflow
tailored to that project's shape (Python service vs CLI vs document
collection vs prompt collection vs …). At that point this document
will be largely superseded for projects that adopt the Skill Creator
path.

Until then, the patterns here exist to communicate one thing:
**qgb's own CI minimalism is a deliberate scope decision, not a gap
to be papered over by adding more steps to `test.yml`.**
