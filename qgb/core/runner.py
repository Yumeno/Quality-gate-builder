"""Execute adopted stages and produce per-stage results.

Phase 1 verification types this module knows how to run:

* ``file_exists``       - the file at ``contract.target`` exists as a regular file.
* ``substring_match``   - the file at ``contract.target`` contains every entry of
                          ``contract.must_contain`` (UTF-8 text).

``command``, ``json_schema`` and ``manual_check`` are deferred to Step 7 / 8;
preflight rejects them before the runner is invoked, so the runner does not
need to handle them.

Dependency handling (Phase 1):

* Stages are executed in the order REQ meta declared them.
* If any of a stage's ``depends_on`` predecessors failed, the stage is
  recorded as ``failed`` with a brief log explaining the skip. This keeps
  the gate schema's "at least one stage failed" invariant trivially true
  while still telling humans which stage was the original cause.

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
        return _run_command(project_root, stage)
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
        text = full.read_text(encoding="utf-8")
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

# Per-stream output cap (Codex 計画レビュー: 64 KiB, tail-prioritised).
# Failure tracebacks tend to appear at the tail of stderr, so we keep the
# last bytes of each stream rather than the first.
_COMMAND_STREAM_CAP_BYTES = 64 * 1024
_COMMAND_DEFAULT_TIMEOUT_SECONDS = 60


def _tail_truncate(text: str, cap: int) -> tuple[str, bool]:
    """Truncate ``text`` to its trailing ``cap`` bytes (utf-8 safe enough).

    Returns (kept_text, was_truncated). We measure in bytes after utf-8
    encoding so multi-byte sequences (e.g. Japanese in stderr) cannot
    silently overshoot the cap. The boundary is then trimmed at a valid
    char by re-decoding with errors="ignore".
    """
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= cap:
        return text, False
    tail_bytes = encoded[-cap:]
    return tail_bytes.decode("utf-8", errors="ignore"), True


def _run_command(project_root: Path, stage: AdoptedStage) -> StageResult:
    """Execute a ``verification_type=command`` stage.

    Phase 1 design (Codex 計画レビュー 2026-05-31):

    * ``subprocess.run(..., shell=False, ...)`` — argv array only, no
      shell interpolation. Shell metacharacters are passed through
      ``argv[0]`` literally, so a command like ``"a ; b"`` is searched
      for as a single filename and fails with ENOENT.
    * Inherited environment (``os.environ.copy()``). Phase 2 may
      restrict this; for now the alternative (minimal env) breaks too
      many real-world commands.
    * ``stdin=DEVNULL`` — interactive commands are out of scope.
    * stdout / stderr captured to memory; each capped at 64 KiB,
      tail-prioritised (tracebacks live at the end). Truncation is
      surfaced in the log as ``stdout: <truncated, last N bytes shown>``.
    * ``cwd`` defaults to ``project_root`` but a contract may specify
      a ``working_dir`` (project-root-relative). Escapes are rejected
      by ``resolve_project_relative`` (Step 5 R1).
    * Timeout from ``timeout_seconds`` (default 60). A timeout is
      reported as failed; ``subprocess.TimeoutExpired`` is caught and
      the partial output is still logged.
    * ``expected_exit_code`` (default 0) is matched literally.

    **Phase 1 out-of-scope** (Codex 計画レビュー + Step 7 横断レビュー):

    * Interactive / TTY-requiring commands.
    * Stdin payloads.
    * Long-running daemons / process-tree kill / signal handling
      (Codex 9: ``subprocess.run(..., timeout=...)`` kills the direct
      child only; grandchildren may survive on Windows. Phase 2 should
      use Job Objects / process groups).
    * Network isolation, container / VM sandboxing.
    * Environment allowlist, secret masking.
    * Shell syntax (pipes, redirects), glob expansion.
    * Concurrent execution of multiple command stages in a single run.
    * Windows ``.bat`` / ``.cmd`` argument-escaping (Codex 8): even with
      ``shell=False`` Windows batch invocation can apply additional
      argument parsing. Phase 1 does not normalise this; users should
      prefer real executables (``.exe``, interpreter argv) over batch
      files until Phase 2.
    * **Real-memory cap on captured output** (Codex 1): the 64 KiB tail
      truncation here is a *log* cap, not an *execution* cap.
      ``subprocess.run(..., capture_output=True)`` buffers the full
      stream in memory before this function ever sees it, so a command
      that writes gigabytes of stdout will allocate gigabytes before
      the truncate. Phase 2 should switch to a ``Popen`` + incremental
      read pipeline if real-memory caps become a requirement.
    """
    import os
    import subprocess

    contract = stage.contract
    command_arg = contract.get("command")
    expected_exit_code = contract.get("expected_exit_code", 0)
    timeout_seconds = contract.get("timeout_seconds", _COMMAND_DEFAULT_TIMEOUT_SECONDS)
    working_dir_arg = contract.get("working_dir")

    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: command",
        f"contract_ref: {stage.contract_ref}",
        f"command: {command_arg}",
        f"expected_exit_code: {expected_exit_code}",
        f"timeout_seconds: {timeout_seconds}",
    ]
    if working_dir_arg:
        log_lines.append(f"working_dir: {working_dir_arg}")

    # Validate the argv shape: must be a non-empty list of non-empty strings.
    if (
        not isinstance(command_arg, list)
        or not command_arg
        or any(not isinstance(a, str) or not a for a in command_arg)
    ):
        log_lines.append(
            "result: failed (contract.command must be a non-empty list of "
            "non-empty strings)"
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

    # Resolve working_dir under project_root (R1: never escape).
    if working_dir_arg:
        try:
            cwd_path = resolve_project_relative(
                project_root, working_dir_arg, "contract.working_dir"
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
        if not cwd_path.is_dir():
            log_lines.append(
                f"result: failed (working_dir does not exist: {cwd_path})"
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
    else:
        cwd_path = project_root

    log_lines.append(f"resolved cwd: {cwd_path}")
    log_lines.append("")
    log_lines.append("--- execution ---")

    # Run the command. Phase 1 (Codex 計画レビュー):
    #   shell=False, env=os.environ.copy(), stdin=DEVNULL,
    #   capture stdout/stderr separately and tail-truncate each.
    try:
        completed = subprocess.run(  # noqa: S603 - argv list, shell=False
            command_arg,
            shell=False,
            cwd=str(cwd_path),
            env=os.environ.copy(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except FileNotFoundError as exc:
        log_lines.append(f"command not found: {exc}")
        log_lines.append("result: failed (command not found)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    except PermissionError as exc:
        log_lines.append(f"permission denied: {exc}")
        log_lines.append("result: failed (permission denied)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )
    except subprocess.TimeoutExpired as exc:
        # Partial output may still be available on the exception.
        partial_stdout = exc.stdout or ""
        partial_stderr = exc.stderr or ""
        if isinstance(partial_stdout, bytes):
            partial_stdout = partial_stdout.decode("utf-8", errors="replace")
        if isinstance(partial_stderr, bytes):
            partial_stderr = partial_stderr.decode("utf-8", errors="replace")
        out_tail, out_trunc = _tail_truncate(
            partial_stdout, _COMMAND_STREAM_CAP_BYTES
        )
        err_tail, err_trunc = _tail_truncate(
            partial_stderr, _COMMAND_STREAM_CAP_BYTES
        )
        log_lines.append(f"timeout after {timeout_seconds}s")
        log_lines.append(
            f"stdout ({'truncated, tail only' if out_trunc else 'full'}):"
        )
        log_lines.append(out_tail)
        log_lines.append(
            f"stderr ({'truncated, tail only' if err_trunc else 'full'}):"
        )
        log_lines.append(err_tail)
        log_lines.append("result: failed (timeout)")
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
        )

    out_tail, out_trunc = _tail_truncate(
        completed.stdout or "", _COMMAND_STREAM_CAP_BYTES
    )
    err_tail, err_trunc = _tail_truncate(
        completed.stderr or "", _COMMAND_STREAM_CAP_BYTES
    )
    log_lines.append(f"exit_code: {completed.returncode}")
    log_lines.append(
        f"stdout ({'truncated, tail only' if out_trunc else 'full'}):"
    )
    log_lines.append(out_tail)
    log_lines.append(
        f"stderr ({'truncated, tail only' if err_trunc else 'full'}):"
    )
    log_lines.append(err_tail)

    if completed.returncode == expected_exit_code:
        log_lines.append("result: passed")
        outcome: StageOutcome = "passed"
    else:
        log_lines.append(
            f"result: failed (expected exit_code={expected_exit_code}, "
            f"got {completed.returncode})"
        )
        outcome = "failed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=int(completed.returncode),
        log_text="\n".join(log_lines) + "\n",
    )


# ---- json_schema verification_type (Step 8 項目 1) ----------------------

# Codex 計画レビュー: Phase 1 では JSON Schema の $ref を意図的にサポート
# しない。$ref が schema 内に存在したら failed として扱う。これにより
# R1 ガード (target / schema 両方が project root 配下に閉じ込められる)
# を ``jsonschema`` ライブラリの ref 解決経路と切り離せる。


def _schema_contains_dollar_ref(node: object) -> bool:
    """Recursively detect any ``$ref`` key in a parsed JSON Schema.

    Phase 1 contract: ``json_schema`` verification rejects schemas that
    use ``$ref`` (internal or external). This keeps R1 path resolution
    the only entry point for filesystem access — the ``jsonschema``
    library is never asked to resolve a reference.
    """
    if isinstance(node, dict):
        if "$ref" in node:
            return True
        return any(_schema_contains_dollar_ref(v) for v in node.values())
    if isinstance(node, list):
        return any(_schema_contains_dollar_ref(v) for v in node)
    return False


def _run_json_schema(project_root: Path, stage: AdoptedStage) -> StageResult:
    """Execute a ``verification_type=json_schema`` stage.

    Phase 1 design (Codex 計画レビュー 2026-05-31):

    * ``target`` (workspace-relative) is parsed as JSON.
    * ``schema`` (workspace-relative) is parsed as JSON and
      validated as a JSON Schema via
      ``jsonschema.validators.validator_for(schema).check_schema()``.
    * Both ``target`` and ``schema`` paths go through
      :func:`qgb.core.loader.resolve_project_relative` — escapes
      (absolute, ``..``-relative, symlinks pointing outside) are
      rejected as failed.
    * ``$ref`` in the schema (internal or external) is unsupported
      and treated as failed (see :func:`_schema_contains_dollar_ref`).
    * Validation failures are reported as failed with the violation
      path + message in ``log_text``.

    **Phase 1 out-of-scope** (Codex 計画レビュー):

    * ``$ref`` resolution (Phase 2 allowlist-based support).
    * JSON Schema ``format`` assertions (Phase 2 strict-mode opt-in).
    * Streaming validation / memory caps for large JSON inputs
      (Phase 2; current implementation buffers the full target).
    * Remote / network schema fetch (always unsupported in qgb).
    """
    import json as _json

    contract = stage.contract
    target = contract.get("target")
    schema_path_str = contract.get("schema")

    log_lines = [
        f"stage_id: {stage.stage_id}",
        f"name: {stage.name}",
        "verification_type: json_schema",
        f"contract_ref: {stage.contract_ref}",
        f"target: {target}",
        f"schema: {schema_path_str}",
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
    # (_run_file_exists / _run_substring_match / _run_command all log
    # ``resolved: ...`` after R1 path resolution succeeds).
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
        target_data = _json.loads(target_full.read_text(encoding="utf-8"))
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
        schema_data = _json.loads(schema_full.read_text(encoding="utf-8"))
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

    # Phase 1: $ref unsupported. Reject before handing the schema to
    # ``jsonschema`` so its resolver is never invoked.
    if _schema_contains_dollar_ref(schema_data):
        log_lines.append(
            "result: failed ($ref in schema is unsupported in Phase 1; "
            "see contract docs)"
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

    # Phase 1: format is NOT enforced (Codex 計画レビュー方針).
    #
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
