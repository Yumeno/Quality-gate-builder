"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from qgb import __version__

EXIT_OK = 0
EXIT_DENY = 1
EXIT_NOT_READY = 2
EXIT_USAGE = 64  # BSD sysexits EX_USAGE; also used for not-yet-implemented subcommands


class QgbArgumentParser(argparse.ArgumentParser):
    """argparse parser that exits with EXIT_USAGE (64) instead of 2 on errors.

    The default argparse behaviour exits with code 2 on usage errors, which
    collides with qgb's NOT_READY semantics (also exit code 2). NOT_READY is
    reserved for the runtime preflight phase (see requirements doc §6.2.3).
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _not_implemented(command: str) -> int:
    print(
        f"qgb {command}: command is not implemented yet (Phase 1, Step 0).",
        file=sys.stderr,
    )
    return EXIT_USAGE


def _handle_not_implemented(args: argparse.Namespace) -> int:
    return _not_implemented(args.command)


def build_parser() -> QgbArgumentParser:
    parser = QgbArgumentParser(
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

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        parser_class=QgbArgumentParser,
    )

    # Phase 1 commands. Handlers are wired in later steps; for Step 0 each
    # subparser shares the same "not yet implemented" handler.
    for name, help_text in (
        ("init", "(not yet implemented) initialize .quality-system/ in the target project"),
        ("detect", "(not yet implemented) detect target language and framework"),
        ("design-stages", "(not yet implemented) propose verification stages for the target"),
        ("scaffold", "(not yet implemented) scaffold a new REQ"),
        ("validate", "(not yet implemented) validate JSON sources of truth"),
        ("validate-policy", "(not yet implemented) validate stage design quality"),
        ("verify", "(not yet implemented) run lightweight checks (volatile artifacts only)"),
        ("run", "(not yet implemented) run the gate and update curated evidence"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(handler=_handle_not_implemented)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.handler is None:
        parser.print_help()
        return EXIT_OK

    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
