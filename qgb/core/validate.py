"""Validate the JSON sources of truth under a project's .quality-system/ tree.

This module is the qgb validate runtime. Beyond the schema-only checks
delegated to ``qgb.core.schema``, it enforces:

* Tree integrity: required files (config.json, policy.json) must exist, every
  REQ meta's ``contract_ref`` must resolve, every policy stage referenced by a
  REQ meta must exist in policy.json, and contract JSONs must live directly
  under ``.quality-system/contracts/<REQ>/``.
* Contract field policy: a contract's ``verification_type`` must not coexist
  with fields owned by *another* known verification_type (e.g. a ``file_exists``
  contract carrying ``command`` is rejected). Unknown forward-compatible fields
  on a contract remain allowed; the contract schema stays
  ``additionalProperties: true`` for extensibility.

Aggregated results land in ``ValidateReport``; the caller decides exit codes
and output format.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from qgb.core.schema import ValidationIssue, validate

# Fields that may appear on every contract regardless of verification_type.
_CONTRACT_BASE_FIELDS: frozenset[str] = frozenset(
    {"schema_version", "req_id", "stage_id", "verification_type"}
)

# verification_type -> fields that ONLY that type may carry. Fields outside
# these sets are treated as forward-compatible extensions and accepted by
# qgb validate (the schema is also permissive).
_CONTRACT_TYPE_FIELDS: dict[str, frozenset[str]] = {
    "command": frozenset({"command", "expected_exit_code", "working_dir", "timeout_seconds"}),
    "file_exists": frozenset({"target"}),
    "substring_match": frozenset({"target", "must_contain"}),
    "json_schema": frozenset({"target", "schema"}),
    "manual_check": frozenset({"description"}),
}

# Union of every type-owned field; used to identify the foreign-typed fields
# that must NOT appear on a contract of a different verification_type.
_ALL_TYPE_FIELDS: frozenset[str] = frozenset().union(*_CONTRACT_TYPE_FIELDS.values())


@dataclass(frozen=True)
class FileIssue:
    """A single JSON Schema violation tied to a concrete file on disk."""

    file: Path
    schema_name: str
    issue: ValidationIssue


@dataclass(frozen=True)
class FieldMismatch:
    """A contract.json carries a field owned by a different verification_type.

    Unknown / forward-compatible fields are NOT reported here; only fields that
    belong to another known verification_type's set are flagged.
    """

    file: Path
    verification_type: str
    field_name: str
    owning_verification_type: str

    def as_message(self) -> str:
        return (
            f"{self.file}: field {self.field_name!r} belongs to "
            f"verification_type={self.owning_verification_type!r}, "
            f"but this contract declares verification_type={self.verification_type!r}"
        )


@dataclass(frozen=True)
class ReadError:
    """A required file could not be read or parsed."""

    file: Path
    message: str


@dataclass(frozen=True)
class IntegrityIssue:
    """A structural problem in the .quality-system/ tree.

    ``kind`` is one of:

    * ``missing_file`` — a required file is absent (``file`` is the expected path)
    * ``misplaced_contract`` — a contract JSON lives outside the expected
      ``contracts/<REQ>/<stage>.json`` layout
    * ``dangling_contract_ref`` — a REQ meta points at a contract that does not exist
    * ``unknown_stage_id`` — a REQ meta references a stage_id not defined in policy.json
    """

    kind: str
    file: Path
    message: str


@dataclass
class ValidateReport:
    """Aggregated result of ``qgb validate``."""

    schema_issues: list[FileIssue] = field(default_factory=list)
    field_mismatches: list[FieldMismatch] = field(default_factory=list)
    read_errors: list[ReadError] = field(default_factory=list)
    integrity_issues: list[IntegrityIssue] = field(default_factory=list)
    files_checked: list[tuple[Path, str]] = field(default_factory=list)

    def has_problems(self) -> bool:
        return bool(
            self.schema_issues
            or self.field_mismatches
            or self.read_errors
            or self.integrity_issues
        )

    def total_problems(self) -> int:
        return (
            len(self.schema_issues)
            + len(self.field_mismatches)
            + len(self.read_errors)
            + len(self.integrity_issues)
        )


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------


def _iter_target_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, schema_name) for each JSON source of truth.

    Order is stable: config.json, policy.json, REQ metas sorted by name, then
    contracts sorted by REQ then stage filename.
    """
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
        # Stages live directly under contracts/<REQ>/<stage>.json. Anything
        # deeper is reported as a misplaced-contract integrity issue (handled
        # in _check_integrity), so we only enumerate the canonical layer here.
        for req_subdir in sorted(p for p in contracts_dir.iterdir() if p.is_dir()):
            for contract in sorted(req_subdir.glob("*.json")):
                yield contract, "contract"


def _iter_misplaced_contracts(root: Path) -> Iterator[Path]:
    """Yield contract JSON files that do not sit at contracts/<REQ>/<stage>.json."""
    contracts_dir = root / ".quality-system" / "contracts"
    if not contracts_dir.is_dir():
        return
    for path in contracts_dir.rglob("*.json"):
        rel = path.relative_to(contracts_dir)
        # Canonical layout: <REQ>/<stage>.json -> exactly two parts.
        if len(rel.parts) != 2:
            yield path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _check_contract_field_mismatch(
    payload: dict[str, Any], path: Path
) -> list[FieldMismatch]:
    """Flag contract fields owned by another known verification_type.

    Unknown / forward-compatible fields (not in any known type's set) are
    accepted; only fields whose ownership belongs to a *different* known
    verification_type are reported.
    """
    if not isinstance(payload, dict):
        return []
    vtype = payload.get("verification_type")
    if not isinstance(vtype, str) or vtype not in _CONTRACT_TYPE_FIELDS:
        # Unknown / missing verification_type is a schema concern.
        return []

    allowed = _CONTRACT_BASE_FIELDS | _CONTRACT_TYPE_FIELDS[vtype]
    mismatches: list[FieldMismatch] = []
    for key in payload:
        if key in allowed:
            continue
        # Only flag fields that are owned by another known type. Forward-
        # compatible extensions (not in _ALL_TYPE_FIELDS) are permitted.
        if key not in _ALL_TYPE_FIELDS:
            continue
        owner = next(
            (t for t, fields in _CONTRACT_TYPE_FIELDS.items() if key in fields),
            "",
        )
        mismatches.append(
            FieldMismatch(
                file=path,
                verification_type=vtype,
                field_name=key,
                owning_verification_type=owner,
            )
        )
    return mismatches


def _check_integrity(
    root: Path,
    payloads: dict[Path, Any],
) -> list[IntegrityIssue]:
    """Detect structural problems independent of per-file schema checks.

    ``payloads`` is the in-memory cache of successfully parsed JSON files
    keyed by absolute path; we use it to avoid re-reading and to skip files
    that failed earlier (already reported as ReadError).
    """
    qs = root / ".quality-system"
    issues: list[IntegrityIssue] = []

    # 1. Required files.
    config = qs / "config.json"
    policy = qs / "policy.json"
    if not config.is_file():
        issues.append(
            IntegrityIssue(
                kind="missing_file",
                file=config,
                message="required file missing: .quality-system/config.json",
            )
        )
    if not policy.is_file():
        issues.append(
            IntegrityIssue(
                kind="missing_file",
                file=policy,
                message="required file missing: .quality-system/policy.json",
            )
        )

    # 2. Misplaced contracts.
    for path in _iter_misplaced_contracts(root):
        issues.append(
            IntegrityIssue(
                kind="misplaced_contract",
                file=path,
                message=(
                    f"contract JSON not at contracts/<REQ>/<stage>.json: "
                    f"{path.relative_to(qs / 'contracts')!s}"
                ),
            )
        )

    # 3. REQ meta references.
    known_stage_ids: set[str] = set()
    policy_payload = payloads.get(policy)
    if isinstance(policy_payload, dict):
        for stage in policy_payload.get("stages", []) or []:
            if isinstance(stage, dict):
                sid = stage.get("id")
                if isinstance(sid, str):
                    known_stage_ids.add(sid)

    req_dir = qs / "req"
    if req_dir.is_dir():
        for meta_path in sorted(req_dir.glob("*.meta.json")):
            meta_payload = payloads.get(meta_path)
            if not isinstance(meta_payload, dict):
                continue
            for stage_entry in meta_payload.get("stages", []) or []:
                if not isinstance(stage_entry, dict):
                    continue
                stage_id = stage_entry.get("stage_id")
                contract_ref = stage_entry.get("contract_ref")

                if (
                    isinstance(stage_id, str)
                    and known_stage_ids
                    and stage_id not in known_stage_ids
                ):
                    issues.append(
                        IntegrityIssue(
                            kind="unknown_stage_id",
                            file=meta_path,
                            message=(
                                f"REQ meta references stage_id {stage_id!r} "
                                f"which is not defined in policy.json"
                            ),
                        )
                    )

                if isinstance(contract_ref, str):
                    # contract_ref is workspace-relative to the project root.
                    target = (root / contract_ref).resolve()
                    if not target.is_file():
                        issues.append(
                            IntegrityIssue(
                                kind="dangling_contract_ref",
                                file=meta_path,
                                message=(
                                    f"contract_ref does not resolve to a file: "
                                    f"{contract_ref}"
                                ),
                            )
                        )

    return issues


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_validate(root: Path) -> ValidateReport:
    """Validate the .quality-system/ tree rooted at ``root``.

    Returns an aggregated ``ValidateReport``. The caller decides what exit
    code or output to produce.
    """
    report = ValidateReport()
    payloads: dict[Path, Any] = {}

    for path, schema_name in _iter_target_files(root):
        report.files_checked.append((path, schema_name))
        try:
            payload = _load_json(path)
        except OSError as exc:
            report.read_errors.append(ReadError(file=path, message=f"read error: {exc}"))
            continue
        except json.JSONDecodeError as exc:
            report.read_errors.append(ReadError(file=path, message=f"invalid JSON: {exc}"))
            continue

        payloads[path] = payload

        for issue in validate(payload, schema_name):
            report.schema_issues.append(
                FileIssue(file=path, schema_name=schema_name, issue=issue)
            )

        if schema_name == "contract":
            report.field_mismatches.extend(
                _check_contract_field_mismatch(payload, path)
            )

    # Integrity checks need the full payload cache, so they run last.
    if (root / ".quality-system").is_dir():
        report.integrity_issues.extend(_check_integrity(root, payloads))

    return report
