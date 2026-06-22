"""Execute ``verification_type=command`` stages.

This module is the carve-out of ``_run_command`` from :mod:`qgb.core.runner`
created in Phase 3 Step 3.1a (P9: keep ``command``-stage execution in a
dedicated module so subsequent sub-steps can layer Popen + process tree
kill + output cap + ``.bat`` argument escaping without bloating
``runner.py``). The behaviour in Step 3.1a is **byte-identical** to the
old ``runner._run_command``; only its location and the public name
change.

Sub-steps that will modify this file in order:

* Step 3.1b-1 — switch ``subprocess.run`` to ``subprocess.Popen`` with
  incremental reader threads (kill path stays equivalent to the old
  ``timeout`` argument).
* Step 3.1b-2 — POSIX process group kill (``preexec_fn=os.setsid`` +
  ``killpg``).
* Step 3.1b-3 — Windows process tree kill via Job Objects (ctypes).
* Step 3.1c — 16 MiB execution cap, separate from the 64 KiB log tail.
* Step 3.1d — ``.bat`` / ``.cmd`` argument escaping (cmd.exe
  metacharacters + MSVCRT argv parsing, two distinct escapers).

The runner module remains the dispatcher: it still chooses which
verification_type to run, and forwards ``verification_type=command`` to
:func:`run_command` here. Existing import paths
(``from qgb.core.runner import StageResult, run_stages``) are
preserved — Step 3.1a does not break the public surface.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from qgb.core.loader import LoaderError, resolve_project_relative

if TYPE_CHECKING:
    from qgb.core.preflight import AdoptedStage
    from qgb.core.runner import StageOutcome, StageResult


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


def run_command(project_root: Path, stage: AdoptedStage) -> StageResult:
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

    **Phase 1 out-of-scope** (Codex 計画レビュー + Step 7 横断レビュー)
    — addressed incrementally in Step 3.1b〜3.1d, see module docstring:

    * Interactive / TTY-requiring commands.
    * Stdin payloads.
    * Long-running daemons / process-tree kill / signal handling
      (Codex 9: ``subprocess.run(..., timeout=...)`` kills the direct
      child only; grandchildren may survive on Windows. Step 3.1b
      introduces Job Objects / process groups).
    * Network isolation, container / VM sandboxing.
    * Environment allowlist, secret masking.
    * Shell syntax (pipes, redirects), glob expansion.
    * Concurrent execution of multiple command stages in a single run.
    * Windows ``.bat`` / ``.cmd`` argument-escaping (Codex 8): even with
      ``shell=False`` Windows batch invocation can apply additional
      argument parsing. Step 3.1d adds two-stage escaping (cmd.exe
      metacharacters + MSVCRT argv parsing).
    * **Real-memory cap on captured output** (Codex 1): the 64 KiB tail
      truncation here is a *log* cap, not an *execution* cap.
      ``subprocess.run(..., capture_output=True)`` buffers the full
      stream in memory before this function ever sees it, so a command
      that writes gigabytes of stdout will allocate gigabytes before
      the truncate. Step 3.1c switches to a ``Popen`` + incremental
      read pipeline with a 16 MiB execution cap.
    """
    from qgb.core.runner import StageResult  # avoid module-level cycle

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
