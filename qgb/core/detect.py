"""Detect orchestration: run every adapter and rank their results (Step 6c).

Per P9 ``core`` does not branch on language. The list of adapters is
hard-coded here for Phase 1; Phase 2 may switch to entry_points if
external plugins land. ``GenericAdapter`` is intentionally last so a
matching language-specific adapter always wins selection.

**Adapter responsibility split:**

* Each adapter inspects ``project_root`` independently and returns either
  a ``DetectedProjectProfile`` or ``None``.
* This module **composes** the results: it picks the highest-confidence
  profile as ``selected``, attaches the rest as ``candidates``, and
  applies the "exclude generic from candidates when a language-specific
  adapter matched" rule.
* The "why generic" annotation lives here (not in
  :class:`GenericAdapter`) so generic does not need to know about the
  other adapters' outcomes.
"""

from __future__ import annotations

from pathlib import Path

from qgb.adapters.base import (
    BaseAdapter,
    DetectedProjectProfile,
    DetectionEvidence,
    DetectionResult,
)
from qgb.adapters.generic import GenericAdapter
from qgb.adapters.python import PythonAdapter


def _default_adapters() -> list[BaseAdapter]:
    """The Phase 1 adapter order. Generic must be last."""
    return [PythonAdapter(), GenericAdapter()]


def run_detect(
    project_root: Path,
    adapters: list[BaseAdapter] | None = None,
) -> DetectionResult:
    """Run every adapter and return the composed :class:`DetectionResult`.

    ``adapters`` is exposed only so tests can supply a custom list. An
    explicit empty list is honoured (Codex 補修 4: do not silently fall
    back to defaults). Default order: language-specific adapters first,
    generic last.
    """
    if adapters is None:
        adapters = _default_adapters()
    profiles: list[DetectedProjectProfile] = []
    generic_profile: DetectedProjectProfile | None = None

    for adapter in adapters:
        profile = adapter.detect(project_root)
        if profile is None:
            continue
        # Codex 補修 5: dispatch on adapter.name (control plane) rather
        # than profile.adapter_name (data plane). An adapter that
        # mislabels its own profile cannot then derail composition.
        if adapter.name == "generic":
            # Hold generic separately; whether to include it depends on
            # whether any other adapter matched.
            generic_profile = profile
        else:
            profiles.append(profile)

    if profiles:
        # A language-specific adapter matched. Generic is excluded from
        # candidates per the calling convention; selected is the highest-
        # confidence language-specific profile (ties: registration order).
        selected = max(profiles, key=lambda p: p.confidence)
        return DetectionResult(selected=selected, candidates=profiles)

    # No language-specific match. Generic is mandatory in this branch.
    if generic_profile is None:
        # GenericAdapter is supposed to never return None; this is a
        # defensive last resort so callers always get a valid result.
        generic_profile = DetectedProjectProfile(
            language="generic",
            framework=None,
            test_runner=None,
            confidence=0.1,
            evidence=[
                DetectionEvidence(
                    kind="fallback",
                    where=".",
                    note="no adapter (including generic) returned a profile",
                )
            ],
            adapter_name="generic",
        )
    else:
        # Annotate why generic was selected. The generic adapter itself
        # does not know whether it was a fallback or a co-equal candidate;
        # only core.detect has that context.
        generic_profile = DetectedProjectProfile(
            language=generic_profile.language,
            framework=generic_profile.framework,
            test_runner=generic_profile.test_runner,
            confidence=generic_profile.confidence,
            evidence=[
                *generic_profile.evidence,
                DetectionEvidence(
                    kind="fallback",
                    where=".",
                    note="no language-specific adapter matched",
                ),
            ],
            adapter_name=generic_profile.adapter_name,
        )
    return DetectionResult(
        selected=generic_profile,
        candidates=[generic_profile],
    )
