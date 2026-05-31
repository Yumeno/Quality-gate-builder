"""Tests exercised by the qgb quality-gate stage S1 (pytest)."""

from __future__ import annotations

from demo_cli.main import greet, main


def test_greet_returns_message() -> None:
    assert greet("world") == "hello, world!"


def test_greet_with_custom_name() -> None:
    assert greet("qgb") == "hello, qgb!"


def test_main_with_no_args_returns_zero() -> None:
    assert main([]) == 0


def test_main_greet_subcommand() -> None:
    assert main(["greet", "--name", "demo"]) == 0
