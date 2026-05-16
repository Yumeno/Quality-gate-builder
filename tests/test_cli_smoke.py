"""Smoke tests for the CLI surface introduced in Step 0."""

from __future__ import annotations

import pytest

from qgb import __version__
from qgb.cli import build_parser, main


def test_help_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "qgb" in captured.out
    assert "quality-gate-builder" in captured.out


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out


def test_main_without_args_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "usage" in captured.out.lower() or "qgb" in captured.out


def test_main_with_unimplemented_subcommand_returns_usage_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = main(["init"])
    captured = capsys.readouterr()
    assert exit_code == 64  # EX_USAGE: subcommand exists but not yet implemented
    assert "not implemented" in captured.err.lower()
