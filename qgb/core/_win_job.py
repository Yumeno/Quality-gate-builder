"""Windows Job Object wrapper for process-tree kill (Step 3.1b-3 +
Step 3.1 補修 #2/#3 で transactional spawn + hardening を統合).

The module owns the entire lifecycle of a Job Object **and** the
suspended-spawn dance that puts a Popen child into it before any
grandchild can escape. Step 3.1 補修 #2 で
:meth:`WindowsJob.spawn_suspended_and_resume` を追加し、外形的に
「suspended の子が外へ漏れない」transactional cleanup を保証する
形に格上げした (philosophy P9 段階単一責任 + P7 再現可能な証跡)。

Exposed API:

* :func:`is_supported` — runtime probe for "are we on Windows AND was
  ctypes / kernel32 loadable?" Callers should treat ``False`` as the
  signal to skip Job Object setup and fall back to ``Popen.kill``.
* :class:`WindowsJob` — context-managed Job Object handle.
  - :meth:`spawn_suspended_and_resume` — transactional spawn (推奨)。
  - :meth:`assign` / :meth:`terminate` — lower-level primitives.
  - ``close()`` (or ``__exit__``) terminates every process in the job.
* :data:`JobUnsupportedError` — raised by ``WindowsJob`` constructor
  or any setup step on failure. Callers degrade gracefully (kill
  direct child + emit ``runner_warning``).

Why ctypes instead of pywin32:

* NF-010 (依存最小化) — qgb's only runtime dependency is
  ``jsonschema``. Adding pywin32 just for one ctypes-equivalent call
  site would expand the supply-chain surface (NF-011).
* Windows-only code paths must not break import on POSIX — we keep
  ``ctypes.WinDLL`` lookups lazy (inside ``is_supported`` / methods).

Step 3.1 補修 #3 で導入した hardening:

* ``ctypes.WinDLL("kernel32", use_last_error=True)`` で独立にロード。
  従来の ``ctypes.windll.kernel32`` は ``use_last_error=False`` 相当で
  ``ctypes.get_last_error()`` が常に 0 を返す盲点があった (P7 違反:
  fallback メッセージのエラー番号が嘘の値になる)。
* 関数ポインタ (CreateJobObjectW 等) を ``__init__`` で **インスタンス
  固有に bind**。従来は ``self._kernel32.OpenProcess.argtypes = [...]``
  を呼び出し毎に再代入していたため、他コードが同じ kernel32 関数を
  別 argtypes で使う場合のグローバル汚染リスクがあった。
* :meth:`_close_handle` は try/finally で ``self._closed = True`` を
  確実に立てる。従来は ``CloseHandle`` の OSError 以外の例外で
  ``_closed`` が False のまま残り、二重 close 経路に入る余地があった。

KILL_ON_JOB_CLOSE flag (load-bearing): job 内のすべてのプロセスを
最終 handle close 時に kill する。qgb が SIGSEGV 等で異常終了しても
OS が孤児を reap してくれる defense-in-depth。
"""

from __future__ import annotations

import os


class JobUnsupportedError(RuntimeError):
    """Raised when Job Object setup fails at creation time."""


def is_supported() -> bool:
    """Return True iff we're on Windows AND kernel32 is loadable.

    Probing happens once at call time; we don't memoise because
    ``ctypes`` lookup is already cached by the loader, and callers
    typically invoke this at most once per ``_run_subprocess`` call.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes

        # Step 3.1 補修 #3: use_last_error=True で独立にロード。
        # ctypes.windll.kernel32 (use_last_error=False 相当) では
        # ``ctypes.get_last_error()`` が常に 0 を返してしまう。
        ctypes.WinDLL("kernel32", use_last_error=True)
        return True
    except (AttributeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Win32 constants and structures.
#
# Definitions sourced from the public Microsoft Learn docs as cited in
# development/docs/journal/phase3-step3-1. Values must not be changed
# without a fresh cross-reference to the canonical Win32 SDK headers.

# JOBOBJECTINFOCLASS enum, value 9.
_JOB_OBJECT_INFO_CLASS_EXTENDED_LIMIT_INFORMATION = 9

# JOB_OBJECT_LIMIT_FLAGS bit for "kill all processes in the job when
# the last handle to the job is closed."
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000

# OpenProcess desired_access bits. We need TERMINATE (for the fallback
# kill path) and SET_QUOTA (the latter is the historically required
# right for AssignProcessToJobObject, even when no quotas are imposed).
_PROCESS_TERMINATE = 0x0001
_PROCESS_SET_QUOTA = 0x0100

# CreateProcess creationflags: child is created suspended and does not
# execute a single instruction until ResumeThread runs. We use this in
# :meth:`spawn_suspended_and_resume` so the child cannot spawn
# grandchildren before it is assigned to the job.
_CREATE_SUSPENDED = 0x00000004

# CreateToolhelp32Snapshot flags + OpenThread access bits.
_TH32CS_SNAPTHREAD = 0x00000004
_THREAD_SUSPEND_RESUME = 0x0002


def _build_extended_limit_information_struct():
    """Construct the ctypes Structure used by SetInformationJobObject.

    The struct layout follows JOBOBJECT_EXTENDED_LIMIT_INFORMATION
    (winnt.h). We only set the ``LimitFlags`` field within
    ``BasicLimitInformation``; every other field stays zero so no
    quota / I/O / process-count limits are imposed.

    Returning the type from a function (rather than module-level)
    keeps the ``import ctypes`` cost out of POSIX module-load paths.
    """
    import ctypes

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    return _JOBOBJECT_EXTENDED_LIMIT_INFORMATION


def _build_thread_entry_struct():
    """Construct THREADENTRY32 (tlhelp32.h) struct lazily."""
    import ctypes
    from ctypes import wintypes

    class _Struct(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    return _Struct


class WindowsJob:
    """Context-managed Job Object with transactional spawn helper.

    Two usage patterns:

    Preferred (Step 3.1 補修 #2): transactional spawn::

        with WindowsJob() as job:
            process = job.spawn_suspended_and_resume(argv, **popen_kwargs)
            # ここから process は走行中。
            # 「suspended のまま外に出ている」状態が存在しないことが
            # spawn_suspended_and_resume の事後条件。
            ...
        # __exit__: KILL_ON_JOB_CLOSE が発火 → 残存プロセス全 kill

    Lower-level (まれな個別制御が必要なときのみ)::

        with WindowsJob() as job:
            proc = subprocess.Popen(..., creationflags=CREATE_SUSPENDED)
            job.assign(proc.pid)
            # caller が自前で ResumeThread する責務を持つ
            ...

    The class never raises ``OSError`` from teardown — close()
    failures are swallowed because there is no caller that could do
    anything useful with them; the worst case is one leaked job
    handle per qgb stage, which the OS will reap on process exit.
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        # Step 3.1 補修 #3 (P7 強化): use_last_error=True で独立ロード。
        # これにより ctypes.get_last_error() が真の GetLastError 値を
        # 返す。fallback メッセージのエラー番号が事実を語るようになる。
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._closed = False
        self._handle = None  # type: ignore[assignment]

        # Step 3.1 補修 #3: 関数ポインタを インスタンス固有に bind して
        # argtypes/restype を一度だけ設定する。従来は assign() 呼び出し
        # ごとに argtypes 再代入していたため、他コードが kernel32 を
        # 別 argtypes で使うとグローバル汚染が起きうる盲点があった。
        self._CreateJobObjectW = self._kernel32.CreateJobObjectW
        self._CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self._CreateJobObjectW.restype = wintypes.HANDLE

        self._SetInformationJobObject = self._kernel32.SetInformationJobObject
        self._SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._SetInformationJobObject.restype = wintypes.BOOL

        self._OpenProcess = self._kernel32.OpenProcess
        self._OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._OpenProcess.restype = wintypes.HANDLE

        self._AssignProcessToJobObject = self._kernel32.AssignProcessToJobObject
        self._AssignProcessToJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.HANDLE,
        ]
        self._AssignProcessToJobObject.restype = wintypes.BOOL

        self._TerminateJobObject = self._kernel32.TerminateJobObject
        self._TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self._TerminateJobObject.restype = wintypes.BOOL

        self._CloseHandle = self._kernel32.CloseHandle
        self._CloseHandle.argtypes = [wintypes.HANDLE]
        self._CloseHandle.restype = wintypes.BOOL

        # Thread snapshot + Resume — used by spawn_suspended_and_resume.
        self._CreateToolhelp32Snapshot = self._kernel32.CreateToolhelp32Snapshot
        self._CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        self._CreateToolhelp32Snapshot.restype = wintypes.HANDLE

        self._Thread32First = self._kernel32.Thread32First
        self._Thread32First.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self._Thread32First.restype = wintypes.BOOL

        self._Thread32Next = self._kernel32.Thread32Next
        self._Thread32Next.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
        self._Thread32Next.restype = wintypes.BOOL

        self._OpenThread = self._kernel32.OpenThread
        self._OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._OpenThread.restype = wintypes.HANDLE

        self._ResumeThread = self._kernel32.ResumeThread
        self._ResumeThread.argtypes = [wintypes.HANDLE]
        self._ResumeThread.restype = wintypes.DWORD

        # CreateJobObjectW(NULL, NULL) — unnamed job, default security.
        handle = self._CreateJobObjectW(None, None)
        if not handle:
            err = ctypes.get_last_error()
            raise JobUnsupportedError(
                f"CreateJobObjectW failed (GetLastError={err}); "
                "falling back to per-child kill"
            )
        self._handle = handle

        # Configure: kill-on-job-close so even an abrupt qgb crash
        # still reaps the descendants.
        struct_type = _build_extended_limit_information_struct()
        info = struct_type()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        ok = self._SetInformationJobObject(
            handle,
            _JOB_OBJECT_INFO_CLASS_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            err = ctypes.get_last_error()
            self._close_handle()
            raise JobUnsupportedError(
                f"SetInformationJobObject failed (GetLastError={err}); "
                "job created but not configured"
            )

    def spawn_suspended_and_resume(
        self,
        argv,
        **popen_kwargs,
    ):
        """Spawn ``argv`` under this job with transactional cleanup.

        Sequence (Step 3.1 補修 #2 = "入らない設計"):

        1. ``subprocess.Popen(creationflags = existing | CREATE_SUSPENDED)``
           で子を suspended で起動。
        2. :meth:`assign` で job に紐付け。失敗時は **必ず子を
           kill + wait してから raise** (suspended のまま外に漏らさない)。
        3. :meth:`_resume_child_main_thread` で実行開始。失敗時は同様に
           必ず子を kill してから raise。

        どこで失敗しても呼び出し元に「suspended で動いていない子の
        Popen オブジェクト」を返さない、というのが事後条件
        (transactional cleanup)。OS 的に atomic ではないため
        ``BaseException`` を使って KeyboardInterrupt も含めて cleanup。

        ``creationflags`` は **既存値に OR**。caller が独自 flag を
        指定していてもそれを尊重する。
        """
        import subprocess

        existing_flags = int(popen_kwargs.pop("creationflags", 0))
        merged_kwargs = dict(popen_kwargs)
        merged_kwargs["creationflags"] = existing_flags | _CREATE_SUSPENDED

        # Popen 自体は同期 API。失敗 (FileNotFoundError 等) は呼び出し元へ
        # propagate。spawn 成功後の cleanup 責務をここで持つ。
        process = subprocess.Popen(argv, **merged_kwargs)  # noqa: S603

        try:
            self.assign(process.pid)
            self._resume_child_main_thread(process.pid)
        except BaseException:
            # assign / resume のどれが失敗しても、suspended の子を
            # 確実に殺してから再 raise。process.kill() + process.wait()
            # 自身は失敗しても (子が既に死んでいる等) 黙殺。
            try:
                process.kill()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            raise
        return process

    def _resume_child_main_thread(self, pid: int) -> None:
        """Find ``pid``'s main thread via toolhelp snapshot and resume it.

        Step 3.1 補修 #2: 旧 _resume_via_main_thread (command.py) を
        WindowsJob に移送。これにより:
        - resume responsibility が WindowsJob に集約 (P9 段階単一責任)
        - command.py 側の dead branch (_handle_thread 試行) を削除可能

        失敗は OSError として raise。spawn_suspended_and_resume の
        ``except BaseException:`` 経路で子の kill + wait まで含めて
        cleanup される。
        """
        import ctypes

        snapshot = self._CreateToolhelp32Snapshot(_TH32CS_SNAPTHREAD, 0)
        # INVALID_HANDLE_VALUE は -1。ctypes が HANDLE を符号付き int
        # として返す環境を想定して -1 と 0 の両方を不正値扱い。
        if not snapshot or snapshot == ctypes.c_void_p(-1).value:
            err = ctypes.get_last_error()
            raise OSError(f"CreateToolhelp32Snapshot failed (GetLastError={err})")

        struct_type = _build_thread_entry_struct()
        try:
            entry = struct_type()
            entry.dwSize = ctypes.sizeof(struct_type)
            ok = self._Thread32First(snapshot, ctypes.byref(entry))
            while ok:
                if entry.th32OwnerProcessID == pid:
                    thread_handle = self._OpenThread(
                        _THREAD_SUSPEND_RESUME, False, entry.th32ThreadID
                    )
                    if thread_handle:
                        try:
                            self._ResumeThread(thread_handle)
                            return
                        finally:
                            self._CloseHandle(thread_handle)
                ok = self._Thread32Next(snapshot, ctypes.byref(entry))
            raise OSError(f"no threads found for pid {pid}")
        finally:
            self._CloseHandle(snapshot)

    def assign(self, pid: int) -> None:
        """Add the process with PID ``pid`` to this job.

        Raises :class:`JobUnsupportedError` on failure. The high-level
        :meth:`spawn_suspended_and_resume` catches this and cleans up
        the suspended child; lower-level callers must do the same.
        """
        if self._closed:
            raise JobUnsupportedError("job handle already closed")

        import ctypes

        proc_handle = self._OpenProcess(
            _PROCESS_SET_QUOTA | _PROCESS_TERMINATE,
            False,
            pid,
        )
        if not proc_handle:
            err = ctypes.get_last_error()
            raise JobUnsupportedError(
                f"OpenProcess({pid}) failed (GetLastError={err})"
            )

        try:
            ok = self._AssignProcessToJobObject(self._handle, proc_handle)
            if not ok:
                err = ctypes.get_last_error()
                raise JobUnsupportedError(
                    f"AssignProcessToJobObject(pid={pid}) failed "
                    f"(GetLastError={err}); the qgb host may itself be "
                    "running inside an incompatible Job Object"
                )
        finally:
            # CloseHandle on the process handle does NOT kill the
            # process — that's exactly what we want. The job retains
            # an internal reference to the assigned process.
            self._CloseHandle(proc_handle)

    def terminate(self) -> None:
        """Actively kill every process in the job NOW.

        Unlike the implicit kill-on-close behaviour, this is
        synchronous: when this method returns, the job's processes
        have been signalled to die (though they may not be reaped
        yet). Callers should still ``Popen.wait()`` to clean up the
        zombie / handles.
        """
        if self._closed:
            return
        # exit_code 1 mirrors the "killed by signal" convention.
        self._TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        if self._closed:
            return
        self._close_handle()

    def _close_handle(self) -> None:
        """Internal: release the job handle; KILL_ON_JOB_CLOSE applies.

        Step 3.1 補修 #3: try/finally で ``_closed = True`` を確実に
        立てる。従来は CloseHandle が OSError 以外 (例: ctypes
        ArgumentError) を投げると ``_closed`` が False のまま残り、
        後続 close で二重 close する経路があった。
        """
        if self._handle is None:
            self._closed = True
            return
        try:
            self._CloseHandle(self._handle)
        except OSError:
            # Already closed by the OS or a stray double-close.
            # Nothing useful we can do; flag is set in finally.
            pass
        finally:
            self._closed = True

    def __enter__(self) -> WindowsJob:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
