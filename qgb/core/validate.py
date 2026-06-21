"""Validate the JSON sources of truth under a project's .quality-system/ tree.

Scope (matches requirements doc §F-009, §6.3.2, §12 acceptance items 6 & 7):

* ``qgb validate`` checks that **each existing JSON file** under
  ``.quality-system/`` parses as JSON and conforms to its bundled schema.
* It also enforces the §F-005 rule that a contract's ``verification_type``
  must not coexist with fields owned by another known verification_type.

Out of scope for ``qgb validate`` (delegated elsewhere):

* Missing top-level files (``config.json`` / ``policy.json``): reported by
  ``qgb validate-policy`` (Step 6) and by the ``qgb run`` preflight (Step 5).
* Cross-file integrity (``contract_ref`` resolution, ``stage_id`` exists in
  policy, DAG of ``depends_on``, etc.): reported by ``qgb validate-policy``.
* Tree-layout integrity (e.g. misplaced contracts): same; ``qgb validate-policy``.
* READY/NOT_READY combined judgement for gate execution: ``qgb run`` preflight.

This separation keeps single-responsibility on a per-command basis (philosophy
P9). ``qgb validate`` answers “does each spec file conform to qgb's machine
contract?”; ``qgb validate-policy`` answers “does the assembled quality system
satisfy the design rules?”.
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
    "json_schema": frozenset(
        {"target", "schema", "enforce_format", "allow_internal_ref"}
    ),
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
    """A spec file could not be read or parsed as JSON."""

    file: Path
    message: str


@dataclass
class ValidateReport:
    """Aggregated result of ``qgb validate``."""

    schema_issues: list[FileIssue] = field(default_factory=list)
    field_mismatches: list[FieldMismatch] = field(default_factory=list)
    read_errors: list[ReadError] = field(default_factory=list)
    files_checked: list[tuple[Path, str]] = field(default_factory=list)

    def has_problems(self) -> bool:
        return bool(self.schema_issues or self.field_mismatches or self.read_errors)

    def total_problems(self) -> int:
        return (
            len(self.schema_issues)
            + len(self.field_mismatches)
            + len(self.read_errors)
        )


# ---------------------------------------------------------------------------
# File enumeration
# ---------------------------------------------------------------------------


def _iter_target_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, schema_name) for each spec JSON file under .quality-system/.

    Order is stable: config.json, policy.json, REQ metas sorted by name, then
    contracts directly under contracts/<REQ>/. Files outside the canonical
    layout (e.g. nested under contracts/<REQ>/<sub>/) are not enumerated;
    detecting such tree-shape problems is the responsibility of
    ``qgb validate-policy`` (Step 6).

    Step 9 (受け入れ条件 17/18): ``knowledge/knowledge.jsonl`` is handled
    separately by :func:`_iter_jsonl_files` because each line is its own
    JSON document with the ``knowledge`` schema (JSONL, not single JSON).
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

    # Phase 3 Step 3.0: optional project-context.json (target project's
    # self-declaration). Validate the schema when present; absence is fine
    # (existing projects keep working without one).
    project_context = qs / "project-context.json"
    if project_context.is_file():
        yield project_context, "project-context"

    req_dir = qs / "req"
    if req_dir.is_dir():
        for meta in sorted(req_dir.glob("*.meta.json")):
            yield meta, "req-meta"

    contracts_dir = qs / "contracts"
    if contracts_dir.is_dir():
        for req_subdir in sorted(p for p in contracts_dir.iterdir() if p.is_dir()):
            for contract in sorted(req_subdir.glob("*.json")):
                yield contract, "contract"


def _iter_jsonl_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield (path, schema_name) for JSONL spec files (Step 9).

    Each yielded path contains one JSON object per non-blank line, all
    validated under the same ``schema_name``. Currently only
    ``knowledge.jsonl`` is in scope.
    """
    qs = root / ".quality-system"
    if not qs.is_dir():
        return
    kjsonl = qs / "knowledge" / "knowledge.jsonl"
    if kjsonl.is_file():
        yield kjsonl, "knowledge"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def _check_contract_field_mismatch(
    payload: dict[str, Any], path: Path
) -> list[FieldMismatch]:
    """Flag contract fields owned by another known verification_type.

    Unknown / forward-compatible fields (not in any known type's set) are
    accepted; only fields whose ownership belongs to a *different* known
    verification_type are reported (see requirements doc §F-005).
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


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run_validate(root: Path) -> ValidateReport:
    """Validate the .quality-system/ tree rooted at ``root``.

    See the module docstring for the precise scope. The caller decides what
    exit code or output format to produce.

    Step 9: in addition to the single-JSON spec files, ``knowledge.jsonl``
    is validated line-by-line against the ``knowledge`` schema (受け入れ
    条件 17/18).
    """
    report = ValidateReport()

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

        for issue in validate(payload, schema_name):
            report.schema_issues.append(
                FileIssue(file=path, schema_name=schema_name, issue=issue)
            )

        if schema_name == "contract":
            report.field_mismatches.extend(
                _check_contract_field_mismatch(payload, path)
            )

    for path, schema_name in _iter_jsonl_files(root):
        report.files_checked.append((path, schema_name))
        try:
            # Step 2.4 補修 A2: decode with errors="replace" instead of
            # strict. A crash mid-append can cut a multi-byte UTF-8
            # sequence (knowledge entries carry Japanese reasons), and a
            # strict read_text would raise UnicodeDecodeError before the
            # line logic below ever runs — crashing every caller
            # (run/check preflight) instead of hitting the partial-tail
            # skip. Byte corruption on a terminated line is re-detected
            # loudly via the U+FFFD check in the line loop (補修 B1) so
            # tolerance stays scoped to the torn tail.
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            report.read_errors.append(
                ReadError(file=path, message=f"read error: {exc}")
            )
            continue
        # Step 9 の knowledge.jsonl validation は Step 7 で確立した
        # append-only / partial-tail-tolerant な運用と矛盾しないように、
        # 「最後の行が改行で終わっていない場合」のみを partial として
        # skip する。それ以外の中間行で JSON parse が失敗したら、
        # ファイルが正しく壊れていることを示すので read_error として
        # 報告する。
        #
        # NF-004 (Windows PowerShell first-class): ``splitlines()`` は
        # LF / CRLF / CR を透過的に処理するので、Windows 書き込みの
        # ``\r\n`` 終端ファイルも ``endswith("\n")`` で正常終了として
        # 認識される (``\r\n`` も末尾に ``\n`` を含むため)。BOM 付き
        # UTF-8 は対象外 — Phase 1 では BOM なし UTF-8 を要求する
        # (phase1-manual.md §19 troubleshooting 参照)。
        lines = text.splitlines()
        ends_with_newline = text.endswith("\n") or text == ""
        for line_no, raw in enumerate(lines, start=1):
            line = raw.strip()
            if not line:
                continue
            is_last_line = line_no == len(lines)
            # Step 2.4 補修 B1 (Codex/段 1 backward-compat 指摘): a byte
            # corrupted INSIDE a JSON string value (Japanese reasons are
            # the common content) decodes to U+FFFD and would otherwise
            # parse as valid JSON — silently passing a file the old
            # strict decoder loudly crashed on. Treat any replacement
            # character on a *terminated* line as corruption; the torn
            # tail (last line, no trailing newline) keeps its Step 7
            # silent-skip semantics.
            if "�" in line:
                if is_last_line and not ends_with_newline:
                    continue
                report.read_errors.append(
                    ReadError(
                        file=path,
                        message=(
                            f"line {line_no} contains U+FFFD replacement "
                            f"characters: byte-level corruption in a "
                            f"terminated line"
                        ),
                    )
                )
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError as exc:
                if is_last_line and not ends_with_newline:
                    # Step 7 が許容する partial tail。silent skip。
                    continue
                report.read_errors.append(
                    ReadError(
                        file=path,
                        message=f"invalid JSON on line {line_no}: {exc}",
                    )
                )
                continue
            for issue in validate(entry, schema_name):
                report.schema_issues.append(
                    FileIssue(
                        file=path,
                        schema_name=schema_name,
                        issue=issue,
                    )
                )

    return report
