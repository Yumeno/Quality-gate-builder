"""Load and validate JSON sources of truth against bundled JSON Schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from typing import Any

# Step 3.1e: ``Traversable`` lives in ``importlib.resources.abc`` on
# Python >= 3.12, but only in ``importlib.abc`` on 3.10 / 3.11 (the
# resources.abc submodule does not exist there). pyproject.toml says
# requires-python = ">=3.10", so we have to support both. The
# importlib.abc location is deprecated in 3.12+ and slated for
# removal in 3.14 — until 3.12 becomes the floor, the runtime probe
# below is the supported pattern.
try:
    from importlib.resources.abc import Traversable
except ImportError:  # Python < 3.12
    from importlib.abc import Traversable

import jsonschema
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_FILES = {
    "config": "config.schema.json",
    "policy": "policy.schema.json",
    "req-meta": "req-meta.schema.json",
    "contract": "contract.schema.json",
    "gate": "gate.schema.json",
    "gate-runtime": "gate.runtime.schema.json",
    "knowledge": "knowledge.schema.json",
    # Phase 2 Step 2.2: JSON Patch subset documents accepted by `qgb patch`.
    "patch": "patch.schema.json",
    # Phase 2 Step 2.5: external proposal documents accepted by
    # `qgb design-stages adopt` (Pattern B).
    "proposal": "proposal.schema.json",
    # Phase 3 Step 3.0: target project's self-declaration
    # (.quality-system/project-context.json). Mediates between human prose
    # (project-context.md) and machine consumers (propose-context output,
    # Phase 5 skills). Replaces the detect/adapter mechanism.
    "project-context": "project-context.schema.json",
}


def _json_pointer_escape(token: object) -> str:
    """Escape a JSON Pointer reference token per RFC 6901 §4.

    Phase 2 Step 2.2 で実装は :mod:`qgb.core.json_pointer` に移植された
    (P9 集約)。ここでは呼び出し互換のため private alias として残す。
    """
    from qgb.core import json_pointer
    return json_pointer.encode([token]).lstrip("/")


def _to_pointer(parts: object) -> str:
    """Convert a jsonschema deque/iterable of path tokens to an RFC 6901 pointer.

    Phase 2 Step 2.2 で実装は :mod:`qgb.core.json_pointer` に移植された
    (P9 集約)。ここでは呼び出し互換のため private alias として残す。
    """
    from qgb.core import json_pointer
    tokens = list(parts) if parts is not None else []
    return json_pointer.encode(tokens)


def schemas_root() -> Traversable:
    """Return the bundled schemas directory as an ``importlib.resources.Traversable``.

    Use this when you need to enumerate or inspect the bundled schemas without
    materialising real on-disk paths (which would break wheel/zip installs).
    """
    return resources.files("qgb").joinpath("schemas")


def load_schema(name: str) -> dict[str, Any]:
    """Load a bundled schema by short name (e.g. "gate", "policy").

    Reads via ``importlib.resources`` so the package works both as an editable
    install on disk and as an installed wheel.
    """
    if name not in SCHEMA_FILES:
        raise KeyError(f"Unknown schema name: {name!r}. Known: {sorted(SCHEMA_FILES)}")
    resource = schemas_root().joinpath(SCHEMA_FILES[name])
    with resource.open("r", encoding="utf-8") as fh:
        return json.load(fh)


_RFC3339_DATE_TIME_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def build_qgb_format_checker() -> FormatChecker:
    """Return a FormatChecker that enforces the formats qgb relies on.

    ``jsonschema`` ships built-in checkers for ``date``, ``email``, ``ipv4``,
    ``ipv6``, ``regex``, and ``uuid`` (and ``idn-email``). It does NOT enforce
    ``date-time`` by default (it requires the optional ``rfc3339-validator``
    package). qgb relies on ``date-time`` for gate.json timestamps and
    knowledge entries, so we register a checker here using only the stdlib
    (preserving NF-010, minimal dependencies). The checker validates the
    RFC3339 *shape* qgb uses (YYYY-MM-DDTHH:MM:SS[.fff](Z|±HH:MM)); it does
    not aim for full RFC3339 conformance (e.g. leap seconds).

    Phase 2 Step 2.1: this helper became public so the ``json_schema``
    verification runner (``qgb/core/runner.py``) can share the same checker
    when ``contract.enforce_format=true``. Centralising the format set in
    one place keeps P9 (single responsibility): one canonical answer to
    "which formats does qgb actually check?".
    """
    checker = FormatChecker()
    # Copy the bundled checkers from the canonical FORMAT_CHECKER (date, email,
    # ipv4, ipv6, regex, uuid, idn-email) into our instance.
    for fmt, func in Draft202012Validator.FORMAT_CHECKER.checkers.items():
        checker.checkers[fmt] = func

    @checker.checks("date-time", raises=(ValueError, TypeError))
    def _check_date_time(value: object) -> bool:
        if not isinstance(value, str):
            return False
        if not _RFC3339_DATE_TIME_RE.match(value):
            raise ValueError(f"not in the RFC3339 date-time shape qgb uses: {value!r}")
        # Final sanity check via fromisoformat (Python 3.11+ accepts the trailing Z).
        # Python 3.10 needs "Z" replaced with "+00:00".
        candidate = value.replace("Z", "+00:00") if value.endswith("Z") else value
        datetime.fromisoformat(candidate)
        return True

    return checker


def qgb_format_names() -> frozenset[str]:
    """Return the set of format names that ``build_qgb_format_checker`` checks.

    Used by the ``json_schema`` runner to compute
    ``formats_seen`` / ``formats_checked`` / ``formats_ignored`` for the
    evidence log (Codex Step 2.1 計画レビュー指摘 3). The set is computed once
    at module import and never mutated, so callers can cache it.
    """
    return _QGB_FORMAT_NAMES


_FORMAT_CHECKER = build_qgb_format_checker()
_QGB_FORMAT_NAMES: frozenset[str] = frozenset(_FORMAT_CHECKER.checkers.keys())


def get_validator(schema_name: str) -> Draft202012Validator:
    """Build a Draft 2020-12 validator with format checking enabled.

    The ``format_checker`` instance enforces ``date-time`` (qgb-defined, via
    stdlib) on top of the formats that ship with jsonschema.
    """
    schema = load_schema(schema_name)
    return Draft202012Validator(schema, format_checker=_FORMAT_CHECKER)


@dataclass(frozen=True)
class ValidationIssue:
    """A single JSON Schema validation error."""

    path: str          # RFC 6901 JSON Pointer into the instance, e.g. "/stages/0/responsibility"
    message: str
    schema_path: str   # RFC 6901 JSON Pointer into the schema that produced the error

    @classmethod
    def from_error(cls, err: jsonschema.ValidationError) -> ValidationIssue:
        return cls(
            path=_to_pointer(err.absolute_path),
            message=err.message,
            schema_path=_to_pointer(err.absolute_schema_path),
        )


def _sort_key(issue: ValidationIssue) -> tuple[str, str, str]:
    return (issue.path, issue.schema_path, issue.message)


def validate(instance: Mapping[str, Any], schema_name: str) -> list[ValidationIssue]:
    """Validate an instance against the named schema. Returns issues (empty = valid).

    Issues are sorted by (instance path, schema path, message) for stable output.
    """
    validator = get_validator(schema_name)
    issues = [ValidationIssue.from_error(e) for e in validator.iter_errors(instance)]
    return sorted(issues, key=_sort_key)


def is_valid(instance: Mapping[str, Any], schema_name: str) -> bool:
    """Convenience: True iff the instance has zero validation issues."""
    return not validate(instance, schema_name)
