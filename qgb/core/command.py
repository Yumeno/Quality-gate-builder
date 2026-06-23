"""Execute ``verification_type=command`` stages.

This module is the carve-out of ``_run_command`` from :mod:`qgb.core.runner`
created in Phase 3 Step 3.1a (P9: keep ``command``-stage execution in a
dedicated module so subsequent sub-steps can layer Popen + process tree
kill + output cap + ``.bat`` argument escaping without bloating
``runner.py``).

Sub-step status:

* Step 3.1a (DONE) — carve-out from runner.py, behaviour byte-identical
  with ``subprocess.run``.
* Step 3.1b-1 (DONE) — switched to ``subprocess.Popen`` + reader threads.
* Step 3.1b-2 (DONE) — POSIX process group kill via
  ``preexec_fn=os.setsid`` + ``killpg``.
* Step 3.1b-3 (DONE) — Windows process tree kill via
  :class:`qgb.core._win_job.WindowsJob`. ``runner_warning`` field on
  :class:`_SubprocessResult` records Job Object setup failures so
  fallback to direct-child kill is auditable.
* Step 3.1c (this sub-step) — 16 MiB per-stream execution cap. Reader
  threads watch their sink size and signal :class:`threading.Event`
  on overflow; the supervisor in :func:`_run_subprocess` then runs
  the same kill path as a timeout. Stream name is recorded in
  :attr:`_SubprocessResult.reason` so the log can tell stdout
  overflow from stderr overflow. Reason enum covers every non-passing
  exit so the gate.runtime schema gets a finite machine-readable set
  (Codex 指摘: P7 構造化フィールド).
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


# Step 3.1c (Codex 指摘で 2 つの cap を明示分離):
#
# * EXECUTION cap is what the reader threads enforce on the live
#   process. Once stdout OR stderr reaches 16 MiB we kill the process
#   tree to prevent a runaway command from exhausting qgb's RAM.
#   The cap is **per stream**, not summed: a noisy stderr should not
#   eat the budget that lets stdout finish a 12 MiB pytest summary.
# * LOG_TAIL cap is what we serialise to gate.json / stage logs.
#   Tracebacks tend to live at the tail, so we keep the trailing
#   64 KiB of each stream rather than the first bytes.
#
# Worst-case retained-in-RAM under cap: stdout 16 MiB + stderr 16 MiB
# + log construction overhead ≈ 35 MiB. This is the explicit ceiling
# the docs and framework-shape §5 quote.
_COMMAND_EXECUTION_CAP_BYTES = 16 * 1024 * 1024
_COMMAND_LOG_TAIL_CAP_BYTES = 64 * 1024

# Back-compat alias for code that imports the old name; tests pin this
# constant value. Step 3.1c-internal code uses _COMMAND_LOG_TAIL_CAP_BYTES
# for clarity.
_COMMAND_STREAM_CAP_BYTES = _COMMAND_LOG_TAIL_CAP_BYTES

_COMMAND_DEFAULT_TIMEOUT_SECONDS = 60


# Step 3.1b-1: switch to Popen + reader threads. The chunk size is the
# usual subprocess pipe granularity; it balances syscall overhead and
# wakeup latency. Step 3.1c needs to notice overruns within ~one
# chunk's worth of bytes so 64 KiB keeps overshoot well under the
# 16 MiB cap.
_READER_CHUNK_BYTES = 64 * 1024


# Step 3.1b-2: POSIX kill grace period between SIGTERM and SIGKILL.
# 3 s is the conventional value that lets a Python child run an
# atexit handler / context manager cleanup, while still bounding the
# qgb stage's tail latency. The value is intentionally not a contract
# field — Step 3.1d-and-later may make it configurable if needed.
_POSIX_KILL_GRACE_SECONDS = 3.0

# Step 3.1c: how often the supervisor polls cap_event and process
# exit while wait()-ing in the long-running path. Same order as
# _POSIX_KILL_GRACE_SECONDS poll granularity — enough latency budget
# for ~16 MiB overshoot at sub-ms detection.
_CAP_POLL_INTERVAL_SECONDS = 0.1

_IS_POSIX = os.name == "posix"


# Step 3.1c: structured exit reasons surfaced through
# _SubprocessResult.reason. None means "child exited normally; check
# returncode for pass/fail." These strings will appear in
# gate.runtime.stages[].reason once the schema is extended (Task 26),
# so the values themselves are part of the gate.json contract — do
# not rename without a schema migration.
_REASON_COMMAND_TIMEOUT = "command_timeout"
_REASON_STDOUT_CAP_EXCEEDED = "stdout_cap_exceeded"
_REASON_STDERR_CAP_EXCEEDED = "stderr_cap_exceeded"


@dataclass(frozen=True)
class _SubprocessResult:
    """In-memory outcome of a single subprocess invocation.

    ``stdout`` / ``stderr`` are utf-8 decoded text. Decode errors are
    replaced (not raised) so a stage cannot crash on a bad byte in a
    user command's output — the bytes-to-text loss is the price we pay
    for putting binary-ish output into a markdown log. Note that the
    bytes are **already capped at 16 MiB per stream** by the reader
    threads (Step 3.1c); the further 64 KiB tail truncation in
    :func:`run_command` is for log readability, not RAM safety.

    ``timed_out`` is True iff the supervisor had to kill the child
    because its ``timeout`` expired (it is a convenience alias for
    ``reason == "command_timeout"`` — kept distinct for back-compat
    with tests that pin ``timed_out`` directly).

    Step 3.1c: ``reason`` is a structured machine-readable exit code:

    * ``None`` — child exited naturally; consult ``returncode``.
    * ``"command_timeout"`` — wall-clock timeout fired.
    * ``"stdout_cap_exceeded"`` — stdout reached 16 MiB.
    * ``"stderr_cap_exceeded"`` — stderr reached 16 MiB.

    Future runners may add codes for spawn / internal failures, but
    those are currently surfaced via exception-flow (caller's
    ``except FileNotFoundError`` etc.), not via ``reason``.

    Step 3.1b-3: ``runner_warning`` is a structured field set when the
    Windows Job Object setup degraded to the per-process kill fallback
    (typically because the qgb host process is itself inside an
    incompatible Job Object). ``None`` means "no warnings, kill path
    was the full strength one for this platform." Step 3.1c lifts
    this and ``reason`` into a gate.runtime structured field so audit
    logs can be searched.
    """

    returncode: int
    stdout: str
    stderr: str
    timed_out: bool
    reason: str | None = None
    runner_warning: str | None = None


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


def _drain_stream(
    stream: BinaryIO,
    sink: bytearray,
    cap_bytes: int,
    cap_event: threading.Event,
    stream_name: str,
    overflow_record: list[str],
) -> None:
    """Read every byte from ``stream`` into ``sink`` until EOF or cap hit.

    Used as a reader-thread target. We accept the raw bytes here (no
    per-thread decode) so multi-byte boundaries are not silently split
    between thread chunks — the full bytes are decoded once at the end
    in :func:`_run_subprocess`. The ``read1`` call blocks only on the
    pipe, not on EOF/exit, so the thread quits promptly when the child
    closes its end (kill or natural exit).

    Step 3.1c: once the sink reaches ``cap_bytes``, the thread sets
    ``cap_event`` and appends the offending stream name to
    ``overflow_record`` (a list used as a thread-safe one-shot signal —
    Python list append is atomic under the GIL). The thread then keeps
    draining so the child does not block on a full pipe — the
    supervisor in :func:`_run_subprocess` is responsible for issuing
    the kill, after which the read1 will return b"" and the thread
    exits. Excess bytes ARE appended past ``cap_bytes`` so the log can
    still show the last 64 KiB; the supervisor only cares that the
    cap was crossed at least once.
    """
    overflow_recorded = False
    try:
        while True:
            chunk = stream.read1(_READER_CHUNK_BYTES)
            if not chunk:
                return
            sink.extend(chunk)
            if not overflow_recorded and len(sink) >= cap_bytes:
                # First crossing wins. We do this before .set() so the
                # supervisor sees a populated overflow_record by the
                # time it inspects cap_event.
                overflow_record.append(stream_name)
                overflow_recorded = True
                cap_event.set()
    finally:
        # Step 3.1b-1: closing the pipe end on this side is safe even
        # when the child has already exited. The Popen wrapper closes
        # them again on cleanup; double-close on a Python file object
        # is a no-op rather than an OSError.
        try:
            stream.close()
        except OSError:
            pass


def _terminate_process(
    process: subprocess.Popen[bytes],
    win_job: object | None = None,
) -> None:
    """Kill ``process`` and its descendants as best the platform allows.

    Step 3.1b-2 (POSIX): the child was started with
    ``preexec_fn=os.setsid``, so ``process.pid`` is also the leader of
    a fresh session / process group. We send SIGTERM to the whole
    group (``killpg``), wait up to :data:`_POSIX_KILL_GRACE_SECONDS`
    for cooperative shutdown, then send SIGKILL to whatever is left.
    This is the conventional two-stage POSIX kill.

    Step 3.1b-3 (Windows): when ``win_job`` is a
    :class:`qgb.core._win_job.WindowsJob` instance, calling
    ``terminate()`` on it kills every process in the job (the direct
    child plus every grandchild created after the assign). The job
    handle is closed by the ``with`` block in :func:`_run_subprocess`,
    and the ``KILL_ON_JOB_CLOSE`` flag provides defense-in-depth
    against a qgb crash between assign and close. When ``win_job`` is
    ``None`` (job setup failed; ``runner_warning`` is being recorded
    by the caller), we fall back to ``Popen.kill`` for the direct
    child only.

    The function never raises:

    * ``ProcessLookupError`` from a race where the child exited between
      poll and signal is ignored — that race resolves the goal anyway.
    * Win32 errors from ``WindowsJob.terminate`` are swallowed inside
      the wrapper for the same reason: there is no useful recovery
      and the caller is already returning a failed StageResult.

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
        # Windows: prefer the Job Object terminate path. If
        # win_job is None we already recorded a runner_warning
        # and accept that grandchildren may leak.
        if win_job is not None:
            try:
                win_job.terminate()  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - any Win32 failure becomes a leak risk we cannot avoid here
                pass
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
    * On timeout, the child (and its descendants, on a supported OS)
      is killed via :func:`_terminate_process`. The captured-so-far
      output is returned with ``timed_out=True``.
    * ``FileNotFoundError`` / ``PermissionError`` from Popen
      construction propagate to the caller, matching the old contract.

    Process tree kill status (Step 3.1b-3 lands the Windows path):

    * POSIX: a new session via ``preexec_fn=os.setsid`` makes
      ``process.pid`` a process group leader. ``killpg`` then reaches
      every descendant **unless** the descendant has explicitly
      detached via its own ``setsid()`` — those willingly-orphaned
      processes are out of scope (framework-shape.md §5).
    * Windows: the child is created ``CREATE_SUSPENDED``, assigned to
      a :class:`qgb.core._win_job.WindowsJob`, then resumed. Job
      ``KILL_ON_JOB_CLOSE`` plus our explicit ``TerminateJobObject``
      on timeout kill the entire tree. If Job Object setup fails
      (nested job, privilege issue), we degrade to ``Popen.kill`` of
      the direct child only AND populate ``runner_warning`` so the
      stage log captures the asymmetry rather than hiding it.

    Step 3.1c: each reader thread enforces a 16 MiB per-stream
    execution cap. Crossing the cap sets a shared
    :class:`threading.Event`; the supervisor loop polls both that
    event and the process exit and kills the tree on overflow with
    ``reason="stdout_cap_exceeded"`` / ``"stderr_cap_exceeded"``.
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

    runner_warning: str | None = None
    win_job = None

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
    else:
        # Windows path: try to create a Job Object and start the
        # child suspended so we can assign it before any grandchild
        # spawns. If the job can't be created, runner_warning is set
        # and the child runs without the job — grandchildren may leak
        # in that case but the visible behaviour stays consistent.
        from qgb.core._win_job import JobUnsupportedError, WindowsJob, is_supported

        if is_supported():
            try:
                win_job = WindowsJob()
            except JobUnsupportedError as exc:
                runner_warning = (
                    "windows job object unavailable; "
                    "process tree kill degraded to direct-child only "
                    f"({exc})"
                )
                win_job = None
            if win_job is not None:
                # CREATE_SUSPENDED so the child doesn't execute any
                # code (and therefore can't spawn grandchildren) until
                # we have assigned it to the job.
                _CREATE_SUSPENDED = 0x00000004
                popen_kwargs["creationflags"] = _CREATE_SUSPENDED
        else:
            runner_warning = (
                "windows job object api unavailable; "
                "process tree kill degraded to direct-child only"
            )

    # Step 3.1d: Windows ``.bat`` / ``.cmd`` argument escaping.
    # ``subprocess.list2cmdline`` (used by Popen on Windows when args
    # is a list) only quotes when whitespace or ``"`` is present;
    # cmd.exe metacharacters (& | < > % ...) are left bare, so
    # passing ``["a & b"]`` to a ``.bat`` would invoke a second
    # command. For ``.bat`` / ``.cmd`` we build the command line
    # ourselves (with metacharacter-aware quoting) and pass it to
    # Popen as a single string — Popen on Windows then forwards the
    # string verbatim to ``CreateProcessW`` instead of re-quoting it.
    # For non-``.bat`` targets we keep the original argv-list path,
    # which is correct for plain ``.exe`` / interpreter invocations.
    from qgb.core._win_bat_escape import build_command_line, needs_bat_escaping

    if needs_bat_escaping(argv):
        spawn_args: list[str] | str = build_command_line(argv)
    else:
        spawn_args = argv

    # Default buffered I/O (bufsize=-1) is what gives us ``BufferedReader``
    # on stdout/stderr — its ``read1`` returns whatever bytes are
    # available without waiting for a full buffer, which is what the
    # reader threads need for prompt progress.
    process = subprocess.Popen(spawn_args, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603 - argv list or pre-built cmdline, shell=False

    # Windows: assign-then-resume. If assign fails we still need to
    # resume the child or it will hang forever; degrade to a warning
    # and fall through.
    if win_job is not None:
        from qgb.core._win_job import JobUnsupportedError

        try:
            win_job.assign(process.pid)
        except JobUnsupportedError as exc:
            new_warning = (
                "windows job object assign failed; "
                "process tree kill degraded to direct-child only "
                f"({exc})"
            )
            runner_warning = (
                new_warning if runner_warning is None
                else f"{runner_warning}; {new_warning}"
            )
            # Close the unused job so its KILL_ON_JOB_CLOSE doesn't
            # surprise anyone — it's empty anyway.
            win_job.close()
            win_job = None
        # Resume the child's main thread now that the job is set up
        # (or failed setup is logged). Popen on Windows stashes the
        # primary-thread handle on a private attribute.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            # ``_handle`` is a Popen private; on CPython for Windows
            # it's a ``subprocess.Handle`` (an int subclass). We get
            # the thread handle from ``process._handle`` via the
            # documented Popen attribute ``_handle`` — but Popen also
            # exposes the main thread handle as ``_handle`` is the
            # process handle; the main thread handle is private under
            # ``_thread_handle`` since 3.13 / ``_handle`` is the process.
            # We use the value Popen captured for ResumeThread.
            thread_handle = getattr(process, "_handle_thread", None)
            if thread_handle is None:
                # 3.11/3.12 expose the thread handle as
                # ``process._handle`` is the *process* and the *main
                # thread handle* is on the private subprocess.STARTUPINFO
                # mechanism. The safest portable approach is to call
                # OpenThread on process.pid → main thread, but Popen
                # already kept the handle: ``process._handle`` is the
                # process handle, not the thread handle, and stdlib
                # closes the thread handle after CREATE_SUSPENDED only
                # if we do not pass it. To resume reliably we instead
                # use the well-known ``NtResumeProcess``-equivalent:
                # call ResumeThread on every thread of the process. To
                # avoid this complexity entirely we use OpenThread on
                # the main thread id, which we get from the snapshot.
                _resume_via_main_thread(kernel32, process.pid)
            else:
                kernel32.ResumeThread(thread_handle)
        except Exception as exc:  # noqa: BLE001
            new_warning = (
                "windows resume thread failed; child may be stuck "
                f"suspended ({exc})"
            )
            runner_warning = (
                new_warning if runner_warning is None
                else f"{runner_warning}; {new_warning}"
            )

    stdout_sink = bytearray()
    stderr_sink = bytearray()

    # _drain_stream closes its pipe argument on exit; if Popen ever
    # returns with stdout/stderr=None despite our PIPE request the
    # following lines would crash — but that combination is documented
    # impossible by the stdlib, so we treat it as a hard invariant.
    assert process.stdout is not None
    assert process.stderr is not None

    # Step 3.1c: shared cap-event + overflow_record (first stream name
    # to cross the cap). overflow_record is a list because list.append
    # under the GIL is atomic enough for our single-writer-per-thread
    # use; the supervisor only reads it after cap_event is set.
    cap_event = threading.Event()
    overflow_record: list[str] = []

    out_thread = threading.Thread(
        target=_drain_stream,
        args=(
            process.stdout,
            stdout_sink,
            _COMMAND_EXECUTION_CAP_BYTES,
            cap_event,
            "stdout",
            overflow_record,
        ),
        name="qgb-cmd-stdout-reader",
        daemon=True,
    )
    err_thread = threading.Thread(
        target=_drain_stream,
        args=(
            process.stderr,
            stderr_sink,
            _COMMAND_EXECUTION_CAP_BYTES,
            cap_event,
            "stderr",
            overflow_record,
        ),
        name="qgb-cmd-stderr-reader",
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

    # Step 3.1 補修 #1 (philosophy P7: 再現可能な証跡の徹底):
    # supervisor loop の状態を 3 つに直交分割する。
    #
    # 各 iteration の先頭で確定的に 1 状態を判定する優先順:
    #
    #   1. ``process.poll()`` が None でない → natural exit
    #      (子が既に死んでいるなら、deadline 到達でも timeout 扱いに
    #      しない — gate.json が "死んでいたのに timeout" を語らない)
    #   2. ``cap_event`` set → cap exceeded
    #   3. ``time.monotonic() >= deadline`` → timeout
    #      (子が生きている and 時間切れ、で確定)
    #
    # これにより 3 状態が排他になり、「死んでいるのに timeout」が
    # 論理的に到達不能になる。旧設計 (``remaining <= 0`` 先頭判定 +
    # ``process.wait(timeout=...)`` の二段) は scheduler のタイミング
    # 次第で false-positive timeout を生み得るステート空間を持ってい
    # た — その空間自体を消す ("入らない設計", Codex 段 3 r2)。
    timed_out = False
    cap_exceeded_stream: str | None = None
    returncode: int | None = None
    deadline = time.monotonic() + timeout_seconds

    while True:
        rc = process.poll()
        if rc is not None:
            # 状態 1: natural exit。timed_out / cap_exceeded は False
            # のまま確定。子が deadline 直前に exit したケースも
            # ここに吸収される。
            returncode = rc
            break
        if cap_event.is_set():
            # 状態 2: cap exceeded。drain_stream が overflow_record を
            # append してから .set() しているので [0] は必ず存在。
            cap_exceeded_stream = overflow_record[0]
            break
        if time.monotonic() >= deadline:
            # 状態 3: timeout。子が生きている and 時間切れ、で確定。
            timed_out = True
            break
        # まだ判定できるシグナルなし。短く sleep して再 poll。
        # _CAP_POLL_INTERVAL_SECONDS は 100 ms 程度で、cap 検出 latency
        # と CPU 使用率のバランスを取った値。
        time.sleep(_CAP_POLL_INTERVAL_SECONDS)

    # Branch consolidation: if either timeout or cap fired we need to
    # kill the tree and reap.
    if timed_out or cap_exceeded_stream is not None:
        _terminate_process(process, win_job=win_job)
        # wait() again so the OS reaps the zombie and reader threads
        # see EOF on the now-closed pipes. No timeout on the second
        # wait because the child has been signalled to die.
        returncode = process.wait()

    # Reader threads finish once Popen closes its pipe ends (natural
    # exit OR kill). Join with a small grace period so even if a
    # thread misses its EOF poll we don't leak.
    out_thread.join(timeout=5)
    err_thread.join(timeout=5)

    # Closing the job triggers KILL_ON_JOB_CLOSE for any straggler
    # processes; safe to call even after explicit TerminateJobObject.
    if win_job is not None:
        win_job.close()

    stdout_text = bytes(stdout_sink).decode("utf-8", errors="replace")
    stderr_text = bytes(stderr_sink).decode("utf-8", errors="replace")

    # Pick the structured reason. Cap overflow takes precedence over
    # timeout: a cap was actually crossed even if the timeout also
    # happens to be expired by the time we get here.
    if cap_exceeded_stream == "stdout":
        reason: str | None = _REASON_STDOUT_CAP_EXCEEDED
    elif cap_exceeded_stream == "stderr":
        reason = _REASON_STDERR_CAP_EXCEEDED
    elif timed_out:
        reason = _REASON_COMMAND_TIMEOUT
    else:
        reason = None

    return _SubprocessResult(
        returncode=returncode,
        stdout=stdout_text,
        stderr=stderr_text,
        timed_out=timed_out,
        reason=reason,
        runner_warning=runner_warning,
    )


def _resume_via_main_thread(kernel32, pid: int) -> None:
    """Open the main thread of ``pid`` and call ResumeThread on it.

    Used as a fallback when Popen doesn't expose the main thread
    handle (CPython 3.11+ behaviour). We walk the toolhelp snapshot
    for the first thread belonging to the process and resume it.
    Any error here is fatal to the suspended child; the caller
    surfaces it via ``runner_warning``.
    """
    import ctypes
    from ctypes import wintypes

    _TH32CS_SNAPTHREAD = 0x00000004
    _THREAD_SUSPEND_RESUME = 0x0002

    class _THREADENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
    if not snapshot or snapshot == wintypes.HANDLE(-1).value:
        raise OSError("CreateToolhelp32Snapshot failed")

    try:
        entry = _THREADENTRY32()
        entry.dwSize = ctypes.sizeof(_THREADENTRY32)
        ok = kernel32.Thread32First(snapshot, ctypes.byref(entry))
        while ok:
            if entry.th32OwnerProcessID == pid:
                kernel32.OpenThread.restype = wintypes.HANDLE
                thread_handle = kernel32.OpenThread(
                    _THREAD_SUSPEND_RESUME, False, entry.th32ThreadID
                )
                if thread_handle:
                    try:
                        kernel32.ResumeThread(thread_handle)
                        return
                    finally:
                        kernel32.CloseHandle(thread_handle)
            ok = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
        raise OSError(f"no threads found for pid {pid}")
    finally:
        kernel32.CloseHandle(snapshot)


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

    # Step 3.1c: runner-side anomalies surface as ``reason`` codes.
    # Cap overflow takes precedence over timeout (a cap exceeded by
    # the very last chunk also tends to trip the timeout once kill
    # propagates). The runner_warning, when present, is appended to
    # every non-passing path so the gate.json log retains the
    # Job-Object-fallback signal.
    if sub_result.reason in (
        _REASON_STDOUT_CAP_EXCEEDED,
        _REASON_STDERR_CAP_EXCEEDED,
    ):
        stream_name = (
            "stdout"
            if sub_result.reason == _REASON_STDOUT_CAP_EXCEEDED
            else "stderr"
        )
        cap_mib = _COMMAND_EXECUTION_CAP_BYTES // (1024 * 1024)
        out_tail, out_trunc = _tail_truncate(
            sub_result.stdout, _COMMAND_LOG_TAIL_CAP_BYTES
        )
        err_tail, err_trunc = _tail_truncate(
            sub_result.stderr, _COMMAND_LOG_TAIL_CAP_BYTES
        )
        log_lines.append(
            f"{stream_name} exceeded {cap_mib} MiB execution cap; "
            "process tree killed"
        )
        log_lines.append(f"reason: {sub_result.reason}")
        if sub_result.runner_warning:
            log_lines.append(f"runner_warning: {sub_result.runner_warning}")
        log_lines.append(
            f"stdout ({'truncated, tail only' if out_trunc else 'full'}):"
        )
        log_lines.append(out_tail)
        log_lines.append(
            f"stderr ({'truncated, tail only' if err_trunc else 'full'}):"
        )
        log_lines.append(err_tail)
        log_lines.append(
            f"result: failed ({stream_name} exceeded {cap_mib} MiB)"
        )
        return StageResult(
            stage_id=stage.stage_id,
            name=stage.name,
            verification_type=stage.verification_type,
            contract_ref=stage.contract_ref,
            result="failed",
            exit_code=None,
            log_text="\n".join(log_lines) + "\n",
            reason=sub_result.reason,
            runner_warning=sub_result.runner_warning,
        )

    if sub_result.timed_out:
        out_tail, out_trunc = _tail_truncate(
            sub_result.stdout, _COMMAND_LOG_TAIL_CAP_BYTES
        )
        err_tail, err_trunc = _tail_truncate(
            sub_result.stderr, _COMMAND_LOG_TAIL_CAP_BYTES
        )
        log_lines.append(f"timeout after {timeout_seconds}s")
        log_lines.append(f"reason: {_REASON_COMMAND_TIMEOUT}")
        if sub_result.runner_warning:
            log_lines.append(f"runner_warning: {sub_result.runner_warning}")
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
            reason=sub_result.reason,
            runner_warning=sub_result.runner_warning,
        )

    out_tail, out_trunc = _tail_truncate(
        sub_result.stdout, _COMMAND_LOG_TAIL_CAP_BYTES
    )
    err_tail, err_trunc = _tail_truncate(
        sub_result.stderr, _COMMAND_LOG_TAIL_CAP_BYTES
    )
    log_lines.append(f"exit_code: {sub_result.returncode}")
    if sub_result.runner_warning:
        log_lines.append(f"runner_warning: {sub_result.runner_warning}")
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
        reason=sub_result.reason,
        runner_warning=sub_result.runner_warning,
    )
