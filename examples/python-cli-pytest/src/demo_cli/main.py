"""Minimal CLI used as the qgb quality-gate target for this example.

The CLI exposes a single ``greet`` subcommand. Its purpose in this
example is to give the quality-gate something concrete to verify:

* S1 (pytest) runs the unit tests in ``tests/`` and expects exit 0.
* S2 (`python -m demo_cli --help`) confirms the CLI surface starts
  cleanly and prints help.
* S3 (substring_match) confirms the README documents the install step.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="demo_cli",
        description="Minimal demo CLI used by examples/python-cli-pytest.",
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    greet = sub.add_parser("greet", help="print a greeting")
    greet.add_argument(
        "--name", default="world", help="who to greet (default: world)"
    )

    return parser


def greet(name: str) -> str:
    return f"hello, {name}!"


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "greet":
        print(greet(args.name))
        return 0
    parser.print_help(sys.stderr)
    return 64
