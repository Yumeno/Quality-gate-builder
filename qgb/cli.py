"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from qgb import __version__
from qgb.core.init import InitReport, run_init
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
        for re in report.read_errors:
            print(f"  - {re.file}: {re.message}", file=stream)

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
        "ok": not report.has_problems(),
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
                "owning_verification_type": fm.owning_verification_type,
            }
            for fm in report.field_mismatches
        ],
        "read_errors": [
            {"file": str(re.file), "message": re.message} for re in report.read_errors
        ],
        "summary": {
            "ok": not report.has_problems(),
            "files": len(report.files_checked),
            "schema_issues": len(report.schema_issues),
            "field_mismatches": len(report.field_mismatches),
            "read_errors": len(report.read_errors),
            "total_problems": report.total_problems(),
        },
    }


def _handle_validate(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb validate: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb validate: --path must point at a project directory, not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    report = run_validate(root)

    if args.json:
        json.dump(_report_to_json(report), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        _print_validate_text(report, sys.stdout if not report.has_problems() else sys.stderr)

    return EXIT_NOT_READY if report.has_problems() else EXIT_OK


# ---- init ----------------------------------------------------------------


def _print_init_text(report: InitReport, stream) -> None:
    if report.has_problems():
        print(
            f"qgb init: refused to corrupt existing tree at {report.project_root}",
            file=stream,
        )
    else:
        print(f"Initialised .quality-system/ at {report.project_root}", file=stream)
    if report.dirs_ensured:
        print(f"  Ensured {len(report.dirs_ensured)} directories.", file=stream)
    for outcome in report.file_outcomes:
        marker = {
            "created": "+",
            "overwritten": "*",
            "skipped": "-",
        }.get(outcome.action, "?")
        note = f" ({outcome.note})" if outcome.note else ""
        print(f"  {marker} {outcome.action:11s} {outcome.path}{note}", file=stream)
    if report.gitignore_action is not None:
        print(f"  .gitignore: {report.gitignore_action}", file=stream)
    if report.errors:
        print("", file=stream)
        print(f"Initialisation errors ({len(report.errors)}):", file=stream)
        for err in report.errors:
            print(f"  - [{err.kind}] {err.message}", file=stream)


def _init_report_to_json(report: InitReport) -> dict[str, object]:
    return {
        "ok": not report.has_problems(),
        "project_root": str(report.project_root),
        "dirs_ensured": [str(p) for p in report.dirs_ensured],
        "files": [
            {"path": str(o.path), "action": o.action, "note": o.note}
            for o in report.file_outcomes
        ],
        "gitignore_action": report.gitignore_action,
        "errors": [
            {"kind": e.kind, "path": str(e.path), "message": e.message}
            for e in report.errors
        ],
        "summary": {
            "ok": not report.has_problems(),
            "dirs_ensured": len(report.dirs_ensured),
            "files": len(report.file_outcomes),
            "errors": len(report.errors),
        },
    }


def _handle_init(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb init: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb init: --path must point at a project directory, not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    report = run_init(root, project_name=args.name, force=args.force)

    if args.json:
        json.dump(_init_report_to_json(report), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        _print_init_text(
            report,
            sys.stdout if not report.has_problems() else sys.stderr,
        )

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

    # init: real handler (Step 3).
    init_p = subparsers.add_parser(
        "init",
        help="initialise .quality-system/ in the target project",
        description=(
            "Create the canonical .quality-system/ directory layout, write minimal "
            "config.json and policy.json (stages: []), seed knowledge/, and append "
            ".quality-system/artifacts/ to .gitignore. Idempotent: existing files "
            "are skipped unless --force is passed. Subsequent steps "
            "(qgb design-stages, qgb scaffold) populate the policy and REQ files."
        ),
    )
    init_p.add_argument(
        "--path",
        default=".",
        help="Project root in which to create .quality-system/ (default: current directory)",
    )
    init_p.add_argument(
        "--name",
        default=None,
        help="Override the project name written into config.json (default: basename of --path)",
    )
    init_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite existing .quality-system/ files (config.json, policy.json, "
            "knowledge/knowledge.jsonl, knowledge/project-context.md) instead of "
            "skipping them. Path-type collisions (file where a directory is "
            "expected, etc.) are NOT bypassed by --force; they still cause "
            "NOT_READY (exit 2)."
        ),
    )
    init_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    init_p.set_defaults(handler=_handle_init)

    # validate: real handler (Step 2).
    validate_p = subparsers.add_parser(
        "validate",
        help="validate existing spec JSON files under .quality-system/",
        description=(
            "Validate each existing JSON spec file under .quality-system/ "
            "(config.json, policy.json, REQ meta, contract JSON) against the "
            "bundled schemas, and reject contract field mismatches per "
            "requirements doc section F-005. "
            "Out of scope: cross-file integrity (contract_ref / stage_id / DAG), "
            "missing top-level files, and tree-shape problems. Those are "
            "handled by 'qgb validate-policy' and 'qgb run' preflight. "
            "Returns 0 on success, 2 (NOT_READY) on any violation, "
            "64 on usage errors."
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
