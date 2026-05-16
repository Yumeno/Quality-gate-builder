"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import sys

from qgb import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qgb",
        description=(
            "quality-gate-builder: generate trace-based quality gates "
            "for arbitrary target projects."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"qgb {__version__}",
    )
    parser.set_defaults(handler=None)

    subparsers = parser.add_subparsers(dest="command", metavar="<command>")

    # Subcommands are wired up in later steps. For Step 0 the parser only
    # needs to support --help and --version.
    subparsers.add_parser(
        "init",
        help="(not yet implemented) initialize .quality-system/ in the target project",
    )
    subparsers.add_parser(
        "detect",
        help="(not yet implemented) detect target language and framework",
    )
    subparsers.add_parser(
        "design-stages",
        help="(not yet implemented) propose verification stages for the target",
    )
    subparsers.add_parser(
        "scaffold",
        help="(not yet implemented) scaffold a new REQ",
    )
    subparsers.add_parser(
        "validate",
        help="(not yet implemented) validate JSON sources of truth",
    )
    subparsers.add_parser(
        "validate-policy",
        help="(not yet implemented) validate stage design quality",
    )
    subparsers.add_parser(
        "verify",
        help="(not yet implemented) run lightweight checks (volatile artifacts only)",
    )
    subparsers.add_parser(
        "run",
        help="(not yet implemented) run the gate and update curated evidence",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    # Subcommand dispatch will be added incrementally in later Steps.
    print(
        f"qgb {args.command}: command is not implemented yet (Phase 1, Step 0).",
        file=sys.stderr,
    )
    return 64  # EX_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
