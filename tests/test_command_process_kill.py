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

from qgb.core.command import (
    _COMMAND_DEFAULT_TIMEOUT_SECONDS,
    _COMMAND_EXECUTION_CAP_BYTES,
    _COMMAND_LOG_TAIL_CAP_BYTES,
    _CapExceededState,
    _run_subprocess,
)

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
        "Windows path is exercised by the Job Object test below."
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


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows-only: validates Job Object kill reaches grandchildren.",
)
def test_windows_kill_reaches_grandchildren(tmp_path: Path) -> None:
    """Step 3.1b-3: Job Object kill must terminate descendants too.

    Mirror of :func:`test_posix_kill_reaches_grandchildren` for the
    Windows code path. ``WindowsJob`` is set up by ``_run_subprocess``;
    on timeout, ``TerminateJobObject`` kills every assigned process —
    direct child plus grandchildren spawned after the assign.

    If this test fails on a CI runner that *does* satisfy
    :func:`qgb.core._win_job.is_supported`, that usually means qgb's
    own host process is itself running inside a Job Object that
    forbids nested jobs. The :class:`_SubprocessResult.runner_warning`
    field should be populated in that case; if so, this test will
    fail loudly because the heartbeat continues — which is the
    intended behaviour, since "grandchild leak" is exactly the
    audit-visible degradation we promised to flag.
    """
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

    assert _wait_heartbeat_started(heartbeat, deadline_seconds=3.0), (
        f"grandchild never created heartbeat file {heartbeat} — the test "
        "cannot distinguish 'kill propagated' from 'never started'."
    )

    assert _wait_heartbeat_plateau(heartbeat, _HEARTBEAT_PAUSE_SECONDS), (
        f"heartbeat at {heartbeat} kept being updated after kill — the "
        "grandchild process leaked past the Windows Job Object kill. "
        f"runner_warning={result.runner_warning!r}"
    )


def test_timeout_constant_unchanged() -> None:
    """Sanity: the public default timeout is still 60 s."""
    assert _COMMAND_DEFAULT_TIMEOUT_SECONDS == 60


def test_cap_constants_step3_1c() -> None:
    """Step 3.1c: execution cap = 16 MiB, log tail cap = 64 KiB.

    These values appear in framework-shape.md §5 and the gate.runtime
    schema reason enum; pin them so accidental edits show up as a
    regression.
    """
    assert _COMMAND_EXECUTION_CAP_BYTES == 16 * 1024 * 1024
    assert _COMMAND_LOG_TAIL_CAP_BYTES == 64 * 1024


def _cap_overflow_script(stream: str, target_bytes: int) -> str:
    """Source for a Python child that prints ``target_bytes`` to ``stream``.

    We write in 1 MiB chunks via ``sys.stdout.buffer.write`` /
    ``sys.stderr.buffer.write`` to bypass text-mode buffering and
    give the reader threads chunky observable progress. After the
    burst the child sleeps for a long time so the cap-driven kill —
    not natural exit — is what terminates it.
    """
    assert stream in ("stdout", "stderr")
    return (
        "import sys, time\n"
        f"stream = sys.{stream}.buffer\n"
        "chunk = b'x' * (1024 * 1024)\n"
        f"remaining = {target_bytes}\n"
        "while remaining > 0:\n"
        "    write = chunk if remaining >= len(chunk) else chunk[:remaining]\n"
        "    stream.write(write)\n"
        "    stream.flush()\n"
        "    remaining -= len(write)\n"
        "time.sleep(60)\n"
    )


def test_stdout_cap_exceeded_kills_and_reports(tmp_path: Path) -> None:
    """Step 3.1c: stdout > 16 MiB triggers tree kill with structured reason."""
    target = _COMMAND_EXECUTION_CAP_BYTES + 2 * 1024 * 1024  # 18 MiB

    result = _run_subprocess(
        argv=[sys.executable, "-c", _cap_overflow_script("stdout", target)],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=30.0,  # generous; cap should fire well before this
    )

    assert result.reason == "stdout_cap_exceeded", (
        f"expected reason=stdout_cap_exceeded, got reason={result.reason!r} "
        f"(timed_out={result.timed_out}, "
        f"stdout_len={len(result.stdout)}, stderr_len={len(result.stderr)})"
    )
    # The exact byte count after kill is non-deterministic (depends on
    # how many writes raced past the cap), but we always saw at least
    # one full cap's worth.
    assert len(result.stdout.encode("utf-8", errors="replace")) >= _COMMAND_EXECUTION_CAP_BYTES


def test_stderr_cap_exceeded_kills_and_reports(tmp_path: Path) -> None:
    """Step 3.1c: stderr > 16 MiB triggers tree kill with stderr reason."""
    target = _COMMAND_EXECUTION_CAP_BYTES + 2 * 1024 * 1024

    result = _run_subprocess(
        argv=[sys.executable, "-c", _cap_overflow_script("stderr", target)],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=30.0,
    )

    assert result.reason == "stderr_cap_exceeded", (
        f"expected reason=stderr_cap_exceeded, got reason={result.reason!r}"
    )
    assert len(result.stderr.encode("utf-8", errors="replace")) >= _COMMAND_EXECUTION_CAP_BYTES


def test_no_false_positive_timeout_when_child_exits_near_deadline(
    tmp_path: Path,
) -> None:
    """補修 #1 回帰防止: 子が deadline 直前に exit したら natural exit 扱い.

    旧 supervisor 設計 (``remaining <= 0`` を ``process.wait`` 前に判定)
    では、deadline まで残り 100 ms 未満の窓で子が exit すると、次の
    ループ先頭で ``remaining`` が負になり ``timed_out=True`` が立っ
    てしまう false-positive ステートがあった。補修 #1 で 3 状態
    直交分割 (poll → cap → deadline) にしたため、子が死んでいれば
    必ず natural exit に倒れる。本テストはこの不変条件を回帰的に守る。

    実装ノート: 子に「timeout の 90% を sleep してから exit」させる
    ことで、確率的に deadline 直前 exit を引き起こす。固定 sleep の
    値は OS scheduler の jitter を踏まえて selected。
    """
    timeout = 1.0
    sleep_target = 0.9  # timeout の 90% スリープしてから exit
    src = (
        "import time\n"
        f"time.sleep({sleep_target})\n"
        "print('done')\n"
    )

    result = _run_subprocess(
        argv=[sys.executable, "-c", src],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=timeout,
    )

    # 子は exit している = natural exit 経路
    assert result.timed_out is False, (
        "child exited normally near deadline but supervisor reported "
        f"timed_out=True (reason={result.reason!r}). The 3-state "
        "orthogonal supervisor must prefer natural exit over deadline."
    )
    assert result.reason is None, (
        f"reason should be None on natural exit, got {result.reason!r}"
    )
    assert result.returncode == 0
    assert "done" in result.stdout


def test_nominal_run_emits_no_reason(tmp_path: Path) -> None:
    """A normal exit must leave reason=None so audits aren't false-positive."""
    result = _run_subprocess(
        argv=[sys.executable, "-c", "print('hello'); print('world')"],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=5.0,
    )
    assert result.reason is None
    assert not result.timed_out
    assert result.returncode == 0


def test_timeout_emits_command_timeout_reason(tmp_path: Path) -> None:
    """Timeout path: reason=command_timeout, timed_out=True (back-compat alias)."""
    result = _run_subprocess(
        argv=[sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=1.0,
    )
    assert result.timed_out is True
    assert result.reason == "command_timeout"


@pytest.mark.skipif(
    os.name != "nt",
    reason="Windows-only sanity: nominal run produces no runner_warning.",
)
def test_windows_nominal_run_emits_no_runner_warning(tmp_path: Path) -> None:
    """Regression guard: a healthy host should never degrade to fallback.

    If this test fails on CI, the qgb host is running in an
    environment where ``WindowsJob`` cannot be created or assigned
    — typically a nested Job Object. The fallback path is by design
    (Codex 指摘: P7 証跡優先), but it should never trigger on a
    plain CI runner. A failure here is a signal that the CI
    configuration changed, not that ``command.py`` is broken.
    """
    result = _run_subprocess(
        argv=[sys.executable, "-c", "print('ok')"],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=5.0,
    )
    assert not result.timed_out
    assert result.returncode == 0
    assert result.runner_warning is None, (
        "Windows nominal run should not emit a runner_warning. "
        f"Got: {result.runner_warning!r}"
    )


# ---- _CapExceededState 単体テスト (補修 #5) ----------------------------------


def test_cap_state_initial_is_not_set() -> None:
    """補修 #5: 新規状態は未到達 (中間ステートが存在しない出発点)."""
    state = _CapExceededState()
    assert state.is_set() is False
    assert state.name is None


def test_cap_state_first_set_wins() -> None:
    """補修 #5: first-wins セマンティクスを 1 オブジェクトで保証."""
    state = _CapExceededState()
    assert state.try_set("stdout") is True
    assert state.is_set() is True
    assert state.name == "stdout"

    # 2 回目以降は False、name は変化しない
    assert state.try_set("stderr") is False
    assert state.name == "stdout"


def test_cap_state_set_atomicity_under_threads() -> None:
    """補修 #5: 並行 try_set でも name が必ず確定値、None ではない.

    旧設計 (cap_event + overflow_record[0]) はこの不変条件を GIL 依存
    で暗黙的に保っていた。_CapExceededState は Lock で明示的に保つ。

    本テストは 100 スレッドが同時に try_set("stdout") / try_set("stderr")
    を呼ぶシナリオで「is_set() が True なのに name が None」という
    中間ステートが観測されないことを assert する。
    """
    import threading as _th

    state = _CapExceededState()
    barrier = _th.Barrier(100)

    def attempt(name: str) -> None:
        barrier.wait()
        state.try_set(name)

    threads = []
    for i in range(100):
        name = "stdout" if i % 2 == 0 else "stderr"
        t = _th.Thread(target=attempt, args=(name,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    # is_set が True なら name は必ず stdout か stderr (None でない)
    assert state.is_set() is True
    assert state.name in ("stdout", "stderr"), (
        f"intermediate state observed: is_set=True but name={state.name!r}"
    )
