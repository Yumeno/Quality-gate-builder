"""Execute ``verification_type=command`` stages.

This module is the carve-out of ``_run_command`` from :mod:`qgb.core.runner`
created in Phase 3 Step 3.1a (P9: keep ``command``-stage execution in a
dedicated module so subsequent sub-steps can layer Popen + process tree
kill + output cap + ``.bat`` argument escaping without bloating
``runner.py``).

Sub-step status:

* Step 3.1a (DONE) — carve-out from runner.py, behaviour byte-identical
  with ``subprocess.run``.
* Step 3.1b-1 (DONE) — switched ``subprocess.run`` to ``subprocess.Popen``
  with incremental reader threads. External behaviour
  byte-equivalent.
* Step 3.1b-2 (this sub-step) — POSIX process group kill. The child is
  put into its own session via ``preexec_fn=os.setsid``, and timeouts
  kill the **whole process group** via ``killpg(SIGTERM)`` → grace →
  ``killpg(SIGKILL)``. Windows path is still ``Popen.kill`` until
  3.1b-3 — that asymmetry is intentional, see ``_terminate_process``.
* Step 3.1b-3 — Windows process tree kill via Job Objects (ctypes).
* Step 3.1c — 16 MiB execution cap, separate from the 64 KiB log tail
  (run_subprocess switches to bytes counters + active kill).
* Step 3.1d — ``.bat`` / ``.cmd`` argument escaping (cmd.exe
  metacharacters + MSVCRT argv parsing, two distinct escapers).

The runner module remains the dispatcher: it still chooses which
verification_type to run, and forwards ``verification_type=command`` to
:func:`run_command` here. Existing import paths
(``from qgb.core.runner import StageResult, run_stages``) are
preserved — Step 3.1b-1 does not break the public surface.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, BinaryIO

from qgb.core.loader import LoaderError, resolve_project_relative

if TYPE_CHECKING:
    from qgb.core.preflight import AdoptedStage
    from qgb.core.runner import StageOutcome, StageResult


# Per-stream output cap (Codex 計画レビュー: 64 KiB, tail-prioritised).
# Failure tracebacks tend to appear at the tail of stderr, so we keep the
# last bytes of each stream rather than the first.
_COMMAND_STREAM_CAP_BYTES = 64 * 1024
_COMMAND_DEFAULT_TIMEOUT_SECONDS = 60


# Step 3.1b-1: switch to Popen + reader threads. The chunk size is the
# usual subprocess pipe granularity; it balances syscall overhead and
# wakeup latency. Larger values matter once Step 3.1c adds a 16 MiB
# execution cap and we need to notice overruns promptly.
_READER_CHUNK_BYTES = 64 * 1024


# Step 3.1b-2: POSIX kill grace period between SIGTERM and SIGKILL.
# 3 s is the conventional value that lets a Python child run an
# atexit handler / context manager cleanup, while still bounding the
# qgb stage's tail latency. The value is intentionally not a contract
# field — Step 3.1d-and-later may make it configurable if needed.
_POSIX_KILL_GRACE_SECONDS = 3.0

_IS_POSIX = os.name == "posix"


@dataclass(frozen=True)
class _SubprocessResult:
    """In-memory outcome of a single subprocess invocation.

    ``timed_out`` is True iff :func:`_run_subprocess` had to kill the
    child because its ``timeout`` expired. ``returncode`` may be a
    signal-like negative number on POSIX in that case; on Windows the
    Popen ``kill`` translates to an arbitrary positive code. Callers
    should treat ``timed_out`` as the authoritative flag and use
    ``returncode`` only when ``timed_out`` is False.

    ``stdout`` / ``stderr`` are utf-8 decoded text. Decode errors are
    replaced (not raised) so a stage cannot crash on a bad byte in a
    user command's output — the bytes-to-text loss is the price we pay
    for putting binary-ish output into a markdown log.
    """

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool


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


def _drain_stream(stream: BinaryIO, sink: bytearray) -> None:
    """Read every byte from ``stream`` into ``sink`` until EOF.

    Used as a reader-thread target. We accept the raw bytes here (no
    per-thread decode) so multi-byte boundaries are not silently split
    between thread chunks — the full bytes are decoded once at the end
    in :func:`_run_subprocess`. The ``readinto1``-style ``read1`` call
    blocks only on the pipe, not on EOF/exit, so the thread quits
    promptly when the child closes its end (kill or natural exit).
    """
    try:
        while True:
            chunk = stream.read1(_READER_CHUNK_BYTES)
            if not chunk:
                return
            sink.extend(chunk)
    finally:
        # Step 3.1b-1: closing the pipe end on this side is safe even
        # when the child has already exited. The Popen wrapper closes
        # them again on cleanup; double-close on a Python file object
        # is a no-op rather than an OSError.
        try:
            stream.close()
        except OSError:
            pass


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    """Kill ``process`` and its descendants as best the platform allows.

    Step 3.1b-2 (POSIX): the child was started with
    ``preexec_fn=os.setsid``, so ``process.pid`` is also the leader of
    a fresh session / process group. We send SIGTERM to the whole
    group (``killpg``), wait up to :data:`_POSIX_KILL_GRACE_SECONDS`
    for cooperative shutdown, then send SIGKILL to whatever is left.
    This is the conventional two-stage POSIX kill.

    Step 3.1b-3 (Windows, not yet implemented): falls back to
    ``Popen.kill`` so the direct child dies, but Windows
    grandchildren can still survive — a separate sub-step will
    introduce a Job Object so the whole tree dies atomically.

    The function never raises:

    * ``ProcessLookupError`` from a race where the child exited between
      poll and signal is ignored — that race resolves the goal anyway.
    * ``PermissionError`` on Windows (e.g. when a child has dropped
      privileges) is logged via stderr only; the runner_warning path
      will surface it in Step 3.1c via a structured field.

    Caller must ``process.wait()`` after this returns so the OS reaps
    the zombie / Popen releases its handles.
    """
    if _IS_POSIX:
        try:
            pgid = os.getpgid(process.pid)
        except ProcessLookupError:
            return
        # Phase 1: SIGTERM the whole group, wait for cooperative exit.
        try:
            os.killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            return
        # Poll instead of fixed sleep so a fast-exiting child doesn't
        # cost us the full 3 s. Granularity 100 ms is fine — we only
        # need to be a small constant slower than the slowest cleanly
        # behaved Python atexit handler.
        deadline = time.monotonic() + _POSIX_KILL_GRACE_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.1)
        # Phase 2: anyone still alive gets SIGKILL. Some descendants
        # may have detached via setsid()-of-their-own — those are out
        # of scope, see framework-shape.md §5.
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return
    else:
        # Windows: direct child only until Step 3.1b-3 puts the
        # subprocess into a Job Object.
        try:
            process.kill()
        except ProcessLookupError:
            return


def _run_subprocess(
    argv: list[str],
    cwd: str,
    env: dict[str, str],
    timeout_seconds: float,
) -> _SubprocessResult:
    """Run ``argv`` with Popen + reader threads, returning text I/O.

    External behaviour parity with the old ``subprocess.run`` call:

    * ``shell=False``, ``stdin=DEVNULL`` — same constraints, no shell
      interpolation, no interactive input.
    * On timeout, the child is killed via :func:`_terminate_process`
      (POSIX: SIGTERM-then-SIGKILL on the whole process group; Windows:
      direct ``Popen.kill`` until 3.1b-3 swaps in Job Objects). The
      captured-so-far output is returned with ``timed_out=True``.
    * ``FileNotFoundError`` / ``PermissionError`` from Popen
      construction propagate to the caller, matching the old contract.

    Process tree kill status (Step 3.1b-2 of 3 in this sub-cluster):

    * POSIX: a new session via ``preexec_fn=os.setsid`` makes
      ``process.pid`` a process group leader. ``killpg`` then reaches
      every descendant **unless** the descendant has explicitly
      detached via its own ``setsid()`` — those willingly-orphaned
      processes are out of scope (framework-shape.md §5).
    * Windows: still per-process. ``Popen.kill`` terminates the direct
      child; grandchildren can survive until Step 3.1b-3.

    No 16 MiB output cap yet — Step 3.1c lands an active kill when
    either stream exceeds the cap.
    """
    # OS-specific Popen kwargs. ``preexec_fn`` is POSIX-only and would
    # raise ``ValueError`` on Windows if passed at all, so we build the
    # kwargs dict conditionally rather than using ``preexec_fn=None``.
    popen_kwargs: dict[str, object] = {
        "shell": False,
        "cwd": cwd,
        "env": env,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if _IS_POSIX:
        # ``preexec_fn=os.setsid`` runs in the child after ``fork()``
        # but before ``exec``, making the child the leader of a new
        # session AND a new process group. That gives ``killpg`` a
        # well-defined target. The classic ``preexec_fn`` thread-safety
        # warning (CVE-equivalent: fork from a multithreaded parent
        # leaves the child in an inconsistent state) does not apply to
        # qgb here because reader threads are started **after** Popen
        # returns; at the fork instant the parent is single-threaded.
        popen_kwargs["preexec_fn"] = os.setsid  # type: ignore[assignment]

    # Default buffered I/O (bufsize=-1) is what gives us ``BufferedReader``
    # on stdout/stderr — its ``read1`` returns whatever bytes are
    # available without waiting for a full buffer, which is what the
    # reader threads need for prompt progress.
    process = subprocess.Popen(argv, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603 - argv list, shell=False

    stdout_sink = bytearray()
    stderr_sink = bytearray()

    # _drain_stream closes its pipe argument on exit; if Popen ever
    # returns with stdout/stderr=None despite our PIPE request the
    # following lines would crash — but that combination is documented
    # impossible by the stdlib, so we treat it as a hard invariant.
    assert process.stdout is not None
    assert process.stderr is not None

    out_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stdout, stdout_sink),
        name="qgb-cmd-stdout-reader",
        daemon=True,
    )
    err_thread = threading.Thread(
        target=_drain_stream,
        args=(process.stderr, stderr_sink),
        name="qgb-cmd-stderr-reader",
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

    timed_out = False
    try:
        returncode = process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        _terminate_process(process)
        # wait() again so the OS reaps the zombie and reader threads
        # see EOF on the now-closed pipes. No timeout on the second
        # wait because the child has been signalled to die.
        returncode = process.wait()

    # Reader threads finish once Popen closes its pipe ends (natural
    # exit OR kill). Join with a small grace period so even if a
    # thread misses its EOF poll we don't leak.
    out_thread.join(timeout=5)
    err_thread.join(timeout=5)

    stdout_text = bytes(stdout_sink).decode("utf-8", errors="replace")
    stderr_text = bytes(stderr_sink).decode("utf-8", errors="replace")

    return _SubprocessResult(
        returncode=returncode,
        stdout=stdout_text,
        stderr=stderr_text,
        timed_out=timed_out,
    )


def run_command(project_root: Path, stage: AdoptedStage) -> StageResult:
    """Execute a ``verification_type=command`` stage.

    Step 3.1b-1 (2026-06-22): subprocess invocation now goes through
    :func:`_run_subprocess` (Popen + reader threads). The visible
    contract is unchanged from Step 3.1a — same exit code, same text
    log fields, same failure-on-timeout message. The internal change
    enables the 16 MiB execution cap (Step 3.1c) and the OS-specific
    process tree kill (Step 3.1b-2 / 3.1b-3) without further reshaping
    this function.

    Phase 1 design points still in force:

    * ``shell=False`` — argv array only, no shell interpolation. Shell
      metacharacters are passed through ``argv[0]`` literally, so a
      command like ``"a ; b"`` is searched for as a single filename
      and fails with ENOENT.
    * Inherited environment (``os.environ.copy()``). Phase 2 may
      restrict this; for now the alternative (minimal env) breaks too
      many real-world commands.
    * ``stdin=DEVNULL`` — interactive commands are out of scope.
    * stdout / stderr captured to memory; each tail-truncated to 64
      KiB for the log (tracebacks live at the end).
    * ``cwd`` defaults to ``project_root`` but a contract may specify
      a ``working_dir`` (project-root-relative). Escapes are rejected
      by ``resolve_project_relative`` (Step 5 R1).
    * Timeout from ``timeout_seconds`` (default 60). A timeout is
      reported as failed with the captured partial output.
    * ``expected_exit_code`` (default 0) is matched literally.

    **Out-of-scope** (addressed incrementally in later sub-steps, see
    module docstring): TTY commands, stdin payloads, network sandbox,
    env allowlist, secret masking, shell syntax, concurrent stages,
    .bat / .cmd argument escaping (Step 3.1d), and execution-time
    output cap (Step 3.1c). Process tree kill is partially addressed
    here — only the direct child dies; grandchildren survive until
    Step 3.1b-2 (POSIX) and Step 3.1b-3 (Windows).
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

    try:
        sub_result = _run_subprocess(
            argv=command_arg,
            cwd=str(cwd_path),
            env=os.environ.copy(),
            timeout_seconds=timeout_seconds,
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

    if sub_result.timed_out:
        out_tail, out_trunc = _tail_truncate(
            sub_result.stdout, _COMMAND_STREAM_CAP_BYTES
        )
        err_tail, err_trunc = _tail_truncate(
            sub_result.stderr, _COMMAND_STREAM_CAP_BYTES
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
        sub_result.stdout, _COMMAND_STREAM_CAP_BYTES
    )
    err_tail, err_trunc = _tail_truncate(
        sub_result.stderr, _COMMAND_STREAM_CAP_BYTES
    )
    log_lines.append(f"exit_code: {sub_result.returncode}")
    log_lines.append(
        f"stdout ({'truncated, tail only' if out_trunc else 'full'}):"
    )
    log_lines.append(out_tail)
    log_lines.append(
        f"stderr ({'truncated, tail only' if err_trunc else 'full'}):"
    )
    log_lines.append(err_tail)

    if sub_result.returncode == expected_exit_code:
        log_lines.append("result: passed")
        outcome: StageOutcome = "passed"
    else:
        log_lines.append(
            f"result: failed (expected exit_code={expected_exit_code}, "
            f"got {sub_result.returncode})"
        )
        outcome = "failed"

    return StageResult(
        stage_id=stage.stage_id,
        name=stage.name,
        verification_type=stage.verification_type,
        contract_ref=stage.contract_ref,
        result=outcome,
        exit_code=int(sub_result.returncode),
        log_text="\n".join(log_lines) + "\n",
    )
