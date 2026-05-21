"""Compute the ALLOW/DENY judgement from per-stage results.

Phase 1 rule (matches requirements doc §6.4.2):

* If every required adopted stage has ``result=passed`` → ``ALLOW``.
* Otherwise → ``DENY``, and ``failed_stage`` is set to the *first* failed
  required stage in execution order.

Out of scope here (handled by ``preflight`` and Step 7):

* NOT_READY conditions (no REQ, missing contract, manual_check, etc.) are
  decided before the runner is called.
* TDD phase=red expected-failure semantics will compose with this function
  in Step 7; for now ``decision.meaning`` is chosen per-phase by callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qgb.core.preflight import AdoptedStage
from qgb.core.runner import StageResult

Status = Literal["ALLOW", "DENY"]


@dataclass(frozen=True)
class Decision:
    """ALLOW/DENY judgement plus the failing stage id (or empty)."""

    status: Status
    failed_stage: str
    meaning: str


# Per-phase ``decision.meaning`` strings. Phase 1 only emits ``verify``;
# Step 7 will widen this when red/green/refactor are exposed.
_MEANING_BY_PHASE: dict[str, dict[Status, str]] = {
    "verify": {
        "ALLOW": "Defined checks passed. This is not proof of total correctness.",
        "DENY": "At least one required check failed. This is not a project-wide quality verdict.",
    },
    "green": {
        "ALLOW": "Implementation phase: defined checks passed.",
        "DENY": "Implementation phase: at least one required check failed.",
    },
    "refactor": {
        "ALLOW": "Refactor phase: defined checks continued to pass.",
        "DENY": "Refactor phase: at least one previously-passing check regressed.",
    },
    "red": {
        # Step 7 will override this; in Phase 1 we keep the same wording as
        # verify so an accidental --phase red still produces a sensible gate.
        "ALLOW": "Defined checks passed. This is not proof of total correctness.",
        "DENY": "At least one required check failed. This is not a project-wide quality verdict.",
    },
}


def decide(
    adopted: list[AdoptedStage],
    results: list[StageResult],
    phase: str,
) -> Decision:
    """Return the ALLOW/DENY decision over the executed stages."""
    results_by_id = {r.stage_id: r for r in results}
    failed_first = ""
    for stage in adopted:
        if not stage.required:
            continue
        result = results_by_id.get(stage.stage_id)
        if result is None or result.result != "passed":
            failed_first = stage.stage_id
            break

    status: Status = "ALLOW" if not failed_first else "DENY"
    meaning_by_status = _MEANING_BY_PHASE.get(phase, _MEANING_BY_PHASE["verify"])
    return Decision(
        status=status,
        failed_stage=failed_first,
        meaning=meaning_by_status[status],
    )
