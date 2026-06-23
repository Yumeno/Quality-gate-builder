"""Step 3.1d: Windows ``.bat`` / ``.cmd`` argument escaping.

Two layers of tests:

1. Unit tests on the escapers themselves
   (:func:`qgb.core._win_bat_escape.escape_cmd_metacharacters`,
   :func:`escape_argv_for_msvcrt`,
   :func:`apply_bat_escaping`,
   :func:`needs_bat_escaping`). These run on every platform — the
   escapers are pure-Python string transforms.

2. End-to-end fixture test (Windows only): a real ``echo_args.bat``
   file is written into ``tmp_path``, invoked through
   :func:`qgb.core.command._run_subprocess`, and the stdout is
   parsed back into a list of strings to confirm each argument
   reached the .bat **literally** — no metacharacter expansion, no
   command splitting.

The end-to-end test is the one that would have caught the original
Codex指摘 (Step 7 item 8): without escaping, an argv item ``"a & b"``
in a .bat invocation runs a second command. The unit tests pin the
transform algorithm so future refactors of the escapers cannot
silently regress the contract.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from qgb.core._win_bat_escape import (
    apply_bat_escaping,
    build_command_line,
    escape_argv_for_msvcrt,
    escape_cmd_metacharacters,
    needs_bat_escaping,
)

# ---- unit: needs_bat_escaping --------------------------------------------


def test_needs_bat_escaping_skips_posix() -> None:
    """POSIX never needs .bat escaping (no cmd.exe layer to worry about)."""
    if os.name == "nt":
        pytest.skip("POSIX-only — Windows-side detection is tested below")
    assert needs_bat_escaping(["script.bat", "x"]) is False
    assert needs_bat_escaping(["script.cmd", "x"]) is False


@pytest.mark.skipif(os.name != "nt", reason="Windows-only detection.")
def test_needs_bat_escaping_detects_bat_and_cmd() -> None:
    assert needs_bat_escaping(["run.bat", "arg"]) is True
    assert needs_bat_escaping(["run.cmd", "arg"]) is True
    assert needs_bat_escaping(["RUN.BAT", "arg"]) is True
    assert needs_bat_escaping([r"C:\path\to\run.bat"]) is True


@pytest.mark.skipif(os.name != "nt", reason="Windows-only detection.")
def test_needs_bat_escaping_ignores_other_targets() -> None:
    assert needs_bat_escaping(["python.exe", "-c", "print()"]) is False
    assert needs_bat_escaping(["tool"]) is False  # no extension
    assert needs_bat_escaping(["script.ps1"]) is False  # PowerShell, scope-out
    assert needs_bat_escaping([]) is False


# ---- unit: escape_cmd_metacharacters -------------------------------------


def test_escape_cmd_metacharacters_pass_through() -> None:
    """Plain text and quotes are untouched (quotes are MSVCRT layer)."""
    assert escape_cmd_metacharacters("hello") == "hello"
    assert escape_cmd_metacharacters("hello world") == "hello world"
    assert escape_cmd_metacharacters('"quoted"') == '"quoted"'
    assert escape_cmd_metacharacters("") == ""


def test_escape_cmd_metacharacters_escapes_each_metachar() -> None:
    assert escape_cmd_metacharacters("a&b") == "a^&b"
    assert escape_cmd_metacharacters("a|b") == "a^|b"
    assert escape_cmd_metacharacters("a<b") == "a^<b"
    assert escape_cmd_metacharacters("a>b") == "a^>b"
    assert escape_cmd_metacharacters("a(b)") == "a^(b^)"
    assert escape_cmd_metacharacters("%PATH%") == "^%PATH^%"


def test_escape_cmd_metacharacters_doubles_carat() -> None:
    """``^`` must double-escape so a literal carat survives cmd.exe."""
    assert escape_cmd_metacharacters("a^b") == "a^^b"


def test_escape_cmd_metacharacters_combinations() -> None:
    """Multiple metacharacters in one argument."""
    assert escape_cmd_metacharacters("a & b | c") == "a ^& b ^| c"
    assert escape_cmd_metacharacters("%FOO% > %BAR%") == "^%FOO^% ^> ^%BAR^%"


# ---- unit: escape_argv_for_msvcrt (reference impl) -----------------------


def test_escape_argv_for_msvcrt_plain() -> None:
    assert escape_argv_for_msvcrt("hello") == "hello"


def test_escape_argv_for_msvcrt_empty() -> None:
    assert escape_argv_for_msvcrt("") == '""'


def test_escape_argv_for_msvcrt_spaces() -> None:
    assert escape_argv_for_msvcrt("hello world") == '"hello world"'


def test_escape_argv_for_msvcrt_quotes_on_cmd_metachar() -> None:
    """Step 3.1d extension: cmd.exe metacharacters force quoting too.

    Pure ``list2cmdline`` only quotes on whitespace/``"``. We extend
    to ``& | < > ( ) % ^`` because cmd.exe ignores metacharacters
    inside quoted regions — that is the .bat shield.
    """
    assert escape_argv_for_msvcrt("a&b") == '"a&b"'
    assert escape_argv_for_msvcrt("%PATH%") == '"%PATH%"'
    assert escape_argv_for_msvcrt("(group)") == '"(group)"'
    assert escape_argv_for_msvcrt(">redirect") == '">redirect"'


def test_escape_argv_for_msvcrt_quote_inside() -> None:
    # ``a"b`` -> a\"b, then wrapped because the quote forces quoting.
    assert escape_argv_for_msvcrt('a"b') == '"a\\"b"'


def test_escape_argv_for_msvcrt_trailing_backslash_unquoted() -> None:
    assert escape_argv_for_msvcrt("a\\") == "a\\"


def test_escape_argv_for_msvcrt_trailing_backslash_quoted() -> None:
    """Inside quotes the trailing backslash must double, per CRT rules."""
    assert escape_argv_for_msvcrt("a b\\") == '"a b\\\\"'


def test_escape_argv_for_msvcrt_backslash_before_quote() -> None:
    """Each ``\\`` doubles when followed by a ``"``."""
    assert escape_argv_for_msvcrt('a\\"b') == '"a\\\\\\"b"'


# ---- unit: apply_bat_escaping --------------------------------------------


def test_apply_bat_escaping_leaves_argv0() -> None:
    """argv[0] is the script path; escaping must not touch it."""
    out = apply_bat_escaping(["run.bat", "a & b"])
    assert out[0] == "run.bat"


def test_apply_bat_escaping_escapes_remaining_args() -> None:
    """Each non-argv-0 item runs through carat + MSVCRT quoting.

    The carat pass ``^&`` prevents cmd.exe metacharacter scanning
    from interpreting ``&`` even inside the surrounding quotes; the
    MSVCRT quote wrap then makes the whole token survive argv
    splitting. Both layers are necessary for ``.bat`` invocation
    (see qgb.core._win_bat_escape module docstring).
    """
    out = apply_bat_escaping(["run.bat", "a & b", "%PATH%"])
    assert out == ["run.bat", '"a ^& b"', '"^%PATH^%"']


def test_apply_bat_escaping_empty_input() -> None:
    assert apply_bat_escaping([]) == []


# ---- unit: build_command_line --------------------------------------------


def test_build_command_line_plain_args() -> None:
    """Plain alphanumeric args do not need quoting."""
    assert build_command_line(["run.bat", "alpha", "beta"]) == "run.bat alpha beta"


def test_build_command_line_metachar_arg_is_quoted_and_carated() -> None:
    """A metacharacter forces both carat-prefixing and MSVCRT quoting.

    Quoting alone is not enough: cmd.exe's metacharacter scan when
    the target is a ``.bat`` runs **across** quote boundaries, so we
    need ``^&`` to neutralise the metacharacter at scan time. The
    quotes then keep the carat-prefixed text from being argv-split.
    """
    cl = build_command_line(["run.bat", "a & b"])
    assert cl == 'run.bat "a ^& b"'


def test_build_command_line_empty_arg_is_quoted_pair() -> None:
    assert build_command_line(["run.bat", ""]) == 'run.bat ""'


def test_build_command_line_no_tail() -> None:
    assert build_command_line(["run.bat"]) == "run.bat"


def test_build_command_line_empty_argv() -> None:
    assert build_command_line([]) == ""


def test_build_command_line_head_with_spaces_is_quoted() -> None:
    """補修 #4 回帰防止: argv[0] (script path) にスペースがあれば quote.

    旧実装は head を unquoted で結合していたため、
    ``C:\\Program Files\\MyTool\\run.bat`` のような path で argv 分割が
    起き、CreateProcessW が ``C:\\Program`` を実行ファイル扱いして
    別 .exe が起動される脆弱性があった。head にも MSVCRT quoting
    を適用することで、Windows 標準インストール先のパスでも安全に
    動作する。
    """
    cl = build_command_line([r"C:\Program Files\MyTool\run.bat"])
    assert cl == '"C:\\Program Files\\MyTool\\run.bat"'


def test_build_command_line_head_with_spaces_and_tail() -> None:
    """補修 #4 回帰防止: head にスペース + tail も同時にあるケース."""
    cl = build_command_line(
        [r"C:\Program Files\x\run.bat", "alpha", "beta with space"]
    )
    assert cl == '"C:\\Program Files\\x\\run.bat" alpha "beta with space"'


def test_build_command_line_head_without_spaces_unchanged() -> None:
    """head にスペース・metachar が無ければ MSVCRT quoting は no-op."""
    assert build_command_line(["run.bat", "arg"]) == "run.bat arg"


# ---- end-to-end: real .bat fixture (Windows only) ------------------------


_BAT_ECHO_SCRIPT = """@echo off
setlocal disabledelayedexpansion
set i=0
:loop
if "%~1"=="" goto :done
set /a i+=1
echo argv[%i%]=%~1
shift
goto :loop
:done
"""


@pytest.mark.skipif(
    os.name != "nt",
    reason="End-to-end .bat fixture is Windows-only; POSIX has no cmd.exe.",
)
def test_bat_fixture_receives_literal_arguments(tmp_path: Path) -> None:
    """Run a .bat with metacharacter-rich argv; assert each arrives literally.

    Without Step 3.1d escaping this test would fail in interesting
    ways: ``a & b`` would split into two commands (the second running
    ``b`` as a program → ``'b' is not recognized``); ``%PATH%`` would
    be expanded to the host PATH; etc.

    The fixture .bat echoes each ``%~1`` (positional arg with surrounding
    quotes stripped) on its own line. We parse the stdout to recover
    the per-argument values and compare to what we sent.
    """
    # Importing _run_subprocess here (rather than at module top) keeps
    # the unit-test portion of this file POSIX-safe — the module-level
    # import block stays free of qgb.core.command's Windows-only side
    # imports.
    from qgb.core.command import _run_subprocess

    bat = tmp_path / "echo_args.bat"
    bat.write_text(_BAT_ECHO_SCRIPT, encoding="ascii")

    payload = [
        "plain",
        "with spaces",
        "a & b",       # cmd separator
        "c | d",       # pipe
        "%PATH%",      # expansion
        ">redirect",   # output redirect
        "(group)",     # parens
        "literal^carat",
    ]

    result = _run_subprocess(
        argv=[str(bat), *payload],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=15.0,
    )

    assert not result.timed_out, (
        f"echo_args.bat hung — stderr={result.stderr!r}"
    )
    assert result.returncode == 0, (
        f"echo_args.bat exited with {result.returncode}; "
        f"stdout={result.stdout!r}, stderr={result.stderr!r}"
    )

    # Parse ``argv[N]=value`` lines into ``[value, ...]`` in order.
    received: list[str] = []
    for line in result.stdout.splitlines():
        if "=" not in line or not line.startswith("argv["):
            continue
        received.append(line.split("=", 1)[1])

    assert received == payload, (
        "argument round-trip mismatch; metacharacter escape failed.\n"
        f"  sent:     {payload}\n"
        f"  received: {received}\n"
        f"  stdout: {result.stdout!r}"
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="End-to-end .bat fixture is Windows-only; POSIX has no cmd.exe.",
)
def test_bat_fixture_no_command_injection(tmp_path: Path) -> None:
    """Confirm an injection-shaped argument does not execute a second command.

    If escaping silently regressed, ``"foo & whoami"`` would split at
    ``&`` and run ``whoami`` as a follow-up command (potentially
    leaking the CI user). With Step 3.1d in place the ``&`` is
    ``^&``-escaped and the .bat sees the literal string.
    """
    from qgb.core.command import _run_subprocess

    bat = tmp_path / "echo_args.bat"
    bat.write_text(_BAT_ECHO_SCRIPT, encoding="ascii")

    result = _run_subprocess(
        argv=[str(bat), "foo & whoami"],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=15.0,
    )

    assert not result.timed_out
    assert result.returncode == 0
    # We expect exactly one argv echo line.
    lines = [
        line for line in result.stdout.splitlines()
        if line.startswith("argv[")
    ]
    assert lines == ["argv[1]=foo & whoami"], (
        "command injection slipped past .bat escaping; "
        f"stdout: {result.stdout!r}"
    )


@pytest.mark.skipif(
    os.name != "nt",
    reason="End-to-end .bat fixture is Windows-only; POSIX has no cmd.exe.",
)
def test_bat_fixture_runs_from_path_with_spaces(tmp_path: Path) -> None:
    """補修 #4 回帰防止: スペースを含む script path でも正しく起動できる.

    旧実装は build_command_line が head (argv[0]) を unquoted で結合
    していたため、``C:\\Program Files\\...\\run.bat`` のような Windows
    標準インストール先パスを指定すると、CreateProcessW が argv[0] を
    ``C:\\Program`` と解釈し、別の実行ファイルを起動する脆弱性が
    あった。head にも MSVCRT quoting を適用する補修 #4 により、
    スペース入りパスでも安全に動作する。

    本テストは fixture script を **意図的にスペース入りディレクトリ**
    に置き、qgb から正常起動 + 引数 round-trip を end-to-end で検証。
    """
    from qgb.core.command import _run_subprocess

    nested_dir = tmp_path / "dir with spaces"
    nested_dir.mkdir()
    bat = nested_dir / "echo args.bat"
    bat.write_text(_BAT_ECHO_SCRIPT, encoding="ascii")

    payload = ["alpha", "beta with space", "gamma & delta"]

    result = _run_subprocess(
        argv=[str(bat), *payload],
        cwd=str(tmp_path),
        env=os.environ.copy(),
        timeout_seconds=15.0,
    )

    assert not result.timed_out, (
        f"script in spaced path hung — stderr={result.stderr!r}"
    )
    assert result.returncode == 0, (
        f"script in spaced path failed to start (returncode="
        f"{result.returncode}); stdout={result.stdout!r}, "
        f"stderr={result.stderr!r}. This is the 補修 #4 regression "
        "signal: head was probably built unquoted."
    )

    received: list[str] = []
    for line in result.stdout.splitlines():
        if "=" not in line or not line.startswith("argv["):
            continue
        received.append(line.split("=", 1)[1])
    assert received == payload, (
        "args did not round-trip from spaced path; "
        f"sent={payload}, received={received}, stdout={result.stdout!r}"
    )


# ---- sanity: POSIX path is a no-op --------------------------------------


@pytest.mark.skipif(os.name == "nt", reason="POSIX-only no-op assertion.")
def test_apply_bat_escaping_noop_on_posix(tmp_path: Path) -> None:
    """needs_bat_escaping returns False on POSIX; apply is unused.

    We still assert apply_bat_escaping itself behaves consistently
    (idempotent on already-clean argv) so cross-platform callers
    that bypass needs_bat_escaping don't crash on POSIX.
    """
    argv = ["./script.sh", "a & b", "%PATH%"]
    assert needs_bat_escaping(argv) is False
    # apply_bat_escaping is platform-agnostic by design; calling it
    # is safe even when needs_bat_escaping says no.
    out = apply_bat_escaping(argv)
    assert out[0] == "./script.sh"
    # Even on POSIX the string transform itself works the same way,
    # so we can pin the algorithm here too.
    assert out == ["./script.sh", '"a ^& b"', '"^%PATH^%"']
