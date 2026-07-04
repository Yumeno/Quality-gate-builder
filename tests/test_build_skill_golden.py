from __future__ import annotations

"""tests/test_build_skill_golden.py -- golden fixture byte-equality tests for
tools/build_skill.py (Phase 5 Step 5.b stage 4).

Golden layout: tools/_golden/<agent>/<mode>/ (acceptance-matrix.md notation).
The converter's own build output layout is dist/skills/<mode>/<agent>/ (the
transpose).  These tests perform the (mode, agent) -> golden path mapping
themselves; nothing about the mapping is the production code's concern.

Goldens are the SOURCE_DATE_EPOCH-unset lineage only (prejournal Sec.3.3).
The golden-compare test forces SOURCE_DATE_EPOCH unset for the duration of
its build so a polluted CI/dev environment can't produce a spurious digest
mismatch against committed goldens.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from build_skill import build_all  # noqa: E402

_GOLDEN_ROOT = _REPO_ROOT / "tools" / "_golden"
_SKILLS_SOURCE = _REPO_ROOT / "skills" / "source"

_MODES = ("full", "split")
_AGENTS = ("claude", "codex")


def _walk_files(root: Path) -> dict[str, Path]:
    result = {}
    for p in root.rglob("*"):
        if p.is_file():
            result[str(p.relative_to(root)).replace(os.sep, "/")] = p
    return result


# ---------------------------------------------------------------------------
# 1. golden byte-equality: real skills/source build vs tools/_golden/
# ---------------------------------------------------------------------------


def test_build_matches_golden_exactly(tmp_path, monkeypatch):
    """Building real skills/source must match tools/_golden/ cell-by-cell:
    same set of relative paths (no extra, no missing) and byte-identical
    content for every file.
    """
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)

    dist_dir = tmp_path / "dist_skills"
    build_all(
        source_dir=_SKILLS_SOURCE,
        dist_dir=dist_dir,
        repo_root=_REPO_ROOT,
        source_date_epoch_raw=None,
    )

    all_missing: list[str] = []
    all_extra: list[str] = []
    all_mismatches: list[str] = []

    for mode in _MODES:
        for agent in _AGENTS:
            cell_label = f"{agent}/{mode}"
            dist_cell = dist_dir / mode / agent
            golden_cell = _GOLDEN_ROOT / agent / mode

            assert dist_cell.is_dir(), f"build did not produce cell {mode}/{agent}"
            assert golden_cell.is_dir(), f"golden cell missing: {golden_cell}"

            dist_files = _walk_files(dist_cell)
            golden_files = _walk_files(golden_cell)

            for rel in sorted(set(dist_files) - set(golden_files)):
                all_missing.append(f"{cell_label}/{rel} (built but not in golden)")
            for rel in sorted(set(golden_files) - set(dist_files)):
                all_extra.append(f"{cell_label}/{rel} (in golden but not built)")
            for rel in sorted(set(dist_files) & set(golden_files)):
                if dist_files[rel].read_bytes() != golden_files[rel].read_bytes():
                    all_mismatches.append(f"{cell_label}/{rel}")

    assert not all_missing and not all_extra and not all_mismatches, (
        "Golden mismatch.\n"
        f"  Built but not in golden ({len(all_missing)}): {all_missing}\n"
        f"  In golden but not built ({len(all_extra)}): {all_extra}\n"
        f"  Byte mismatches ({len(all_mismatches)}): {all_mismatches}\n"
        "If this is an intentional change to any of the 8 build_input_digest "
        "categories, regenerate goldens with `python tools/regen_golden.py` "
        "and commit the updated tools/_golden/ tree in the SAME commit."
    )


# ---------------------------------------------------------------------------
# 2. golden tree shape: exactly the 4 expected cell dirs + README.md
# ---------------------------------------------------------------------------


def test_golden_tree_contains_only_expected_entries():
    """tools/_golden/ top level must be exactly {claude, codex, README.md},
    and claude/codex must each contain exactly {full, split}.
    """
    top_entries = {p.name for p in _GOLDEN_ROOT.iterdir()}
    assert top_entries == {"claude", "codex", "README.md"}, (
        f"Unexpected top-level entries in tools/_golden/: {top_entries}"
    )

    for agent in _AGENTS:
        agent_dir = _GOLDEN_ROOT / agent
        mode_entries = {p.name for p in agent_dir.iterdir()}
        assert mode_entries == set(_MODES), (
            f"Unexpected entries under tools/_golden/{agent}/: {mode_entries}"
        )


# ---------------------------------------------------------------------------
# 3. regen_golden.py refuses when SOURCE_DATE_EPOCH is set
# ---------------------------------------------------------------------------


def test_regen_golden_refuses_when_source_date_epoch_set():
    """regen_golden.py must exit 2 and not touch tools/_golden/ when
    SOURCE_DATE_EPOCH is set in the environment.
    """
    env = dict(os.environ)
    env["SOURCE_DATE_EPOCH"] = "1735689600"

    result = subprocess.run(
        [sys.executable, str(_TOOLS_DIR / "regen_golden.py")],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "SOURCE_DATE_EPOCH" in result.stderr
