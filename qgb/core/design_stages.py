"""Stage design proposal & commit (Step 6d).

Phase 1 rule-based suggestion: pick a template from ``examples/`` based on
the language reported by :func:`qgb.core.detect.run_detect`, copy its
``policy.json#stages`` as a starting point, and let the user adopt or
discard. The proposal phase is read-only; commit is handled separately
by :func:`commit_design`.

**Phase 1 scope (per Codex 計画レビュー 2026-05-31):**

* Template source is the real ``examples/<name>/.quality-system/policy.json``
  file — not an in-code dict. This keeps templates and ``qgb run`` inputs
  in lockstep.
* Phase 1 ships exactly one template: ``examples/generic-minimal``. Python
  CLI / Markdown detections also fall back to it; ``detect`` output is
  reflected in the human message but not in template selection.
* Atomic commit copies the project's ``.quality-system/`` to a temp tree,
  edits the temp ``policy.json``, runs ``validate_policy_preflight`` over
  the temp tree, and only ``os.replace``-swaps the real ``policy.json``
  if validation passes.

**Phase 1 out-of-scope:**

* Concurrent ``design-stages --commit`` (single-writer assumption).
* Template merge / partial overwrite.
* Interactive edit mode (``--interactive`` / ``--revise`` are Phase 2).
* LLM-based template selection or stage authoring.
* git integration (``init`` already manages ``.gitignore``).
* Filesystem locking, fsync durability.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgb.adapters.base import DetectionResult
from qgb.core.detect import run_detect

# Phase 1 templates live in the repo's examples/ tree, located by walking
# up from this file.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATES_DIR = _REPO_ROOT / "examples"

# Phase 1: the only available template. detect() output influences the
# human-readable banner but does not change the template choice.
_DEFAULT_TEMPLATE = "generic-minimal"


# ---- proposal phase ------------------------------------------------------


@dataclass(frozen=True)
class StageProposal:
    """A single stage entry suggested to the user."""

    id: str
    name: str
    responsibility: str
    depends_on: list[str]
    verification_type: str
    required_contract_fields: list[str]


@dataclass(frozen=True)
class DesignProposal:
    """Aggregate output of the proposal phase.

    Codex 補修 7: ``committed`` was removed from this dataclass. The
    proposal is pure data about what *could* be adopted; commit state
    lives in :class:`CommitOutcome` and in the CLI's JSON envelope.
    Conflating them invited a "proposal carries its own commit status"
    misuse pattern that would have to be unwound in Phase 2 anyway.
    """

    template: str
    stages: list[StageProposal]
    detect: DetectionResult
    warnings: list[str] = field(default_factory=list)


def propose_design(project_root: Path) -> DesignProposal:
    """Build a :class:`DesignProposal` for ``project_root``.

    The proposal phase does not touch the project's ``.quality-system/``.
    """
    detect_result = run_detect(project_root)
    template_name = _pick_template(detect_result)
    stages = _load_template_stages(template_name)
    return DesignProposal(
        template=template_name,
        stages=stages,
        detect=detect_result,
    )


def _pick_template(_detect_result: DetectionResult) -> str:
    """Phase 1: always return the default template.

    Per the Codex 計画レビュー, Python and Markdown detections fall back
    to ``generic-minimal``; only the banner reflects the real language.
    """
    return _DEFAULT_TEMPLATE


def _load_template_stages(template_name: str) -> list[StageProposal]:
    template_path = (
        _TEMPLATES_DIR
        / template_name
        / ".quality-system"
        / "policy.json"
    )
    if not template_path.is_file():
        raise FileNotFoundError(
            f"design-stages template not found: {template_path}"
        )
    payload = json.loads(template_path.read_text(encoding="utf-8"))
    raw_stages = payload.get("stages", [])
    out: list[StageProposal] = []
    for raw in raw_stages:
        out.append(
            StageProposal(
                id=raw["id"],
                name=raw["name"],
                responsibility=raw.get("responsibility", ""),
                depends_on=list(raw.get("depends_on", [])),
                verification_type=raw["verification_type"],
                required_contract_fields=list(
                    raw.get("required_contract_fields", [])
                ),
            )
        )
    return out


# ---- commit phase --------------------------------------------------------


@dataclass(frozen=True)
class CommitOutcome:
    """Result of an attempted policy commit."""

    ok: bool
    policy_path: Path | None
    blockers: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    message: str = ""


def commit_design(
    project_root: Path,
    proposal: DesignProposal,
    *,
    force: bool = False,
) -> CommitOutcome:
    """Atomically replace ``policy.json#stages`` with the proposal's stages.

    Flow (Step 6b 風 atomic swap, Codex 計画レビューで採用):

    1. Refuse if no ``.quality-system/`` (the user must run ``qgb init``).
    2. Refuse if ``policy.json#stages`` is non-empty unless ``force=True``.
    3. Copy ``.quality-system/`` to a sibling staging tree.
    4. Rewrite the staging ``policy.json`` with the proposed stages.
    5. Run ``validate_policy_preflight`` against the staging tree.
    6. If any blocker, abort without touching the real policy.
    7. Otherwise, write the staged policy contents to a tmp file next to
       the real policy and ``os.replace`` it into place.

    The original ``policy.json`` is left untouched on any failure.
    """
    qs = project_root / ".quality-system"
    policy_path = qs / "policy.json"
    if not policy_path.is_file():
        return CommitOutcome(
            ok=False,
            policy_path=None,
            message=(
                "no .quality-system/policy.json — run `qgb init` first"
            ),
        )

    current = json.loads(policy_path.read_text(encoding="utf-8"))
    if current.get("stages") and not force:
        return CommitOutcome(
            ok=False,
            policy_path=policy_path,
            message=(
                "policy.json already has stages; pass --force to replace"
            ),
        )

    # Stage to a sibling temp project so validate-policy can run on disk.
    # Codex 補修 1/2: use tempfile.mkdtemp() instead of a fixed name so
    # a pre-existing user directory named "<project>.qgb-stage" is not
    # silently destroyed, and concurrent commits do not collide.
    staging_parent_template = f"{project_root.name}.qgb-stage-"
    staging_root = Path(
        tempfile.mkdtemp(
            prefix=staging_parent_template,
            dir=project_root.parent,
        )
    )
    # mkdtemp created an empty dir; replace it with a recursive copy.
    shutil.rmtree(staging_root)
    shutil.copytree(project_root, staging_root)

    staged_policy_path = staging_root / ".quality-system" / "policy.json"
    new_policy = dict(current)
    new_policy["stages"] = [_stage_to_dict(s) for s in proposal.stages]
    staged_policy_path.write_text(
        json.dumps(new_policy, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Validate the staged tree.
    from qgb.core.preflight import validate_policy_preflight

    report = validate_policy_preflight(staging_root, None)
    if report.has_blockers():
        blockers = [
            {"kind": i.kind, "where": i.where, "message": i.message}
            for i in report.blocking_issues()
        ]
        shutil.rmtree(staging_root, ignore_errors=True)
        return CommitOutcome(
            ok=False,
            policy_path=policy_path,
            blockers=blockers,
            message="staged policy failed validate-policy",
        )

    # All clear: replace the real policy atomically. Codex 補修 3: write
    # to a unique sibling tmp file (NamedTemporaryFile) so a pre-existing
    # policy.json.tmp left over from another process is not destroyed.
    staged_text = staged_policy_path.read_text(encoding="utf-8")
    fd, tmp_path_str = tempfile.mkstemp(
        prefix="policy.json.",
        suffix=".tmp",
        dir=policy_path.parent,
    )
    tmp_path = Path(tmp_path_str)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(staged_text)
    try:
        os.replace(tmp_path, policy_path)
    finally:
        shutil.rmtree(staging_root, ignore_errors=True)
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    warnings = [
        {"kind": i.kind, "where": i.where, "message": i.message}
        for i in report.warnings()
    ]
    return CommitOutcome(
        ok=True,
        policy_path=policy_path,
        warnings=warnings,
        message="policy.json updated",
    )


def _stage_to_dict(stage: StageProposal) -> dict[str, Any]:
    return {
        "id": stage.id,
        "name": stage.name,
        "responsibility": stage.responsibility,
        "depends_on": list(stage.depends_on),
        "verification_type": stage.verification_type,
        "required_contract_fields": list(stage.required_contract_fields),
    }
