"""Generate REQ meta, contract placeholders, and L1/L5 test dirs (Step 6d).

Phase 1 scaffold writes:

* ``.quality-system/req/<REQ>.meta.json``
* ``.quality-system/contracts/<REQ>/<stage>.json`` per stage in
  ``policy.json``
* ``tests/quality/L1_behavior/`` and ``tests/quality/L5_contract/``
  with a ``.gitkeep`` marker apiece

Generated contracts use **schema-valid placeholders**: every required
field is populated with a value the JSON schema accepts, but the values
are clearly intended to be replaced (``"TODO: ..."`` for strings, paths
that point at non-existing locations so ``qgb run`` fails rather than
falsely passes).

**Phase 1 scope (Codex 計画レビュー):**

* REQ id is validated against the same regex the schema enforces:
  ``^REQ-[A-Z0-9]+-[0-9]{3,}$``.
* If ``.quality-system/policy.json`` is missing, refuse with
  NOT_READY.
* If ``policy.json`` has no ``stages[]``, refuse with NOT_READY
  (design-stages --commit has not run yet).
* If the target REQ already has meta or contracts, refuse without
  ``--force``. With ``--force``, only the target REQ's files are
  replaced; ``policy.json`` and other REQs are untouched.

**Phase 1 out-of-scope:**

* L2 / L3 / L4 / L6 test scaffolding (those layers default to ``review``
  per spec §3.5 until Phase 2).
* Verification-type-aware "smart" contract synthesis (we use placeholders
  rather than inferring real commands / paths).
* Multi-REQ batch scaffolding.
* git operations (``init`` already manages ``.gitignore``).
* **Atomic --force overwrite** (Codex 補修 4): when ``--force`` rewrites
  the target REQ, meta / contracts / tests are updated in order without
  a temp-tree swap. A mid-write failure can leave the target REQ in a
  partially-rewritten state. Phase 2 should stage the new REQ tree to a
  sibling temp and swap. ``policy.json`` and other REQs are never
  touched by ``--force``, so the blast radius is bounded.
* **ScaffoldOutcome action classification** (Codex 補修 8): the
  ``created`` field is a flat list. Phase 2 may split this into
  ``created`` / ``updated`` / ``skipped`` once consumers (e.g. automation
  flows) need the distinction.
* **Duplicate stage id defense** (Codex 補修 9): scaffold trusts that
  ``validate-policy`` ran before it. If the policy contains duplicate
  stage ids, scaffold will overwrite the second contract file silently.
  Phase 1 contract is "run ``qgb validate-policy`` first"; Phase 2 may
  add a defensive duplicate check at scaffold entry.
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQ_ID_PATTERN = re.compile(r"^REQ-[A-Z0-9]+-[0-9]{3,}$")


@dataclass(frozen=True)
class ScaffoldOutcome:
    ok: bool
    req_id: str
    created: list[str] = field(default_factory=list)
    message: str = ""


def scaffold_req(
    project_root: Path,
    req_id: str,
    *,
    force: bool = False,
) -> ScaffoldOutcome:
    """Generate REQ meta + contracts + L1/L5 test dirs for ``req_id``.

    Returns a :class:`ScaffoldOutcome`; the CLI maps ``ok=False`` to
    EXIT_NOT_READY. Raises only on truly unexpected I/O failures.
    """
    if not REQ_ID_PATTERN.match(req_id):
        return ScaffoldOutcome(
            ok=False,
            req_id=req_id,
            message=(
                f"invalid REQ id '{req_id}'; expected ^REQ-[A-Z0-9]+-[0-9]{{3,}}$"
            ),
        )

    qs = project_root / ".quality-system"
    policy_path = qs / "policy.json"
    if not policy_path.is_file():
        return ScaffoldOutcome(
            ok=False,
            req_id=req_id,
            message=(
                "no .quality-system/policy.json — run `qgb init` and "
                "`qgb design-stages --commit` first"
            ),
        )

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    stages = policy.get("stages") or []
    if not stages:
        return ScaffoldOutcome(
            ok=False,
            req_id=req_id,
            message=(
                "policy.json has no stages[]; run `qgb design-stages "
                "--commit` first"
            ),
        )

    # Codex 補修 5: defensive shape validation. Without this a
    # malformed policy.json (missing stage id / verification_type) would
    # raise KeyError mid-scaffold and dump a traceback. validate-policy
    # would normally catch this earlier, but scaffold is also reachable
    # without it (e.g. hand-edited policy), so we guard here.
    for idx, stage in enumerate(stages):
        if not isinstance(stage, dict):
            return ScaffoldOutcome(
                ok=False,
                req_id=req_id,
                message=(
                    f"policy.json stages[{idx}] is not an object; "
                    f"run `qgb validate-policy` to inspect"
                ),
            )
        for required_key in ("id", "verification_type"):
            if required_key not in stage:
                return ScaffoldOutcome(
                    ok=False,
                    req_id=req_id,
                    message=(
                        f"policy.json stages[{idx}] is missing "
                        f"'{required_key}'; run `qgb validate-policy`"
                    ),
                )

    req_dir = qs / "req"
    contracts_dir = qs / "contracts" / req_id
    meta_path = req_dir / f"{req_id}.meta.json"

    if (meta_path.exists() or contracts_dir.exists()) and not force:
        return ScaffoldOutcome(
            ok=False,
            req_id=req_id,
            message=(
                f"REQ {req_id} already exists; pass --force to overwrite"
            ),
        )

    created: list[str] = []

    # 1. REQ meta.
    req_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "schema_version": "1.0",
        "req_id": req_id,
        "title": f"TODO: describe {req_id}",
        "stages": [
            {
                "stage_id": s["id"],
                "contract_ref": (
                    f".quality-system/contracts/{req_id}/{s['id']}.json"
                ),
                "required": True,
            }
            for s in stages
        ],
    }
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    created.append(str(meta_path.relative_to(project_root)))

    # 2. Contracts. Wipe any existing contracts dir if --force.
    if contracts_dir.exists() and force:
        shutil.rmtree(contracts_dir, ignore_errors=True)
    contracts_dir.mkdir(parents=True, exist_ok=True)
    for stage in stages:
        contract = _placeholder_contract(req_id, stage)
        path = contracts_dir / f"{stage['id']}.json"
        path.write_text(
            json.dumps(contract, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        created.append(str(path.relative_to(project_root)))

    # 3. L1 / L5 test dirs (Phase 1 focus).
    tests_root = project_root / "tests" / "quality"
    for layer in ("L1_behavior", "L5_contract"):
        layer_dir = tests_root / layer
        layer_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = layer_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
            created.append(str(gitkeep.relative_to(project_root)))

    return ScaffoldOutcome(
        ok=True,
        req_id=req_id,
        created=created,
        message=f"scaffolded {req_id}",
    )


def _placeholder_contract(req_id: str, stage: dict[str, Any]) -> dict[str, Any]:
    """Schema-valid contract with TODO placeholders.

    Per Codex 計画レビュー: every required field must satisfy the schema,
    but values are chosen so ``qgb run`` is unlikely to PASS by accident.
    """
    vtype = stage["verification_type"]
    contract: dict[str, Any] = {
        "schema_version": "1.0",
        "req_id": req_id,
        "stage_id": stage["id"],
        "verification_type": vtype,
    }

    if vtype == "command":
        contract["command"] = ["TODO-replace-with-command-argv"]
        contract["expected_exit_code"] = 0
    elif vtype == "file_exists":
        contract["target"] = f"TODO/{stage['id']}/placeholder-target.txt"
    elif vtype == "substring_match":
        contract["target"] = f"TODO/{stage['id']}/placeholder-target.txt"
        contract["must_contain"] = ["TODO-replace-with-substring"]
    elif vtype == "json_schema":
        contract["target"] = f"TODO/{stage['id']}/placeholder-target.json"
        contract["schema"] = (
            f"TODO/{stage['id']}/placeholder-schema.json"
        )
    elif vtype == "manual_check":
        contract["description"] = (
            "TODO: describe the manual check (philosophy P6: manual_check "
            "cannot be the sole basis for ALLOW)"
        )
    else:
        # Unknown verification_type: leave only the required base fields.
        # Validate would catch this anyway.
        pass

    return contract
