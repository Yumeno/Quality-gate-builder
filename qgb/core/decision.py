"""Compute the ALLOW/DENY judgement from per-stage results.

Phase 1 rule (matches requirements doc §6.4.2 and the curated gate schema):

* Every adopted stage is judgement material. If every adopted stage's
  ``result == passed`` → ``ALLOW``. Otherwise → ``DENY``, with
  ``failed_stage`` set to the *first* failed stage in execution order.

The ``required`` flag on REQ meta stages is constrained to
``const: true`` in Phase 1 (see ``req-meta.schema.json``), so this
function does not branch on it. Two design pressures point the same way:

* The curated ``gate.schema.json`` enforces "ALLOW implies every entry
  in stages[] has result=passed"; honouring an optional/failing stage
  while still emitting ALLOW would produce a schema-invalid gate.
* If a stage isn't authoritative, it should not be in the adopted
  set at all; "optional ALLOW basis" is a contradiction in terms.

Optional-stage semantics (e.g. "advisory checks") and waivers belong
to Phase 2 (knowledge integration); the schema-level rejection makes
sure Phase 1 designers can't write a misleading half-state.

Out of scope here (handled by ``preflight``):

* NOT_READY conditions (no REQ, missing contract, manual_check, etc.) are
  decided before the runner is called.

Step 7 added per-phase ``decision.meaning`` semantics:

* ``phase=red`` + DENY → "expected failure" wording
* ``phase=red`` + ALLOW → "unexpected pass" wording (suspicious; the new
  test should have failed)
* ``phase=verify`` + DENY → "signal to revise" wording (DENY is data,
  not a project verdict)
* ``phase=green/refactor`` → neutral implementation / refactor wording

The CLI keeps exit codes aligned with ``status`` regardless of phase
(ALLOW=0, DENY=1), so CI scripts can read either side without
special-casing phase=red.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from qgb.core.preflight import AdoptedStage
from qgb.core.runner import StageResult

Status = Literal["ALLOW", "DENY"]


# Codex RA2: keep ``decision.meaning`` strictly verbatim per F-016 so any
# downstream consumer that exact-matches this string is not broken. The
# project-local note (P11) is exposed separately as ``decision.scope``.
_DECISION_SCOPE_NOTE = (
    "Judgement is local to this project's policy/contracts and is not "
    "comparable across projects (P11)."
)


@dataclass(frozen=True)
class Decision:
    """ALLOW/DENY judgement plus the failing stage id (or empty).

    Step 6+7 統合レビュー (Codex RA2): ``meaning`` stays strictly
    verbatim per F-016 so exact-match consumers are not silently
    broken. The project-local note (P11) lives in ``scope`` as a
    separate field; ``gate.json#/decision/scope`` is emitted alongside
    ``decision.result`` / ``decision.meaning``.
    """

    status: Status
    failed_stage: str
    meaning: str
    scope: str = _DECISION_SCOPE_NOTE


# Per-phase ``decision.meaning`` strings. Wired to F-016 Step 7.
#
# Design notes (Codex 計画レビュー):
#
# * ``phase=red`` is the TDD red step: a failing test was just added and
#   the code is not yet implemented. DENY here is **expected** — the
#   meaning says so explicitly. ALLOW under phase=red is suspicious
#   (the new test should fail) and the meaning calls that out as
#   "unexpected pass" so an automated reader can flag it for review.
# * ``phase=green`` and ``phase=refactor`` use neutral implementation /
#   refactor wording. A DENY here is a normal failure.
# * ``phase=verify`` is the default for ad-hoc runs and uses
#   "revision signal" wording from F-016 instead of treating DENY as
#   a "failure" of the project.
# * Exit codes (in qgb/cli.py) are kept aligned with ``status``: ALLOW=0,
#   DENY=1 regardless of phase. The phase only changes what the gate
#   *means*, not what the CLI returns. This avoids CI scripts having
#   to special-case phase=red to read both exit code and gate.json.
_MEANING_BY_PHASE: dict[str, dict[Status, str]] = {
    "verify": {
        "ALLOW": "Defined checks passed. This is not proof of total correctness.",
        "DENY": (
            "Defined checks did not pass. This is not a failure but a "
            "signal to revise."
        ),
    },
    "green": {
        "ALLOW": (
            "Required checks passed against the freshly implemented code."
        ),
        "DENY": (
            "Implementation phase: at least one required check failed."
        ),
    },
    "refactor": {
        "ALLOW": (
            "Refactor phase: required checks remained passing after refactor."
        ),
        "DENY": (
            "Refactor phase: at least one previously-passing check regressed."
        ),
    },
    "red": {
        "ALLOW": (
            "Unexpected pass: phase=red expected the new test to fail before "
            "implementation. Inspect whether the test actually exercises the "
            "intended behaviour."
        ),
        "DENY": (
            "The required test fails as expected before implementation."
        ),
    },
}


def decide(
    adopted: list[AdoptedStage],
    results: list[StageResult],
    phase: str,
) -> Decision:
    """Return the ALLOW/DENY decision over the executed stages.

    Every non-waived adopted stage participates in the judgement: an
    ALLOW gate must have every such stage's ``result == passed`` (this
    matches the curated gate.schema.json's ``allOf`` constraint).

    Step 7 D: waived stages are excluded from the judgement entirely
    (their ``result`` is ``"waived"``, never ``"passed"``). A REQ whose
    adopted stages are *all* waived produces ``DENY`` rather than
    ALLOW — Phase 1 refuses to treat "no judgement material" as ALLOW
    because the curated gate's ALLOW semantics require at least one
    passed required check (philosophy P1 / P5: ALLOW must mean
    "defined required checks passed", not "nothing was checked").
    """
    results_by_id = {r.stage_id: r for r in results}
    failed_first = ""
    judgement_passed = 0
    for stage in adopted:
        result = results_by_id.get(stage.stage_id)
        # Waived stages are excluded from judgement.
        if result is not None and result.result == "waived":
            continue
        if result is None or result.result != "passed":
            failed_first = stage.stage_id
            break
        judgement_passed += 1

    if failed_first:
        status: Status = "DENY"
        # Codex A7: defensive postcondition. DENY with a non-empty
        # failed_first means at least one stage was inspected and
        # failed; nothing more to assert here.
    elif judgement_passed == 0:
        # Every adopted stage was waived (or none at all). Phase 1 does
        # not emit ALLOW with no judgement material — the user must
        # remove the waivers or accept a DENY signal that the REQ has
        # no automatic basis.
        #
        # Step 7 補修 (Codex 5): ``failed_stage`` stays empty here. It
        # used to be set to ``adopted[0].stage_id``, but that pointed
        # at a *waived* stage and made gate.json look like the waived
        # stage was the reason for DENY. The reason is "no judgement
        # material", which is a REQ-level condition, not a stage-level
        # one; surfacing a stage id would mislead automation that
        # reads ``failed_stage`` to locate the actual failure.
        status = "DENY"
        failed_first = ""
    else:
        status = "ALLOW"

    meaning_by_status = _MEANING_BY_PHASE.get(phase, _MEANING_BY_PHASE["verify"])

    # Codex A7: defensive postcondition. ``status=ALLOW`` must always be
    # backed by at least one non-waived passed stage. The branches above
    # already guarantee this, but the assert protects against a future
    # refactor that introduces a bypass path. Schema-side enforcement
    # (gate.schema.json#allOf for ALLOW + contains: passed) is the
    # second line of defense; this in-process check catches the
    # condition before evidence is even written.
    if status == "ALLOW":
        assert judgement_passed > 0, (
            f"decide() postcondition: ALLOW requires judgement_passed > 0, "
            f"got {judgement_passed}"
        )
    return Decision(
        status=status,
        failed_stage=failed_first,
        meaning=meaning_by_status[status],
    )
