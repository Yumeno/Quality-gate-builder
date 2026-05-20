"""Validate the JSON sources of truth under a project's .quality-system/ tree."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgb.core.schema import ValidationIssue, validate

# Per-verification_type allowed field set for contract.json. Anything outside
# the base fields ("schema_version", "req_id", "stage_id", "verification_type")
# and the allowed set for the declared verification_type is rejected as
# "field mismatch" by qgb validate. See requirements doc §F-005.
_CONTRACT_BASE_FIELDS: frozenset[str] = frozenset(
    {"schema_version", "req_id", "stage_id", "verification_type"}
)

_CONTRACT_TYPE_FIELDS: dict[str, frozenset[str]] = {
    "command": frozenset({"command", "expected_exit_code", "working_dir", "timeout_seconds"}),
    "file_exists": frozenset({"target"}),
    "substring_match": frozenset({"target", "must_contain"}),
    "json_schema": frozenset({"target", "schema"}),
    "manual_check": frozenset({"description"}),
}


@dataclass(frozen=True)
class FileIssue:
    """A single validation problem tied to a concrete file on disk."""

    file: Path
    schema_name: str
    issue: ValidationIssue


@dataclass(frozen=True)
class FieldMismatch:
    """A contract.json has a field that does not belong to its verification_type."""

    file: Path
    verification_type: str
    field_name: str

    def as_message(self) -> str:
        return (
            f"{self.file}: field {self.field_name!r} is not allowed for "
            f"verification_type={self.verification_type!r}"
        )


@dataclass
class ValidateReport:
    """Aggregated result of `qgb validate`."""

    schema_issues: list[FileIssue] = field(default_factory=list)
    field_mismatches: list[FieldMismatch] = field(default_factory=list)
    read_errors: list[tuple[Path, str]] = field(default_factory=list)
    files_checked: list[tuple[Path, str]] = field(default_factory=list)

    def has_problems(self) -> bool:
        return bool(self.schema_issues or self.field_mismatches or self.read_errors)

    def total_problems(self) -> int:
        return (
            len(self.schema_issues) + len(self.field_mismatches) + len(self.read_errors)
        )


def _iter_target_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, schema_name) for each JSON source-of-truth under .quality-system/."""
    qs = root / ".quality-system"
    if not qs.is_dir():
        return

    config = qs / "config.json"
    if config.is_file():
        yield config, "config"

    policy = qs / "policy.json"
    if policy.is_file():
        yield policy, "policy"

    req_dir = qs / "req"
    if req_dir.is_dir():
        for meta in sorted(req_dir.glob("*.meta.json")):
            yield meta, "req-meta"

    contracts_dir = qs / "contracts"
    if contracts_dir.is_dir():
        for contract in sorted(contracts_dir.glob("*/*.json")):
            yield contract, "contract"


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _check_contract_field_mismatch(
    payload: dict[str, Any], path: Path
) -> list[FieldMismatch]:
    """Reject contract.json fields that do not belong to its verification_type.

    The schema itself stays permissive (additionalProperties: true) for
    extensibility; the strict mismatch check lives here at the runner level,
    per requirements doc §F-005.
    """
    if not isinstance(payload, dict):
        return []
    vtype = payload.get("verification_type")
    if not isinstance(vtype, str) or vtype not in _CONTRACT_TYPE_FIELDS:
        # Unknown / missing verification_type is already caught by the schema.
        return []
    allowed = _CONTRACT_BASE_FIELDS | _CONTRACT_TYPE_FIELDS[vtype]
    mismatches: list[FieldMismatch] = []
    for key in payload:
        if key in allowed:
            continue
        # Skip keys that legitimately belong to another verification_type:
        # we still report them; that is the whole point of this check.
        mismatches.append(
            FieldMismatch(file=path, verification_type=vtype, field_name=key)
        )
    return mismatches


def run_validate(root: Path) -> ValidateReport:
    """Validate the .quality-system/ tree rooted at ``root``.

    Returns an aggregated ``ValidateReport``. The caller decides what exit
    code or output to produce.
    """
    report = ValidateReport()
    for path, schema_name in _iter_target_files(root):
        report.files_checked.append((path, schema_name))
        try:
            payload = _load_json(path)
        except OSError as exc:
            report.read_errors.append((path, f"read error: {exc}"))
            continue
        except json.JSONDecodeError as exc:
            report.read_errors.append((path, f"invalid JSON: {exc}"))
            continue

        for issue in validate(payload, schema_name):
            report.schema_issues.append(
                FileIssue(file=path, schema_name=schema_name, issue=issue)
            )

        if schema_name == "contract":
            report.field_mismatches.extend(
                _check_contract_field_mismatch(payload, path)
            )

    return report
