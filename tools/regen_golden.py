"""regen_golden.py -- Regenerate tools/_golden/ from a real build_skill.py build.

Phase 5 Step 5.b stage 4.  This script is NOT a digest input: it only moves
already-built files into the golden tree, it never changes anything build_skill.py
reads to compute build_input_digest.  Running this script twice (with no other
change) reproduces byte-identical golden content, because the underlying build
is deterministic (SOURCE_DATE_EPOCH unset lineage).

Golden layout: tools/_golden/<agent>/<mode>/ (acceptance-matrix.md notation),
which is the transpose of the converter's own output layout dist/skills/<mode>/<agent>/
(see tools/build_skill.py AGENT_TO_HOOK_DIRNAME comment area and
development/docs/skill-converter/acceptance-matrix.md "golden fixture" row).
This script performs the <mode>/<agent> -> <agent>/<mode> remap when copying.

Usage:
    python tools/regen_golden.py

Exit codes:
    0  -- success, tools/_golden/{claude,codex}/ regenerated
    2  -- SOURCE_DATE_EPOCH is set in the environment (refuse; golden is the
          unset-epoch lineage only, prejournal Sec.3.3)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_GOLDEN_ROOT = _REPO_ROOT / "tools" / "_golden"
_BUILD_SCRIPT = _REPO_ROOT / "tools" / "build_skill.py"

# (mode, agent) pairs the converter is expected to produce.  Kept in sync with
# metadata.yaml's build_modes x target_agents (currently 2 x 2 = 4 cells).
_MODES = ("full", "split")
_AGENTS = ("claude", "codex")


def main() -> int:
    if os.environ.get("SOURCE_DATE_EPOCH") is not None:
        print(
            "[regen_golden] ERROR: SOURCE_DATE_EPOCH is set in the environment. "
            "tools/_golden/ is the SOURCE_DATE_EPOCH-unset lineage only "
            "(prejournal Sec.3.3); unset it before regenerating goldens.",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory(prefix="qgb_regen_golden_") as tmp_str:
        tmp_dist = Path(tmp_str) / "dist_skills"

        # Build via subprocess (public CLI surface, --dist-dir override) with
        # SOURCE_DATE_EPOCH explicitly removed from the child environment even
        # if some other mechanism reintroduced it between the check above and
        # here (defense in depth; the check above is authoritative).
        child_env = dict(os.environ)
        child_env.pop("SOURCE_DATE_EPOCH", None)

        result = subprocess.run(
            [
                sys.executable,
                str(_BUILD_SCRIPT),
                "--dist-dir",
                str(tmp_dist),
            ],
            cwd=str(_REPO_ROOT),
            env=child_env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(
                f"[regen_golden] ERROR: build_skill.py failed (exit {result.returncode})",
                file=sys.stderr,
            )
            print(result.stdout, file=sys.stderr)
            print(result.stderr, file=sys.stderr)
            return 2

        # Wipe only the <agent> subtrees under tools/_golden/, never README.md
        # (or anything else that might live alongside the golden cells).
        _GOLDEN_ROOT.mkdir(parents=True, exist_ok=True)
        for agent in _AGENTS:
            agent_dir = _GOLDEN_ROOT / agent
            if agent_dir.exists():
                shutil.rmtree(agent_dir)

        file_counts: dict[str, int] = {}
        for mode in _MODES:
            for agent in _AGENTS:
                src_cell = tmp_dist / mode / agent
                dest_cell = _GOLDEN_ROOT / agent / mode
                dest_cell.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_cell, dest_cell)
                count = sum(1 for p in dest_cell.rglob("*") if p.is_file())
                file_counts[f"{agent}/{mode}"] = count

    total = sum(file_counts.values())
    print(f"[regen_golden] OK  (total files={total})")
    for cell_name in sorted(file_counts):
        print(f"  {cell_name}: {file_counts[cell_name]} files")

    return 0


if __name__ == "__main__":
    sys.exit(main())
