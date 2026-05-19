"""Load and validate JSON sources of truth against bundled JSON Schemas."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import resources
from importlib.resources.abc import Traversable
from typing import Any

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
}


def _json_pointer_escape(token: object) -> str:
    """Escape a JSON Pointer reference token per RFC 6901 §4."""
    s = str(token)
    return s.replace("~", "~0").replace("/", "~1")


def _to_pointer(parts: object) -> str:
    """Convert a jsonschema deque/iterable of path tokens to an RFC 6901 pointer."""
    tokens = list(parts) if parts is not None else []
    if not tokens:
        return ""
    return "/" + "/".join(_json_pointer_escape(t) for t in tokens)


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


def _build_format_checker() -> FormatChecker:
    """Return a FormatChecker that enforces the formats qgb relies on.

    ``jsonschema`` ships built-in checkers for ``date``, ``email``, ``ipv4``,
    ``ipv6``, ``regex``, and ``uuid`` (and ``idn-email``). It does NOT enforce
    ``date-time`` by default (it requires the optional ``rfc3339-validator``
    package). qgb relies on ``date-time`` for gate.json timestamps and
    knowledge entries, so we register a checker here using only the stdlib
    (preserving NF-010, minimal dependencies). The checker validates the
    RFC3339 *shape* qgb uses (YYYY-MM-DDTHH:MM:SS[.fff](Z|±HH:MM)); it does
    not aim for full RFC3339 conformance (e.g. leap seconds).
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


_FORMAT_CHECKER = _build_format_checker()


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
