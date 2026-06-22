"""Process tree kill tests for qgb.core.command._run_subprocess.

Step 3.1b-2 (POSIX) and 3.1b-3 (Windows) introduce OS-specific kill
paths so a stage timeout terminates not just the direct child but
also any grandchildren that the user's command may have spawned.
Phase 1's ``subprocess.run(..., timeout=N)`` killed only the direct
child, leaving Windows grandchildren and POSIX session-children
running — which is a P6/P7 risk because a "failed" stage may still
have side-effecting workers in the background.

The tests below use a **token + heartbeat fixture**:

1. A short parent script spawns a grandchild that periodically
   touches ``<temp>/child-alive-<token>.txt`` every 50 ms (heartbeat).
2. We invoke ``_run_subprocess`` with a 1 s timeout against the parent.
3. After kill, we poll the heartbeat file for a few seconds.
4. We assert that the heartbeat mtime stops being updated. Polling
   for an mtime-plateau is more robust than scraping ``pgrep`` /
   ``tasklist`` output, which is sensitive to environment names and
   permission boundaries.

Per-OS skipping:

* POSIX path (3.1b-2): exercised on Ubuntu CI and any POSIX dev box.
* Windows path (3.1b-3): currently expected to fail (grandchildren
  leak); this file marks the Windows leak test as ``xfail`` until
  3.1b-3 swaps in the Job Object kill. That gives us a regression
  net the moment 3.1b-3 lands.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

import pytest

from qgb.core.command import _COMMAND_DEFAULT_TIMEOUT_SECONDS, _run_subprocess

_HEARTBEAT_PAUSE_SECONDS = 2.0


def _parent_script_source(heartbeat_path: Path) -> str:
    """Source for the *parent* process: spawn the grandchild, then sleep.

    The grandchild is spawned with ``start_new_session=True`` only on
    POSIX so it lives in the *same* session/process-group as its parent
    until the kill arrives — that is the realistic shape of a user's
    pytest-runner spawning worker processes, and is the case where the
    old ``Popen.kill`` would leak grandchildren on Windows.

    The parent then sleeps for a long time so the timeout from the
    test side, not natural exit, is what triggers the kill.
    """
    hp = str(heartbeat_path).replace("\\", "\\\\")
    return (
        "import subprocess, sys, time\n"
        "grandchild = [sys.executable, '-c', "
        + repr(
            "import time\n"
            "from pathlib import Path\n"
            f"hp = Path(r{hp!r})\n"
            "while True:\n"
            "    hp.touch()\n"
            "    time.sleep(0.05)\n"
        )
        + "]\n"
        "subprocess.Popen(grandchild)\n"
        "time.sleep(120)\n"
    )


def _wait_heartbeat_plateau(
    heartbeat_path: Path, observation_seconds: float
) -> bool:
    """Return True iff heartbeat mtime stops being updated.

    We sample mtime once, sleep ``observation_seconds``, sample
    again. If the second sample equals the first, the grandchild is
    no longer touching the file — i.e. the kill propagated. If the
    file is missing on either sample we also count that as "no
    heartbeat" (the grandchild may have died before being able to
    create it, which is still the desired outcome).
    """
    if not heartbeat_path.exists():
        return True
    first = heartbeat_path.stat().st_mtime_ns
    time.sleep(observation_seconds)
    if not heartbeat_path.exists():
        return True
    second = heartbeat_path.stat().st_mtime_ns
    return second == first


def _wait_heartbeat_started(heartbeat_path: Path, deadline_seconds: float) -> bool:
    """Block until the heartbeat file first appears, returning True on success."""
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        if heartbeat_path.exists():
            return True
        time.sleep(0.05)
    return False


@pytest.mark.skipif(
    os.name != "posix",
    reason=(
        "POSIX-only: validates os.setsid + killpg covers grandchildren. "
        "Windows path is exercised by the Job Object test below "
        "(currently xfail until Step 3.1b-3)."
    ),
)
def test_posix_kill_reaches_grandchildren(tmp_path: Path) -> None:
    """Step 3.1b-2: kill on timeout must terminate descendants too."""
    token = uuid.uuid4().hex
    heartbeat = tmp_path / f"child-alive-{token}.txt"
    parent_src = _parent_script_source(heartbeat)

    result = _run_subprocess(
        argv=[sys.executable, "-c", parent_src],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=1.0,
    )

    assert result.timed_out, (
        "expected the 1 s timeout to fire before the parent's 120 s sleep "
        f"completes, got timed_out=False with returncode={result.returncode}"
    )

    # If the grandchild never started, the test cannot prove kill reach.
    # Sleep a tiny bit so a slow CI fork still creates the file.
    assert _wait_heartbeat_started(heartbeat, deadline_seconds=3.0), (
        f"grandchild never created heartbeat file {heartbeat} — the test "
        "cannot distinguish 'kill propagated' from 'never started'."
    )

    assert _wait_heartbeat_plateau(heartbeat, _HEARTBEAT_PAUSE_SECONDS), (
        f"heartbeat at {heartbeat} kept being updated after kill — the "
        "grandchild process leaked past the POSIX killpg path."
    )


@pytest.mark.xfail(
    os.name == "nt",
    reason=(
        "Step 3.1b-2 only addresses POSIX. Windows grandchildren leak "
        "until Step 3.1b-3 swaps Popen.kill for a Job Object kill."
    ),
    strict=False,
)
@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows-only mirror of the POSIX kill test.",
)
def test_windows_kill_reaches_grandchildren(tmp_path: Path) -> None:
    """Step 3.1b-3 placeholder: same shape as POSIX, expected to fail now."""
    token = uuid.uuid4().hex
    heartbeat = tmp_path / f"child-alive-{token}.txt"
    parent_src = _parent_script_source(heartbeat)

    result = _run_subprocess(
        argv=[sys.executable, "-c", parent_src],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=1.0,
    )

    assert result.timed_out

    assert _wait_heartbeat_started(heartbeat, deadline_seconds=3.0)
    assert _wait_heartbeat_plateau(heartbeat, _HEARTBEAT_PAUSE_SECONDS)


def test_timeout_constant_unchanged() -> None:
    """Sanity: the public default timeout is still 60 s."""
    assert _COMMAND_DEFAULT_TIMEOUT_SECONDS == 60
