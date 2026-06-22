# Security Policy

This document covers two related but distinct topics:

1. **CI Action SHA pin policy** — how qgb's own CI workflow keeps its
   third-party-action surface small and pin-updated.
2. **Reporting a vulnerability** — how to reach the maintainer with a
   security finding in qgb itself (the Python CLI / library).

The policy is **forward-looking only**. It governs maintenance from
Phase 3 Step 3.1 onward; pre-3.1 commits (which had no CI workflow)
are not retroactively in scope.

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
2. Edit `.github/workflows/test.yml`:
   - Replace the SHA in the `uses:` line.
   - Update the comment line above it with the new tag and date.
3. Update this file's pin table.
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
