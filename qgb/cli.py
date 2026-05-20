"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from qgb import __version__
from qgb.core.validate import ValidateReport, run_validate

EXIT_OK = 0
EXIT_DENY = 1
EXIT_NOT_READY = 2
EXIT_USAGE = 64  # BSD sysexits EX_USAGE. See requirements doc §6.2.3.
# Phase 1 transitional: stub handlers for not-yet-implemented subcommands also
# return EXIT_USAGE so callers can distinguish CLI-level problems from gate
# decisions (ALLOW=0, DENY=1) and from NOT_READY=2. Once every subcommand is
# implemented, this overload disappears and EXIT_USAGE is reserved for genuine
# argparse usage errors.


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
        f"qgb {command}: command is not implemented yet in this Phase 1 build.",
        file=sys.stderr,
    )
    return EXIT_USAGE


def _handle_not_implemented(args: argparse.Namespace) -> int:
    return _not_implemented(args.command)


# ---- validate ------------------------------------------------------------


def _print_validate_text(report: ValidateReport, stream) -> None:
    if not report.files_checked:
        print("No .quality-system/ files were found to validate.", file=stream)
        return

    print(f"Checked {len(report.files_checked)} file(s):", file=stream)
    for path, schema_name in report.files_checked:
        print(f"  - {path} (schema: {schema_name})", file=stream)

    if not report.has_problems():
        print("OK: all JSON sources of truth are valid.", file=stream)
        return

    if report.read_errors:
        print("", file=stream)
        print(f"Read errors ({len(report.read_errors)}):", file=stream)
        for path, message in report.read_errors:
            print(f"  - {path}: {message}", file=stream)

    if report.schema_issues:
        print("", file=stream)
        print(f"Schema violations ({len(report.schema_issues)}):", file=stream)
        for fi in report.schema_issues:
            print(
                f"  - {fi.file} [{fi.schema_name}] "
                f"{fi.issue.path or '/'}: {fi.issue.message}",
                file=stream,
            )

    if report.field_mismatches:
        print("", file=stream)
        print(
            f"Contract field mismatches ({len(report.field_mismatches)}):",
            file=stream,
        )
        for fm in report.field_mismatches:
            print(f"  - {fm.as_message()}", file=stream)


def _report_to_json(report: ValidateReport) -> dict[str, object]:
    return {
        "files_checked": [
            {"path": str(p), "schema": s} for p, s in report.files_checked
        ],
        "schema_issues": [
            {
                "file": str(fi.file),
                "schema": fi.schema_name,
                "path": fi.issue.path,
                "schema_path": fi.issue.schema_path,
                "message": fi.issue.message,
            }
            for fi in report.schema_issues
        ],
        "field_mismatches": [
            {
                "file": str(fm.file),
                "verification_type": fm.verification_type,
                "field": fm.field_name,
            }
            for fm in report.field_mismatches
        ],
        "read_errors": [
            {"file": str(p), "message": msg} for p, msg in report.read_errors
        ],
        "summary": {
            "files": len(report.files_checked),
            "schema_issues": len(report.schema_issues),
            "field_mismatches": len(report.field_mismatches),
            "read_errors": len(report.read_errors),
        },
    }


def _handle_validate(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb validate: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE

    report = run_validate(root)

    if args.json:
        json.dump(_report_to_json(report), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        _print_validate_text(report, sys.stdout if not report.has_problems() else sys.stderr)

    return EXIT_NOT_READY if report.has_problems() else EXIT_OK


# ---- parser --------------------------------------------------------------


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

    # Phase 1 commands. Handlers are wired in incrementally; not-yet-implemented
    # commands share a single stub handler that returns EXIT_USAGE.
    stub_commands: tuple[tuple[str, str], ...] = (
        ("init", "(not yet implemented) initialize .quality-system/ in the target project"),
        ("detect", "(not yet implemented) detect target language and framework"),
        ("design-stages", "(not yet implemented) propose verification stages for the target"),
        ("scaffold", "(not yet implemented) scaffold a new REQ"),
        ("validate-policy", "(not yet implemented) validate stage design quality"),
        ("verify", "(not yet implemented) run lightweight checks (volatile artifacts only)"),
        ("run", "(not yet implemented) run the gate and update curated evidence"),
    )
    for name, help_text in stub_commands:
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(handler=_handle_not_implemented)

    # validate: real handler (Step 2).
    validate_p = subparsers.add_parser(
        "validate",
        help="validate JSON sources of truth under .quality-system/",
        description=(
            "Validate config.json, policy.json, REQ meta JSON, and contract JSON "
            "files against the bundled schemas. Returns 0 on success, "
            "2 (NOT_READY) on any violation, 64 on usage errors."
        ),
    )
    validate_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    validate_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    validate_p.set_defaults(handler=_handle_validate)

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
