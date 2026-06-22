"""Windows Job Object wrapper for process-tree kill (Step 3.1b-3).

This module is intentionally Windows-only and self-contained. The
exposed API is:

* :func:`is_supported` — runtime probe for "are we on Windows AND was
  ctypes / kernel32 loadable?" Callers should treat ``False`` as the
  signal to skip Job Object setup and fall back to ``Popen.kill``.
* :class:`WindowsJob` — context-managed Job Object handle. Assign a
  process to it via :meth:`assign`; ``close()`` (or ``__exit__``)
  terminates every process in the job.
* :data:`JobUnsupportedError` — raised by ``WindowsJob`` constructor
  if any of the underlying Win32 calls fail at job creation time.
  The caller in :mod:`qgb.core.command` catches this and records a
  ``runner_warning`` while falling back to ``Popen.kill``.

Why we use ctypes instead of pywin32:

* NF-010 (依存最小化) — qgb's only runtime dependency is
  ``jsonschema``. Adding pywin32 just for one ctypes-equivalent call
  site would expand the supply-chain surface (NF-011).
* Windows-only code paths must not break import on POSIX — using
  ``import ctypes`` at module top is safe (POSIX ships it) as long
  as the ``windll.kernel32`` reference is created lazily inside
  ``is_supported`` and the ``WindowsJob`` constructor.

API design notes:

* ``KILL_ON_JOB_CLOSE`` is the load-bearing flag. Setting it on the
  job means "when the last handle to this job closes, terminate
  every process assigned to it." So even if qgb crashes between
  ``assign`` and ``close``, Windows will reap the descendants when
  our process exits.
* ``AssignProcessToJobObject`` must run BEFORE the child has a
  chance to spawn grandchildren. The natural sequence is:

    1. Job object created and configured.
    2. ``Popen(creationflags=CREATE_SUSPENDED)`` — child is created
       suspended; it has not executed a single instruction yet.
    3. Assign the child to the job.
    4. ``ResumeThread`` on the child's primary thread.

  Steps 2 and 4 happen in :mod:`qgb.core.command`; this module
  owns step 1 and 3 plus all teardown.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import ctypes as _ctypes_for_typing  # noqa: F401


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

        ctypes.windll.kernel32  # noqa: B018 - touching the attribute is the probe
        return True
    except (AttributeError, OSError):
        return False


# ---------------------------------------------------------------------------
# Win32 constants and structures.
#
# We deliberately keep these as module-level literals so the values are
# self-documenting in source review. Definitions sourced from the public
# Microsoft Learn docs as cited in development/docs/journal/phase3-step3-1
# (and reproduced in code comments below). Values must not be changed
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


class WindowsJob:
    """Context-managed Job Object that kills its members on close.

    Usage::

        with WindowsJob() as job:
            proc = subprocess.Popen(..., creationflags=CREATE_SUSPENDED)
            job.assign(proc.pid)
            kernel32.ResumeThread(proc._handle)  # see command.py

        # Exit from ``with``: every process in the job is terminated.

    The class never raises ``OSError`` from teardown — close()
    failures are swallowed because there is no caller that could do
    anything useful with them; the worst case is one leaked job
    handle per qgb stage, which the OS will reap on process exit.
    """

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._kernel32 = ctypes.windll.kernel32
        self._closed = False

        # CreateJobObjectW(NULL, NULL) — unnamed job, default security.
        # The W variant takes LPCWSTR but we pass NULL so it's
        # symbol-only; we don't need ctypes-side argtype declarations
        # for this single call.
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        handle = self._kernel32.CreateJobObjectW(None, None)
        if not handle:
            err = ctypes.get_last_error()
            raise JobUnsupportedError(
                f"CreateJobObjectW failed (GetLastError={err}); "
                "falling back to per-child kill"
            )
        self._handle = handle

        # Configure the job: set the LimitFlags so all members die
        # when the last handle (this one) is closed.
        struct_type = _build_extended_limit_information_struct()
        info = struct_type()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL
        ok = self._kernel32.SetInformationJobObject(
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

    def assign(self, pid: int) -> None:
        """Add the process with PID ``pid`` to this job.

        Raises :class:`JobUnsupportedError` on failure. Caller in
        :mod:`qgb.core.command` is expected to catch this and degrade
        gracefully (kill direct child + emit ``runner_warning``).
        """
        if self._closed:
            raise JobUnsupportedError("job handle already closed")

        import ctypes
        from ctypes import wintypes

        # OpenProcess(PROCESS_SET_QUOTA | PROCESS_TERMINATE, ...)
        self._kernel32.OpenProcess.argtypes = [
            wintypes.DWORD,
            wintypes.BOOL,
            wintypes.DWORD,
        ]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        proc_handle = self._kernel32.OpenProcess(
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
            self._kernel32.AssignProcessToJobObject.argtypes = [
                wintypes.HANDLE,
                wintypes.HANDLE,
            ]
            self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
            ok = self._kernel32.AssignProcessToJobObject(
                self._handle, proc_handle
            )
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
            self._kernel32.CloseHandle(proc_handle)

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

        from ctypes import wintypes

        self._kernel32.TerminateJobObject.argtypes = [
            wintypes.HANDLE,
            wintypes.UINT,
        ]
        self._kernel32.TerminateJobObject.restype = wintypes.BOOL
        # exit_code 1 mirrors the "killed by signal" convention.
        self._kernel32.TerminateJobObject(self._handle, 1)

    def close(self) -> None:
        if self._closed:
            return
        self._close_handle()

    def _close_handle(self) -> None:
        """Internal: release the job handle; KILL_ON_JOB_CLOSE applies."""
        try:
            self._kernel32.CloseHandle(self._handle)
        except OSError:
            # Already closed by the OS or a stray double-close.
            # Nothing useful we can do; mark closed so we don't try
            # again.
            pass
        self._closed = True

    def __enter__(self) -> WindowsJob:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
