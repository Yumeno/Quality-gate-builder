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
