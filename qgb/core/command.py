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
* Step 3.1 補修 #2 (DONE, 2026-06-23) — WindowsJob に transactional
  spawn (``spawn_suspended_and_resume``) を統合。command.py の
  Windows 経路は WindowsJob を context manager として使い、
  assign/resume のどこで失敗しても「suspended の子が外へ漏れる」
  ステートに入らない構造に再設計。dead branch (``_handle_thread``
  試行) と ``_resume_via_main_thread`` を削除。
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

# Step 3.1c: how often the supervisor polls cap_state and process
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


class _CapExceededState:
    """First-wins cap overflow signal — name + flag を 1 オブジェクトに統合.

    Step 3.1 補修 #5 (philosophy P7 + P9 + 「入らない設計」, Codex r2 指摘)
    で導入。補修 #6 (Codex 段 5 r1) で **read も Lock 内** に揃え、
    「説明と実装の同期境界」を一致させた。

    旧設計は ``threading.Event`` (= flag) と ``list[str]`` (= stream
    name 蓄積) の 2 変数で「cap exceeded 状態」を表現していた。これは
    「event 立っているのに stream name が読めない」中間ステートを
    GIL の挙動に依存して回避する暗黙的な設計だった (`append` 後に
    ``set`` する順序契約)。

    本クラスは 1 オブジェクトで:
    - ``try_set(name)``: first-wins で stream 名を記録 (Lock 内)
    - ``snapshot()``: 現在の name を Lock 内で読む (None なら未到達)
    - ``is_set()``: 越えたかどうか (snapshot のラッパー)

    を ``Lock`` で保護する。「中間ステート」が **同期境界の中で完結**
    する設計。GIL の atomic-write 挙動への依存もなくなるので、将来の
    free-threading 化 (PEP 703) にも耐性。

    Lock の取得コストは _drain_stream あたり最大 1 回 (first-wins で
    set 後は判定スキップ) + supervisor / 最終判定での read 数回なので
    runtime 影響は無視できる範囲。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._name: str | None = None

    def try_set(self, name: str) -> bool:
        """First call sets the name and returns True; later calls return False."""
        with self._lock:
            if self._name is None:
                self._name = name
                return True
            return False

    def snapshot(self) -> str | None:
        """Return the stream name that first crossed the cap (Lock 内 read).

        補修 #6 (Codex 段 5 r1): name / is_set を Lock 内で読むことで
        「同期境界の中で読み書きが完結する」契約を明示化。CPython
        GIL の object reference atomic-write に暗黙依存しない。
        """
        with self._lock:
            return self._name

    def is_set(self) -> bool:
        """True iff some stream has crossed the cap (Lock 内 read)."""
        return self.snapshot() is not None


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
    cap_state: _CapExceededState,
    stream_name: str,
) -> None:
    """Read every byte from ``stream`` into ``sink`` until EOF or cap hit.

    Used as a reader-thread target. We accept the raw bytes here (no
    per-thread decode) so multi-byte boundaries are not silently split
    between thread chunks — the full bytes are decoded once at the end
    in :func:`_run_subprocess`. The ``read1`` call blocks only on the
    pipe, not on EOF/exit, so the thread quits promptly when the child
    closes its end (kill or natural exit).

    Step 3.1 補修 #5: cap 状態を ``_CapExceededState`` に統合
    (旧 ``cap_event`` + ``overflow_record`` 2 変数の race-prone な
    分離を排除)。``cap_state.try_set(stream_name)`` が first-wins
    で stream 名と flag を 1 命令で確定させる。

    The thread keeps draining after a cap crossing so the child does
    not block on a full pipe — the supervisor in
    :func:`_run_subprocess` is responsible for issuing the kill, after
    which the read1 will return b"" and the thread exits. Excess
    bytes ARE appended past ``cap_bytes`` so the log can still show
    the last 64 KiB; the supervisor only cares that the cap was
    crossed at least once.
    """
    overflow_recorded = False
    try:
        while True:
            chunk = stream.read1(_READER_CHUNK_BYTES)
            if not chunk:
                return
            sink.extend(chunk)
            if not overflow_recorded and len(sink) >= cap_bytes:
                # First-wins: try_set returns True only for the first
                # caller. False means another stream already won; we
                # still mark our local flag so we don't keep checking.
                cap_state.try_set(stream_name)
                overflow_recorded = True
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

    # Step 3.1d: Windows ``.bat`` / ``.cmd`` argument escaping
    # (escape は Windows / POSIX どちらでも先に決定する。POSIX では
    # needs_bat_escaping=False で no-op、Windows では .bat/.cmd の
    # head + tail を均一に quote 化した command line string が返る)。
    from qgb.core._win_bat_escape import build_command_line, needs_bat_escaping

    if needs_bat_escaping(argv):
        spawn_args: list[str] | str = build_command_line(argv)
    else:
        spawn_args = argv

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
        # Default buffered I/O (bufsize=-1) gives BufferedReader so
        # _drain_stream can call read1.
        process = subprocess.Popen(spawn_args, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603
    else:
        # Step 3.1 補修 #2 (philosophy P9 + 「入らない設計」):
        # Windows 経路は WindowsJob.spawn_suspended_and_resume に統合。
        # この context manager は「Popen + assign + resume」を transactional
        # に実行する — 途中で失敗しても suspended の子は必ず kill+wait
        # されてから例外が出るので、「suspended のまま動いていない子の
        # Popen オブジェクトを呼び出し元が握る」状態が存在しない。
        #
        # job 作成自体に失敗した場合 (nested job 環境等) は runner_warning
        # を立てて素の Popen 経路にフォールバック。grandchildren leak の
        # 可能性は runner_warning として gate.json の audit に残る。
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
        else:
            runner_warning = (
                "windows job object api unavailable; "
                "process tree kill degraded to direct-child only"
            )

        if win_job is not None:
            try:
                process = win_job.spawn_suspended_and_resume(
                    spawn_args, **popen_kwargs
                )
            except JobUnsupportedError as exc:
                # assign 失敗。spawn_suspended_and_resume は子を kill+wait
                # 済なので、こちらは job を閉じてフォールバック経路へ。
                new_warning = (
                    "windows job object assign failed; "
                    "process tree kill degraded to direct-child only "
                    f"({exc})"
                )
                runner_warning = (
                    new_warning if runner_warning is None
                    else f"{runner_warning}; {new_warning}"
                )
                win_job.close()
                win_job = None
                process = subprocess.Popen(spawn_args, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603
            except OSError as exc:
                # resume 失敗 (toolhelp snapshot 異常等)。同様に
                # spawn_suspended_and_resume が子を kill+wait 済。
                new_warning = (
                    "windows resume failed; "
                    "process tree kill degraded to direct-child only "
                    f"({exc})"
                )
                runner_warning = (
                    new_warning if runner_warning is None
                    else f"{runner_warning}; {new_warning}"
                )
                win_job.close()
                win_job = None
                process = subprocess.Popen(spawn_args, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603
        else:
            # Job Object 不採用パス。直接 Popen — 孫プロセスは leak しうる
            # が runner_warning は既に立っている。
            process = subprocess.Popen(spawn_args, **popen_kwargs)  # type: ignore[arg-type]  # noqa: S603

    stdout_sink = bytearray()
    stderr_sink = bytearray()

    # _drain_stream closes its pipe argument on exit; if Popen ever
    # returns with stdout/stderr=None despite our PIPE request the
    # following lines would crash — but that combination is documented
    # impossible by the stdlib, so we treat it as a hard invariant.
    assert process.stdout is not None
    assert process.stderr is not None

    # Step 3.1 補修 #5: cap 状態を _CapExceededState に統合
    # (旧 cap_event + overflow_record 2 変数の race-prone な分離を消す)。
    cap_state = _CapExceededState()

    out_thread = threading.Thread(
        target=_drain_stream,
        args=(
            process.stdout,
            stdout_sink,
            _COMMAND_EXECUTION_CAP_BYTES,
            cap_state,
            "stdout",
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
            cap_state,
            "stderr",
        ),
        name="qgb-cmd-stderr-reader",
        daemon=True,
    )
    out_thread.start()
    err_thread.start()

    # Step 3.1 補修 #1 + #6 (philosophy P7: 再現可能な証跡の徹底):
    #
    # supervisor loop は **観測契機** のみを扱う。最終結果は reader
    # thread を join した後に確定する (補修 #6 = Codex 段 5 r1 指摘で
    # 「観測契機の優先順 ≠ 最終結果の優先順」と判明したため)。
    #
    # supervisor 観測契機の優先順 (loop を抜けるトリガー):
    #
    #   A. ``process.poll()`` 非 None → 子が exit (kill 不要)
    #   B. ``cap_state.is_set()`` → cap 越え (kill 必要)
    #   C. ``time.monotonic() >= deadline`` → 時間切れ (kill 必要)
    #
    # この観測契機は **早期離脱の判定** であって、最終結果ではない。
    # 例えば A で抜けた場合でも、その瞬間 reader thread が cap を
    # まだ書き終えていない可能性があり、reader を join した時点で
    # cap_state が真になるケースがある (child writes over cap →
    # child exits quickly → supervisor が poll を先に観測する race)。
    #
    # 最終結果の優先順 (reader join 後に確定):
    #
    #   1. cap exceeded (出力 16 MiB 超過の事実が観測されたら、子の
    #      exit/timeout に関係なく cap_exceeded を最終 reason に)
    #   2. timeout (cap でない and 時間切れ)
    #   3. natural exit
    #
    # この設計により「cap 越えていたのに natural exit 扱いになる」
    # 状態が消える ("入らない設計", Codex 段 5 r1)。
    observed_exit_rc: int | None = None  # supervisor A 観測時の rc
    observed_timeout = False
    needs_kill = False
    deadline = time.monotonic() + timeout_seconds

    while True:
        rc = process.poll()
        if rc is not None:
            observed_exit_rc = rc
            break
        if cap_state.is_set():
            needs_kill = True
            break
        if time.monotonic() >= deadline:
            observed_timeout = True
            needs_kill = True
            break
        # 観測待ち sleep。_CAP_POLL_INTERVAL_SECONDS = 100 ms。
        time.sleep(_CAP_POLL_INTERVAL_SECONDS)

    # 観測 B / C の場合は kill が必要。observed_exit_rc は kill 後の
    # wait で上書きされる (子は既に signal された状態)。
    if needs_kill:
        _terminate_process(process, win_job=win_job)
        observed_exit_rc = process.wait()

    # Reader threads は Popen が pipe を閉じるまで動き続ける (natural
    # exit でも kill 後でも同じ)。join で完了を待ち、cap_state の
    # 最終値を確定させる — これが「観測契機 ≠ 最終結果」の核心。
    out_thread.join(timeout=5)
    err_thread.join(timeout=5)

    # Closing the job triggers KILL_ON_JOB_CLOSE for any straggler
    # processes; safe to call even after explicit TerminateJobObject.
    if win_job is not None:
        win_job.close()

    stdout_text = bytes(stdout_sink).decode("utf-8", errors="replace")
    stderr_text = bytes(stderr_sink).decode("utf-8", errors="replace")

    # 補修 #6: 最終結果は reader join 後に cap > timeout > natural exit
    # の優先順で確定する。supervisor が natural exit を観測していても、
    # reader thread が遅れて cap を確定させていれば cap が勝つ。
    # cap_state.snapshot() を 1 回だけ取り出して使う (再呼び出しで Lock
    # を無駄に取らない)。
    final_cap_stream = cap_state.snapshot()
    if final_cap_stream == "stdout":
        reason: str | None = _REASON_STDOUT_CAP_EXCEEDED
        timed_out = False
    elif final_cap_stream == "stderr":
        reason = _REASON_STDERR_CAP_EXCEEDED
        timed_out = False
    elif observed_timeout:
        reason = _REASON_COMMAND_TIMEOUT
        timed_out = True
    else:
        reason = None
        timed_out = False
    returncode = observed_exit_rc

    return _SubprocessResult(
        returncode=returncode,
        stdout=stdout_text,
        stderr=stderr_text,
        timed_out=timed_out,
        reason=reason,
        runner_warning=runner_warning,
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
