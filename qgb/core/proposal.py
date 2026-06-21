"""Pattern B external-LLM interface core (Phase 2 Step 2.5).

qgb never calls an LLM (Pattern B / memory qgb-llm-boundary). This module
implements the two structured endpoints an external tool talks to:

* :func:`build_proposal_context` — export the project's design-relevant
  state as one JSON document (the *input material* for an external LLM).
  P8 / NF-007 framing is machine-readable metadata (``document_kind`` /
  ``intended_use`` / ``contains_executable_instructions: false``), not a
  natural-language plea — the safety responsibility for how an LLM is
  prompted lives in the Phase 5 skill, outside qgb.
* :func:`adopt_proposal` — import a proposal document (shape:
  ``proposal.schema.json``, ``proposal_type="policy_stages"``: a
  declarative FULL replacement of ``policy.json#stages``), validate it
  against the **same world** the project actually lives in (project-wide
  + every existing REQ, prejournal §3-1), and atomically swap
  ``policy.json`` only when nothing breaks.

Validation order is a **stable API** (Codex Step 2.5 計画レビュー指摘 2;
Phase 5 skills machine-match ``AdoptError.reason``):

1. ``read_error``                 — proposal file unreadable
2. ``invalid_json``               — proposal file is not JSON / not UTF-8
3. ``schema_invalid``             — violates proposal.schema.json
4. ``unsupported_schema_version`` — schema_version not in the supported set
5. ``unsupported_proposal_type``  — proposal_type not in the supported set
6. ``policy_build_failed``        — current policy.json unreadable / not an
   object, so a new policy document cannot be assembled
7. ``policy_schema_invalid``      — assembled policy violates policy.schema.json
8. ``policy_preflight_failed``    — same-world validation found blockers
   (detail carries per-scope findings: which REQ breaks, what kind, where)
9. ``atomic_write_failed``        — sibling-tmp swap failed

``reason`` strings are stable; ``detail`` payloads are NOT a stable API
(informational only).

Evidence policy (prejournal §1-3): adopt appends NOTHING to
knowledge.jsonl — like ``qgb patch``, source-of-truth edits are audited
via git. P7 is served by the result carrying ``proposal_sha256`` /
``policy_before_sha256`` / ``policy_after_sha256`` / ``applied_at`` /
``source_metadata`` so CI / Phase 5 skills can persist a verifiable trail.

Known tension (recorded, not changed here): same-world validation
includes the knowledge-orphan scan, so a pre-existing orphaned waiver
blocks adopt (and policy patch) of even unrelated changes until the
orphan is repaired — consistent with Step 2.2/2.3 patch behaviour;
waiver removal tooling is Phase 3.

Destructive renames are intentionally rejected in one shot: the
supported migration is **3 段移行** — (a) adopt an additive proposal
keeping old stages, (b) migrate each REQ meta via ``qgb patch``,
(c) adopt a removal proposal once nothing references the old stages.
One-shot rename needs the Phase 3 multi-doc transaction.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgb.core.evidence import make_timestamps
from qgb.core.loader import (
    LoaderError,
    load_policy,
    load_project_context,
    load_req_meta,
    quality_system_root,
)
from qgb.core.patch_apply import PatchApplyError, _atomic_write_json
from qgb.core.preflight import (
    collect_same_world_blockers,
    collect_same_world_warnings,
    list_req_ids,
    validate_policy_preflight_same_world,
)
from qgb.core.schema import validate as schema_validate

__all__ = [
    "AdoptError",
    "AdoptResult",
    "PROPOSAL_CONTEXT_DOCUMENT_KIND",
    "SUPPORTED_PROPOSAL_SCHEMA_VERSIONS",
    "SUPPORTED_PROPOSAL_TYPES",
    "adopt_proposal",
    "build_proposal_context",
]

PROPOSAL_CONTEXT_DOCUMENT_KIND = "qgb.proposal_context"
SUPPORTED_PROPOSAL_SCHEMA_VERSIONS = frozenset({"1.0"})
SUPPORTED_PROPOSAL_TYPES = frozenset({"policy_stages"})

# Mirrors policy.schema.json's enum; exported in the context so external
# tools do not have to parse our schema files to learn the vocabulary.
_VERIFICATION_TYPES = (
    "command",
    "file_exists",
    "substring_match",
    "json_schema",
    "manual_check",
)


@dataclass(frozen=True)
class AdoptError(ValueError):
    """Raised when :func:`adopt_proposal` rejects a proposal.

    ``reason`` is one of the nine stable strings in the module docstring
    (in validation order). ``detail`` is informational, not stable.
    """

    reason: str
    message: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.message} (reason={self.reason})"


@dataclass
class AdoptResult:
    """Successful (or dry-run) outcome of :func:`adopt_proposal`.

    The three sha256 hashes are the P7 trail: ``proposal_sha256`` is the
    raw bytes of the proposal file, ``policy_before_sha256`` the bytes of
    policy.json before the swap, ``policy_after_sha256`` the exact bytes
    written (or that would be written, for dry-run). ``applied_at`` is
    RFC3339 UTC, ``None`` for dry-run.
    """

    target: Path
    would_write: bool
    written: bool
    proposal_sha256: str
    policy_before_sha256: str
    policy_after_sha256: str
    applied_at: str | None
    source_metadata: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# propose-context
# ---------------------------------------------------------------------------


def build_proposal_context(project_root: Path) -> dict[str, Any]:
    """Assemble the structured export an external LLM tool reads.

    Contents (Phase 3 Step 3.0 で構造更新 — deliberately minimal and stable):
    project_context (target project's self-declaration, optional),
    current policy.json verbatim, REQ inventory (id / title / adopted
    stage ids with required+waived flags), and a machine-readable
    constraints summary. Contract bodies, knowledge.jsonl and
    project-context.md are intentionally excluded.

    **Phase 3 Step 3.0 change**: the ``detect`` field (machine-derived
    language / framework / test_runner) was removed. The target project's
    self-understanding is now expressed via ``project-context.json``
    (a human-authored or agent-assisted declaration with
    ``human_reviewed: bool``). When ``project-context.json`` is absent,
    ``project_context`` is ``None`` and the external LLM is expected to
    read the target project directly to form its own understanding —
    consistent with Phase 5 skill responsibility (対象理解は LLM、
    ALLOW/DENY は qgb の contract 実行結果で決まる).

    Raises :class:`qgb.core.loader.LoaderError` when policy.json is
    missing/unreadable (the CLI maps it to NOT_READY) — a project must
    be ``qgb init``-ed before its context can be exported.
    """
    project_context = load_project_context(project_root)
    policy = load_policy(project_root)

    reqs: list[dict[str, Any]] = []
    for req_id in list_req_ids(project_root):
        try:
            meta = load_req_meta(project_root, req_id)
        except LoaderError as exc:
            # An unreadable meta is part of the world the LLM must know
            # about (its stages cannot be migrated blindly).
            reqs.append({"req_id": req_id, "load_error": exc.message})
            continue
        stages = [
            {
                "stage_id": entry.get("stage_id"),
                "required": bool(entry.get("required", True)),
                "waived": bool(entry.get("waived", False)),
            }
            for entry in (meta.get("stages") or [])
            if isinstance(entry, dict)
        ]
        reqs.append(
            {
                "req_id": req_id,
                "title": meta.get("title", ""),
                "stages": stages,
            }
        )

    # Phase 3 Step 3.0: collect advisory warnings about the context's
    # provenance. Most important: project_context.human_reviewed=false
    # signals that the declaration is provisional (an agent may have
    # drafted it without human approval) — external LLMs should weigh
    # human_reviewed=true content more strongly per P8.
    warnings: list[str] = []
    if isinstance(project_context, dict):
        reviewed = project_context.get("human_reviewed")
        if reviewed is not True:
            warnings.append(
                "project_context.human_reviewed is not true; the target "
                "project's self-declaration has not been approved by a "
                "human reviewer and should be treated as provisional "
                "(P8: only explicit user declarations should anchor "
                "design decisions)"
            )
    return {
        # P8 framing: machine-readable metadata, not prose (prejournal §1-4).
        "document_kind": PROPOSAL_CONTEXT_DOCUMENT_KIND,
        "schema_version": "1.0",
        "intended_use": "external_tool_input_data",
        "contains_executable_instructions": False,
        # Phase 3 Step 3.0: project_context replaces detect. None when the
        # target project has not declared its context via project-context.json.
        "project_context": project_context,
        "policy": policy,
        "reqs": reqs,
        "constraints": {
            "verification_types": list(_VERIFICATION_TYPES),
            "manual_check_rule": (
                "manual_check cannot be the basis of a required ALLOW "
                "stage (philosophy P6); qgb run rejects it"
            ),
            "recommended_stage_count": {"min": 3, "max": 7},
            "stage_id_rule": (
                "stage ids are free-form but must be unique within the "
                "policy; depends_on must reference existing ids and form "
                "a DAG"
            ),
            "contract_layout": (
                ".quality-system/contracts/<REQ>/<stage>.json (canonical; "
                "anything else is rejected as misplaced_contract)"
            ),
            "existing_req_compatibility": (
                "adopt validates the proposed stages against every "
                "existing REQ; removing or renaming a stage that a REQ "
                "meta still references is rejected. Migrate in three "
                "steps: additive adopt, per-REQ meta patch, removal adopt"
            ),
        },
        "expected_response": {
            "schema": "proposal.schema.json",
            "proposal_type": "policy_stages",
            "semantics": (
                "stages[] is a declarative FULL replacement of "
                "policy.json#stages; policy_id is optional (current id "
                "is preserved when absent)"
            ),
        },
        # Advisory warnings about the export (Phase 3 Step 3.0). Always
        # present (empty list when nothing to warn about) so consumers can
        # rely on the field's existence.
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# adopt
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def adopt_proposal(
    project_root: Path,
    proposal_path: Path,
    *,
    dry_run: bool = False,
) -> AdoptResult:
    """Validate an external proposal and atomically apply it to policy.json.

    See the module docstring for the nine-step validation order (stable
    API). Every reject path leaves policy.json untouched; only step 9
    writes, via the sibling-tmp + ``os.replace`` swap shared with the
    patch substrate.
    """
    # 1. read_error
    try:
        raw = proposal_path.read_bytes()
    except OSError as exc:
        raise AdoptError(
            reason="read_error",
            message=f"cannot read proposal file {proposal_path}: {exc}",
        ) from exc
    proposal_sha256 = _sha256(raw)

    # 2. invalid_json — strip UTF-8 BOM (PS5.1 Out-File writes BOM)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AdoptError(
            reason="invalid_json",
            message=f"proposal file {proposal_path} is not valid JSON: {exc}",
        ) from exc
    try:
        proposal = json.loads(text)
    except (ValueError, json.JSONDecodeError) as exc:
        raise AdoptError(
            reason="invalid_json",
            message=f"proposal file {proposal_path} is not valid JSON: {exc}",
        ) from exc

    # 3. schema_invalid (RecursionError guard: deep-nest JSON can blow the
    # C stack inside jsonschema — surface as schema_invalid, not a raw traceback)
    try:
        issues = schema_validate(proposal, "proposal")
    except RecursionError as exc:
        raise AdoptError(
            reason="schema_invalid",
            message="proposal document is nested too deeply for validation",
        ) from exc
    if issues:
        raise AdoptError(
            reason="schema_invalid",
            message=(
                f"proposal violates proposal.schema.json "
                f"({len(issues)} issue(s))"
            ),
            detail={
                "issues": [
                    {
                        "path": i.path,
                        "message": i.message,
                        "schema_path": i.schema_path,
                    }
                    for i in issues
                ]
            },
        )

    # 4. unsupported_schema_version
    version = proposal["schema_version"]
    if version not in SUPPORTED_PROPOSAL_SCHEMA_VERSIONS:
        raise AdoptError(
            reason="unsupported_schema_version",
            message=(
                f"proposal schema_version {version!r} is not supported; "
                f"supported: {sorted(SUPPORTED_PROPOSAL_SCHEMA_VERSIONS)}"
            ),
        )

    # 5. unsupported_proposal_type
    ptype = proposal["proposal_type"]
    if ptype not in SUPPORTED_PROPOSAL_TYPES:
        raise AdoptError(
            reason="unsupported_proposal_type",
            message=(
                f"proposal_type {ptype!r} is not supported; "
                f"supported: {sorted(SUPPORTED_PROPOSAL_TYPES)}"
            ),
        )

    # 6. policy_build_failed — assemble the new policy from the current
    # one. The current policy must itself be a readable JSON object; we
    # keep everything except stages (and policy_id when proposed) so
    # unknown-but-valid extra fields survive the adopt.
    policy_path = quality_system_root(project_root) / "policy.json"
    try:
        before_bytes = policy_path.read_bytes()
    except OSError as exc:
        raise AdoptError(
            reason="policy_build_failed",
            message=(
                f"cannot build new policy: current {policy_path} is "
                f"unreadable: {exc}"
            ),
        ) from exc
    try:
        current = json.loads(before_bytes.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AdoptError(
            reason="policy_build_failed",
            message=(
                f"cannot build new policy: current {policy_path} is not "
                f"valid JSON: {exc}"
            ),
        ) from exc
    if not isinstance(current, dict):
        raise AdoptError(
            reason="policy_build_failed",
            message=(
                f"cannot build new policy: current {policy_path} root is "
                f"not a JSON object"
            ),
        )
    policy_before_sha256 = _sha256(before_bytes)

    new_policy: dict[str, Any] = dict(current)
    new_policy["stages"] = proposal["stages"]
    if "policy_id" in proposal:
        new_policy["policy_id"] = proposal["policy_id"]

    # 7. policy_schema_invalid
    issues = schema_validate(new_policy, "policy")
    if issues:
        raise AdoptError(
            reason="policy_schema_invalid",
            message=(
                f"assembled policy violates policy.schema.json "
                f"({len(issues)} issue(s))"
            ),
            detail={
                "issues": [
                    {
                        "path": i.path,
                        "message": i.message,
                        "schema_path": i.schema_path,
                    }
                    for i in issues
                ]
            },
        )

    # 8. policy_preflight_failed — same-world validation (prejournal §3-1).
    reports = validate_policy_preflight_same_world(
        project_root, policy_override=new_policy
    )
    blockers = collect_same_world_blockers(reports)
    if blockers:
        raise AdoptError(
            reason="policy_preflight_failed",
            message=(
                f"proposed policy breaks the current world: "
                f"{len(blockers)} blocker(s) across project/REQ scopes"
            ),
            detail={"blockers": blockers},
        )
    warnings = [
        f"[{w['scope']}] {w['kind']} at {w['where']}: {w['message']}"
        for w in collect_same_world_warnings(reports)
    ]

    encoded = (
        json.dumps(new_policy, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    policy_after_sha256 = _sha256(encoded)
    source_metadata_raw = proposal.get("source_metadata")
    source_metadata: dict[str, Any] = (
        source_metadata_raw if isinstance(source_metadata_raw, dict) else {}
    )

    if dry_run:
        return AdoptResult(
            target=policy_path,
            would_write=True,
            written=False,
            proposal_sha256=proposal_sha256,
            policy_before_sha256=policy_before_sha256,
            policy_after_sha256=policy_after_sha256,
            applied_at=None,
            source_metadata=source_metadata,
            warnings=warnings,
        )

    # 9. atomic_write_failed — reuse the patch substrate's sibling-tmp
    # swap so write semantics cannot drift between patch and adopt (the
    # same deliberate private reuse as check.py -> evidence helpers).
    try:
        _atomic_write_json(policy_path, new_policy)
    except PatchApplyError as exc:
        raise AdoptError(
            reason="atomic_write_failed",
            message=exc.message,
        ) from exc

    return AdoptResult(
        target=policy_path,
        would_write=True,
        written=True,
        proposal_sha256=proposal_sha256,
        policy_before_sha256=policy_before_sha256,
        policy_after_sha256=policy_after_sha256,
        applied_at=make_timestamps().rfc3339,
        source_metadata=source_metadata,
        warnings=warnings,
    )
