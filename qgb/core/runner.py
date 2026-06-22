"""Execute adopted stages and produce per-stage results.

Verification types this module dispatches:

* ``file_exists``       - the file at ``contract.target`` exists as a regular file.
* ``substring_match``   - the file at ``contract.target`` contains every entry of
                          ``contract.must_contain`` (UTF-8 text).
* ``command``           - delegated to :mod:`qgb.core.command` (carved out
                          in Phase 3 Step 3.1a so process tree kill, output
                          cap and ``.bat`` argument escaping can be layered
                          there without bloating this dispatcher).
* ``json_schema``       - inline below, validates ``contract.target`` against
                          ``contract.schema`` (Phase 1 + Phase 2 Step 2.1).

``manual_check`` is rejected by preflight before the runner is invoked, so
this module never has to handle it.

Dependency handling:

* Stages are executed in the order REQ meta declared them.
* If any of a stage's ``depends_on`` predecessors failed, the stage is
  recorded as ``failed`` with a brief log explaining the skip. This keeps
  the gate schema's "at least one stage failed" invariant trivially true
  while still telling humans which stage was the original cause.
* A ``waived`` stage short-circuits before any other branch — Step 7 D —
  and is treated as judgement-excluded by :mod:`qgb.core.decision`.

The runner does *not* write files. It only produces in-memory results;
:mod:`qgb.core.evidence` is what serialises them to gate.json / log files.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import jsonschema
import jsonschema.exceptions

from qgb.core.loader import LoaderError, resolve_project_relative
from qgb.core.preflight import AdoptedStage

StageOutcome = Literal["passed", "failed", "waived"]


@dataclass(frozen=True)
class StageResult:
    """In-memory outcome of running a single adopted stage."""

    stage_id: str
    name: str
    verification_type: str
    contract_ref: str
    result: StageOutcome
    exit_code: int | None
    log_text: str


# ---------------------------------------------------------------------------


def run_stages(
    project_root: Path, adopted: list[AdoptedStage]
) -> list[StageResult]:
    """Execute every adopted stage, respecting depends_on for skip-on-failure."""
    results_by_id: dict[str, StageResult] = {}
    out: list[StageResult] = []

    for stage in adopted:
        # Step 7 D: waived stages short-circuit before any other branch.
        # They are not executed, not subject to depends_on, and produce
        # a ``result=waived`` entry. The decision layer treats waived
        # stages as judgement-excluded, and the evidence layer adds a
        # ``KNOWLEDGE-WAIVER-<REQ>-<stage>`` basis row.
        if stage.waived:
            result = StageResult(
                stage_id=stage.stage_id,
                name=stage.name,
                verification_type=stage.verification_type,
                contract_ref=stage.contract_ref,
                result="waived",
                exit_code=None,
                log_text=(
                    f"stage_id: {stage.stage_id}\n"
                    f"name: {stage.name}\n"
                    f"verification_type: {stage.verification_type}\n"
                    f"contract_ref: {stage.contract_ref}\n\n"
                    f"waived: stage was waived by REQ meta.\n"
                    f"waiver_reason: {stage.waiver_reason}\n"
                    f"result: waived\n"
                ),
            )
            results_by_id[stage.stage_id] = result
            out.append(result)
            continue

        # If any predecessor failed, mark this stage failed without running.
        # A waived predecessor is treated as not-failed (the waiver explicitly
        # accepted whatever its outcome would have been).
        failed_dep = next(
            (
                dep
                for dep in stage.depends_on
                if dep in results_by_id and results_by_id[dep].result == "failed"
            ),
            None,
        )
        if failed_dep is not None:
            result = StageResult(
                stage_id=stage.stage_id,
                name=stage.name,
                verification_type=stage.verification_type,
                contract_ref=stage.contract_ref,
                result="failed",
                exit_code=None,
                log_text=(
                    f"stage_id: {stage.stage_id}\n"
                    f"name: {stage.name}\n"
                    f"verification_type: {stage.verification_type}\n"
                    f"contract_ref: {stage.contract_ref}\n\n"
                    f"skipped: predecessor stage {failed_dep!r} failed; "
                    f"this stage is recorded as failed without running.\n"
                    f"result: failed\n"
                ),
            )
        else:
            result = _execute_one(project_root, stage)

        results_by_id[stage.stage_id] = result
        out.append(result)

    return out


# ---------------------------------------------------------------------------


def _execute_one(project_root: Path, stage: AdoptedStage) -> StageResult:
    if stage.verification_type == "file_exists":
        return _run_file_exists(project_root, stage)
    if stage.verification_type == "substring_match":
        return _run_substring_match(project_root, stage)
    if stage.verification_type == "command":
        # Phase 3 Step 3.1a: command-stage execution lives in
        # qgb.core.command. Import lazily to avoid an import-time
        # cycle (command.py uses StageResult from this module).
        from qgb.core.command import run_command

        return run_command(project_root, stage)
    if stage.verification_type == "json_schema":
        return _run_json_schema(project_root, stage)
    # Preflight should have caught unsupported types; this is a defensive guard.
    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result="failed",
        exit_code=None,
        log_text=(
            f"stage_id: {stage.stage_id}\n"
            f"verification_type: {stage.verification_type}\n"
            f"error: this verification_type is not runnable in Phase 1\n"
            f"result: failed\n"
        ),
    )


def _run_file_exists(project_root: Path, stage: AdoptedStage) -> StageResult:
    target = stage.contract.get("target")
    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: file_exists",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        "",
        f"check: {target} exists as a regular file",
    ]

    if not isinstance(target, str) or not target:
        log_lines.append("result: failed (contract.target is missing or empty)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        full = resolve_project_relative(project_root, target, "contract.target")
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    is_regular_file = full.is_file()
    log_lines.append(
        f"resolved: {full}"
    )
    if is_regular_file:
        log_lines.append("result: passed")
        outcome: StageOutcome = "passed"
    else:
        if full.exists():
            log_lines.append(
                "result: failed (path exists but is not a regular file)"
            )
        else:
            log_lines.append("result: failed (file does not exist)")
        outcome = "failed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=None,
        log_text="\n".join(log_lines) + "\n",
    )


def _run_substring_match(project_root: Path, stage: AdoptedStage) -> StageResult:
    target = stage.contract.get("target")
    must_contain = stage.contract.get("must_contain")
    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: substring_match",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        f"must_contain: {must_contain}",
        "",
        "check: every entry of must_contain[] occurs in target file",
    ]

    if (
        not isinstance(target, str)
        or not target
        or not isinstance(must_contain, list)
        or not must_contain
    ):
        log_lines.append(
            "result: failed (contract.target or contract.must_contain is malformed)"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        full = resolve_project_relative(project_root, target, "contract.target")
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    if not full.is_file():
        log_lines.append(f"resolved: {full}")
        log_lines.append("result: failed (target file does not exist)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        text = full.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        log_lines.append(
            f"result: failed (target is not valid UTF-8: {exc})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    missing: list[str] = []
    for keyword in must_contain:
        if not isinstance(keyword, str):
            missing.append(repr(keyword))
            continue
        if keyword in text:
            # Step 6a Commit 3 (Codex L2) + 補修 1 次 (Codex m1):
            # str.index returns a Python code point index (Python's str
            # is a sequence of Unicode code points; the UTF-16 vs UCS-4
            # distinction is an internal storage detail not exposed by
            # str indexing). The previous "byte offset" label was wrong
            # for non-ASCII keywords; "char offset" matches what we
            # actually compute. A real UTF-8 byte offset would require
            # encoding the prefix; that is a Phase 2+ enrichment.
            offset = text.index(keyword)
            log_lines.append(f"- {keyword!r}: found at char offset {offset}")
        else:
            log_lines.append(f"- {keyword!r}: not found")
            missing.append(keyword)

    if missing:
        log_lines.append(f"result: failed (missing keywords: {missing})")
        outcome: StageOutcome = "failed"
    else:
        log_lines.append("result: passed")
        outcome = "passed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=None,
        log_text="\n".join(log_lines) + "\n",
    )


# ---- command verification_type (Step 7 項目 B) --------------------------
#
# Phase 3 Step 3.1a (2026-06-22): the entire command-stage runner —
# argv validation, working_dir R1 resolution, subprocess invocation,
# stdout/stderr cap, timeout handling — was carved out to
# :mod:`qgb.core.command` so subsequent sub-steps (Popen + process tree
# kill in 3.1b, 16 MiB execution cap in 3.1c, .bat/.cmd argument
# escaping in 3.1d) can layer on top of a single-responsibility module
# (P9). The dispatcher above (``_execute_one``) imports
# ``qgb.core.command.run_command`` lazily to avoid an import cycle with
# ``StageResult`` defined in this module.


# ---- json_schema verification_type (Step 8 項目 1) ----------------------

# Codex 計画レビュー (Phase 1 / Phase 2 Step 2.1): Phase 1 では JSON Schema
# の $ref を意図的にサポートしない。Phase 2 Step 2.1 で
# ``contract.allow_internal_ref=true`` のときだけ「self-ref (RFC 6901 JSON
# Pointer) のみ」を allowlist として許容する。それ以外 (anchor / 絶対 URI /
# 相対 URI / network) は引き続き failed として扱う。これにより R1 ガード
# (target / schema 両方が project root 配下に閉じ込められる) を
# ``jsonschema`` ライブラリの ref 解決経路と切り離せる。


def _collect_dollar_refs(node: object) -> list[str]:
    """Walk a parsed JSON Schema and return all ``$ref`` *string* values.

    Phase 2 Step 2.1 (Codex 指摘 1/2 反映):

    * Returns a list (not a bool) so the runner can build a precise log
      line listing every disallowed ref it found, not just "some ref".
    * Order is depth-first / insertion-order; callers should sort if they
      want a stable output ordering.
    * Non-string ``$ref`` values are still collected (as their ``repr``)
      so a malformed ``$ref`` cannot silently bypass the allowlist check.
      A real JSON Schema with a non-string ``$ref`` is invalid, but the
      runner must not crash on it.
    """
    found: list[str] = []

    def _walk(n: object) -> None:
        if isinstance(n, dict):
            if "$ref" in n:
                ref_val = n["$ref"]
                if isinstance(ref_val, str):
                    found.append(ref_val)
                else:
                    found.append(repr(ref_val))
            for v in n.values():
                _walk(v)
        elif isinstance(n, list):
            for v in n:
                _walk(v)

    _walk(node)
    return found


def _collect_format_names(node: object) -> set[str]:
    """Walk a parsed JSON Schema and return the set of ``format`` string values.

    Phase 2 Step 2.1 (Codex 指摘 3): used to compute the
    ``formats_seen`` / ``formats_checked`` / ``formats_ignored`` evidence
    lines. Non-string format values are skipped — a malformed ``format``
    value is invalid schema, ``check_schema`` will surface that earlier.
    """
    found: set[str] = set()

    def _walk(n: object) -> None:
        if isinstance(n, dict):
            fmt = n.get("format")
            if isinstance(fmt, str):
                found.add(fmt)
            for v in n.values():
                _walk(v)
        elif isinstance(n, list):
            for v in n:
                _walk(v)

    _walk(node)
    return found


def _is_internal_pointer_ref(ref: str) -> bool:
    """True iff ``ref`` is a self-document JSON Pointer (RFC 6901) ref.

    Codex Step 2.1 指摘 1 (許可条件の厳密化):

    * ``"#"`` (root pointer) — allowed
    * ``"#/..."`` (proper JSON Pointer starting with ``#/``) — allowed
    * Everything else (``#anchor``, ``""``, absolute URI, ``file://``,
      ``http://``, ``../foo.json#/y``, ``schema.json#/x``) — rejected

    Crucially this does NOT call ``startswith("#")``; ``#foo`` is the
    ``$anchor`` form and triggers identifier-based resolution rather than
    pure pointer traversal. Phase 2 Step 2.1 only allowlists pointer-only
    refs whose resolution is purely lexical inside the same document.
    """
    return ref == "#" or ref.startswith("#/")


def _run_json_schema(project_root: Path, stage: AdoptedStage) -> StageResult:
    """Execute a ``verification_type=json_schema`` stage.

    Phase 1 design (Codex 計画レビュー 2026-05-31) + Phase 2 Step 2.1
    extensions (Codex 計画レビュー 2026-06-04):

    * ``target`` (workspace-relative) is parsed as JSON.
    * ``schema`` (workspace-relative) is parsed as JSON and
      validated as a JSON Schema via
      ``jsonschema.validators.validator_for(schema).check_schema()``.
    * Both ``target`` and ``schema`` paths go through
      :func:`qgb.core.loader.resolve_project_relative` — escapes
      (absolute, ``..``-relative, symlinks pointing outside) are
      rejected as failed.
    * **``$ref`` handling (Phase 2 Step 2.1, Codex 指摘 1/2):**

      Order is **spec-locked**: every ``$ref`` value is collected via
      :func:`_collect_dollar_refs` BEFORE the validator is constructed.
      If ``contract.allow_internal_ref`` is ``true`` (default ``false``),
      pointer-only refs (``"#"`` or ``"#/..."``) are accepted; anchor
      refs (``#name``), absolute / file / http(s) / relative URIs are
      still rejected as failed. If ``allow_internal_ref`` is absent or
      ``false`` (Phase 1 behaviour), **any** ``$ref`` is rejected.
    * **``format`` handling (Phase 2 Step 2.1, Codex 指摘 3):**

      ``format`` assertions are opt-in via ``contract.enforce_format``
      (default ``false``). When ``true``, the validator is wired with
      :func:`qgb.core.schema.build_qgb_format_checker` so the same
      format set used for qgb's own spec files (``date``,
      ``date-time``, ``email``, ``ipv4``, ``ipv6``, ``regex``, ``uuid``,
      ``idn-email``) is applied to the user's target. The runner emits
      ``formats_seen`` / ``formats_checked`` / ``formats_ignored`` log
      lines so a typo'd format in the user's schema is visible in the
      evidence even though ``jsonschema`` silently ignores unknown
      formats.
    * Validation failures are reported as failed with the violation
      path + message in ``log_text``.

    **Out-of-scope (Phase 3 or later):**

    * Streaming validation / memory caps for large JSON inputs.
    * Remote / network schema fetch (always unsupported in qgb).
    * External-file ``$ref`` (``../x.json#/y`` / ``schema.json#/x``):
      reopens path-escape, base-URI, and symlink concerns; deferred.
    """
    import json as _json

    from qgb.core.schema import build_qgb_format_checker, qgb_format_names

    contract = stage.contract
    target = contract.get("target")
    schema_path_str = contract.get("schema")
    # Phase 2 Step 2.1: opt-in flags (default false → Phase 1 behaviour).
    enforce_format = bool(contract.get("enforce_format", False))
    allow_internal_ref = bool(contract.get("allow_internal_ref", False))

    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: json_schema",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        f"schema: {schema_path_str}",
        f"enforce_format: {str(enforce_format).lower()}",
        f"allow_internal_ref: {str(allow_internal_ref).lower()}",
    ]

    if (
        not isinstance(target, str)
        or not target
        or not isinstance(schema_path_str, str)
        or not schema_path_str
    ):
        log_lines.append(
            "result: failed (contract.target or contract.schema is missing "
            "or not a string)"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    # Resolve target under project root (R1).
    try:
        target_full = resolve_project_relative(
            project_root, target, "contract.target"
        )
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    # Resolve schema under project root (R1).
    try:
        schema_full = resolve_project_relative(
            project_root, schema_path_str, "contract.schema"
        )
    except LoaderError as exc:
        log_lines.append(f"result: failed ({exc.message})")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    # Step 8 統合レビュー W1: surface the resolved target/schema paths
    # so the audit log matches the other runners' convention
    # (_run_file_exists / _run_substring_match / qgb.core.command.run_command
    # all log ``resolved: ...`` after R1 path resolution succeeds).
    log_lines.append(f"resolved target: {target_full}")
    log_lines.append(f"resolved schema: {schema_full}")

    if not target_full.is_file():
        log_lines.append(
            f"result: failed (target file does not exist: {target_full})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    if not schema_full.is_file():
        log_lines.append(
            f"result: failed (schema file does not exist: {schema_full})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        target_data = _json.loads(target_full.read_text(encoding="utf-8-sig"))
    except (_json.JSONDecodeError, UnicodeDecodeError) as exc:
        log_lines.append(
            f"result: failed (target is not valid JSON: {exc})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    try:
        schema_data = _json.loads(schema_full.read_text(encoding="utf-8-sig"))
    except (_json.JSONDecodeError, UnicodeDecodeError) as exc:
        log_lines.append(
            f"result: failed (schema is not valid JSON: {exc})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    # Phase 2 Step 2.1: collect every $ref string up front (Codex 指摘 2:
    # spec-locked order — refs are screened BEFORE validator construction
    # so ``jsonschema`` is never asked to resolve anything).
    refs = _collect_dollar_refs(schema_data)
    if refs:
        if allow_internal_ref:
            # Internal-only allowlist: '#' or '#/...'. Anchor refs (#name),
            # absolute / file / http(s) / relative URIs are still rejected.
            disallowed = sorted(
                {r for r in refs if not _is_internal_pointer_ref(r)}
            )
            if disallowed:
                log_lines.append(
                    "result: failed (non-internal $ref rejected; "
                    "allow_internal_ref accepts '#' or '#/...' only)"
                )
                log_lines.append(
                    f"disallowed_refs ({len(disallowed)}):"
                )
                for r in disallowed:
                    log_lines.append(f"  - {r}")
                return StageResult(
                    stage_id=stage.stage_id,
                    name=stage.name,
                    verification_type=stage.verification_type,
                    contract_ref=stage.contract_ref,
                    result="failed",
                    exit_code=None,
                    log_text="\n".join(log_lines) + "\n",
                )
            # All refs are internal pointer refs → fall through to validator.
            # Step 2.1 補修 A1: count と列挙を unique 基準で揃える。生 list
            # `refs` は同じ ref が複数箇所に出現すれば重複を含むので、
            # `sorted(set(refs))` で dedup したものを正本とし、count もその
            # 長さで合わせる (Codex 横断レビュー指摘)。
            unique_refs = sorted(set(refs))
            log_lines.append(
                f"internal_refs_accepted ({len(unique_refs)}): "
                + ", ".join(unique_refs)
            )
        else:
            # Phase 1 behaviour (allow_internal_ref absent or false): reject
            # every $ref. The log lists what was found so authors can decide
            # whether to opt in to allow_internal_ref or rewrite the schema.
            # Step 2.1 補修 A1: count と列挙を unique 基準で揃える。
            unique_refs = sorted(set(refs))
            log_lines.append(
                "result: failed ($ref in schema is rejected; "
                "set contract.allow_internal_ref=true to allow "
                "'#' / '#/...' pointer refs)"
            )
            log_lines.append(f"found_refs ({len(unique_refs)}):")
            for r in unique_refs:
                log_lines.append(f"  - {r}")
            return StageResult(
                stage_id=stage.stage_id,
                name=stage.name,
                verification_type=stage.verification_type,
                contract_ref=stage.contract_ref,
                result="failed",
                exit_code=None,
                log_text="\n".join(log_lines) + "\n",
            )

    # Schema must itself be a valid JSON Schema.
    try:
        validator_cls = jsonschema.validators.validator_for(schema_data)
        validator_cls.check_schema(schema_data)
    except jsonschema.exceptions.SchemaError as exc:
        log_lines.append(
            f"result: failed (schema is not a valid JSON Schema: {exc.message})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    # Phase 2 Step 2.1: format is enforced only when contract.enforce_format
    # is true. Default (false) preserves Phase 1 behaviour. Codex Step 2.1
    # 指摘 3 反映: emit formats_seen / formats_checked / formats_ignored to
    # the log so a typo'd format name in the user's schema is auditable.
    #
    # ``formats_seen`` is the set of format names that actually appear in
    # the user's schema. ``formats_checked`` is the subset qgb's format
    # checker knows about (and will assert when enforce_format=true).
    # ``formats_ignored`` is whatever ``jsonschema`` would silently skip —
    # the diff exposes typos like ``"datetime"`` for ``"date-time"``.
    # Step 2.1 補修 A4: format checker の構築ポリシー (Codex 横断レビュー指摘):
    #
    # * ``qgb_format_names()`` は module import 時に一度だけ計算した
    #   ``_QGB_FORMAT_NAMES`` (frozenset、L120) を返す。「qgb が知っている
    #   format 名の集合」は実行時に変化しないので import-time cache でよい。
    # * ``build_qgb_format_checker()`` は呼ぶたびに新しい ``FormatChecker``
    #   インスタンスを返す。Phase 2 Step 2.1 ではすべての stage 実行で fresh
    #   な checker を構築する設計を採用 (将来 jsonschema 側が checker を
    #   stateful 化したり stage 間で副作用を持ち込むのを防ぐため)。
    # * ``qgb_format_names()`` のキャッシュ集合と、毎回新規構築する checker
    #   の ``checkers.keys()`` は同じ format set を返す (どちらも
    #   ``build_qgb_format_checker()`` の checkers ロジック由来)。
    formats_seen = sorted(_collect_format_names(schema_data))
    if enforce_format:
        known_formats = qgb_format_names()
        formats_checked = sorted(f for f in formats_seen if f in known_formats)
        formats_ignored = sorted(f for f in formats_seen if f not in known_formats)
        log_lines.append(f"formats_seen ({len(formats_seen)}): {formats_seen}")
        log_lines.append(
            f"formats_checked ({len(formats_checked)}): {formats_checked}"
        )
        log_lines.append(
            f"formats_ignored ({len(formats_ignored)}): {formats_ignored}"
        )
        _qgb_format_checker = build_qgb_format_checker()
    else:
        log_lines.append(f"formats_seen ({len(formats_seen)}): {formats_seen}")
        _qgb_format_checker = None

    # Step 8 統合レビュー C1: defensive try/except around validator
    # instantiation and iter_errors. ``check_schema`` above filters out
    # the common malformed-schema case, but the jsonschema library can
    # still raise (unknown draft, library version drift, unexpected
    # custom format etc.). A bare exception here would surface as a
    # traceback in `qgb run`; treating it as a stage failure keeps
    # auditability intact and matches the runner's contract that
    # individual stages never crash the whole gate.
    #
    # Step 8 統合レビュー C2 (再): sort by the **string form** of
    # ``absolute_path``. ``e.absolute_path`` is a deque whose elements
    # can mix ``int`` (array index) and ``str`` (object key); Python 3
    # refuses to compare ``int`` and ``str`` directly, so a raw
    # ``list(e.absolute_path)`` key would raise ``TypeError`` on real
    # schemas that have both array and object levels. Stringifying each
    # element (``str(p) for p in e.absolute_path``) gives a deterministic
    # ordering across runs while staying robust to mixed-type paths.
    try:
        if _qgb_format_checker is not None:
            validator = validator_cls(
                schema_data, format_checker=_qgb_format_checker
            )
        else:
            validator = validator_cls(schema_data)
        errors = sorted(
            validator.iter_errors(target_data),
            key=lambda e: [str(p) for p in e.absolute_path],
        )
    except Exception as exc:  # noqa: BLE001 - any validator error is a stage failure
        log_lines.append(
            f"result: failed (validator raised unexpectedly: "
            f"{type(exc).__name__}: {exc})"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    if not errors:
        log_lines.append("result: passed")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="passed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    log_lines.append(f"validation errors ({len(errors)}):")
    for err in errors:
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        log_lines.append(f"  - {path}: {err.message}")
    log_lines.append("result: failed (schema validation errors)")
    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result="failed",
        exit_code=None,
        log_text="\n".join(log_lines) + "\n",
    )
