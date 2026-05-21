"""Smoke tests for the CLI surface introduced in Step 0."""

from __future__ import annotations

import subprocess
import sys

import pytest

from qgb import __version__
from qgb.cli import EXIT_OK, EXIT_USAGE, build_parser, main


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--help"])
    assert excinfo.value.code == EXIT_OK
    captured = capsys.readouterr()
    assert "usage:" in captured.out.lower()
    assert "qgb" in captured.out
    # Subcommands should be listed in --help output.
    assert "init" in captured.out
    assert "run" in captured.out


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])
    assert excinfo.value.code == EXIT_OK
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_main_without_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "usage:" in captured.out.lower()
    assert "init" in captured.out
    assert "run" in captured.out


def test_main_with_unimplemented_subcommand_returns_usage_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # `detect` is still a stub in Step 3; it shares the not-yet-implemented handler.
    exit_code = main(["detect"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE
    assert "not implemented" in captured.err.lower()


def test_unknown_subcommand_exits_with_usage_code() -> None:
    """argparse usage errors must exit 64, not 2 (which collides with NOT_READY)."""
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["definitely-not-a-command"])
    assert excinfo.value.code == EXIT_USAGE


def test_unknown_top_level_flag_exits_with_usage_code() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--no-such-flag"])
    assert excinfo.value.code == EXIT_USAGE


# --- subprocess smoke tests: verify the actual `python -m qgb` entry point ---


def _run_qgb(*args: str) -> subprocess.CompletedProcess[str]:
    """Spawn `python -m qgb ...` with UTF-8 forced on both ends.

    Windows defaults to the active code page (e.g. CP932) for console I/O, so
    the child process can produce bytes the parent's UTF-8 reader thread
    cannot decode. ``PYTHONIOENCODING=utf-8`` and ``PYTHONUTF8=1`` make the
    child use UTF-8 unconditionally.
    """
    import os

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "qgb", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_subprocess_help() -> None:
    result = _run_qgb("--help")
    assert result.returncode == EXIT_OK
    assert "usage:" in result.stdout.lower()
    assert "init" in result.stdout
    assert "run" in result.stdout


def test_subprocess_version() -> None:
    result = _run_qgb("--version")
    assert result.returncode == EXIT_OK
    assert __version__ in result.stdout


def test_subprocess_no_args_prints_help() -> None:
    result = _run_qgb()
    assert result.returncode == EXIT_OK
    assert "usage:" in result.stdout.lower()


def test_subprocess_unknown_command_exits_64() -> None:
    result = _run_qgb("definitely-not-a-command")
    assert result.returncode == EXIT_USAGE
    # argparse error message goes to stderr.
    assert "error" in result.stderr.lower()


def test_subprocess_unimplemented_subcommand_exits_64() -> None:
    # Use a stub subcommand (Step 3 has wired init/validate to real handlers).
    result = _run_qgb("detect")
    assert result.returncode == EXIT_USAGE
    assert "not implemented" in result.stderr.lower()
