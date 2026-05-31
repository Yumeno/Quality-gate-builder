"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from qgb import __version__
from qgb.core import evidence as evidence_mod
from qgb.core.decision import decide
from qgb.core.evidence import write_evidence
from qgb.core.init import InitReport, run_init
from qgb.core.preflight import (
    PreflightReport,
    run_preflight,
    validate_policy_preflight,
)
from qgb.core.runner import run_stages
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


# ---- run -----------------------------------------------------------------


def _format_preflight_text(report: PreflightReport) -> str:
    lines: list[str] = []
    lines.append(f"NOT_READY: preflight rejected {len(report.issues)} issue(s).")
    for issue in report.issues:
        lines.append(f"  - [{issue.kind}] {issue.where}")
        lines.append(f"      {issue.message}")
    return "\n".join(lines) + "\n"


def _preflight_to_json(report: PreflightReport, req_id: str) -> dict[str, object]:
    return {
        "ok": False,
        "req_id": req_id,
        "status": "NOT_READY",
        "issues": [
            {"kind": i.kind, "where": i.where, "message": i.message}
            for i in report.issues
        ],
    }


def _run_result_to_json(gate: dict[str, object]) -> dict[str, object]:
    return {
        "ok": gate["status"] == "ALLOW",
        "req_id": gate["req_id"],
        "status": gate["status"],
        "failed_stage": gate["failed_stage"],
        "phase": gate["phase"],
        "gate": gate,
    }


def _print_run_text(gate: dict[str, object], stream) -> None:
    status = gate["status"]
    print(
        f"{status}: {gate['req_id']} (phase={gate['phase']})",
        file=stream,
    )
    print(f"  meaning: {gate['decision']['meaning']}", file=stream)  # type: ignore[index]
    print(f"  run_dir: {gate['paths']['run_dir']}", file=stream)  # type: ignore[index]
    print(
        f"  curated_latest_dir: {gate['paths']['curated_latest_dir']}",  # type: ignore[index]
        file=stream,
    )
    if status == "DENY":
        print(f"  failed_stage: {gate['failed_stage']}", file=stream)
    print("  stages:", file=stream)
    for stage in gate["stages"]:  # type: ignore[index]
        print(
            f"    - {stage['id']} ({stage['verification_type']}): {stage['result']}",
            file=stream,
        )


def _confirm_run(
    req_id: str, adopted_count: int, *, assume_yes: bool
) -> tuple[bool, str]:
    """Phase 1 F-008: ask for confirmation before mutating curated evidence.

    Returns ``(proceed, reason)``:

    * ``(True, "")`` — execution may continue (``--yes`` or user typed y/yes).
    * ``(False, "non_tty_without_yes")`` — stdin is not a TTY and ``--yes``
      was not given; refuses to read blindly.
    * ``(False, "declined")`` — the user typed anything other than y/yes.

    The prompt itself goes to stderr so ``--json`` keeps stdout clean; the
    caller decides whether to emit a JSON abort payload to stdout.
    """
    if assume_yes:
        return True, ""

    stdin_isatty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    if not stdin_isatty:
        print(
            "qgb run: stdin is not a TTY; refuse to read confirmation blindly. "
            "Pass --yes to proceed in non-interactive contexts "
            "(e.g. CI, quality-gate.ps1).",
            file=sys.stderr,
        )
        return False, "non_tty_without_yes"

    print(
        f"qgb run: about to execute {adopted_count} adopted stage(s) for "
        f"{req_id} and overwrite curated evidence at "
        f".quality-system/evidence/{req_id}/latest/.",
        file=sys.stderr,
    )
    sys.stderr.write("Proceed? [y/N]: ")
    sys.stderr.flush()
    try:
        answer = sys.stdin.readline()
    except EOFError:
        answer = ""
    answer = answer.strip().lower()
    if answer in ("y", "yes"):
        return True, ""
    print("qgb run: aborted by user (no curated evidence written).", file=sys.stderr)
    return False, "declined"


def _abort_to_json(req_id: str, reason: str) -> dict[str, object]:
    """Codex 補修 1: ``--json`` モードで abort 経路も機械可読にする。

    preflight NOT_READY が JSON を返すのと同じ契約に揃える。``reason``
    は ``declined`` / ``non_tty_without_yes`` のいずれか。
    """
    return {
        "ok": False,
        "req_id": req_id,
        "status": "NOT_READY",
        "reason": reason,
    }


def _handle_run(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb run: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb run: --path must point at a project directory, not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    req_id: str = args.req_id
    phase: str = args.phase
    assume_yes: bool = args.yes

    preflight = run_preflight(root, req_id)
    if not preflight.ready_for_run():
        if args.json:
            json.dump(
                _preflight_to_json(preflight, req_id),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            sys.stderr.write(_format_preflight_text(preflight))
        return EXIT_NOT_READY

    # F-008: ask for confirmation only after preflight succeeded. A failed
    # preflight is a NOT_READY that the user cannot answer "yes" to anyway,
    # so prompting first would just be noise.
    proceed, abort_reason = _confirm_run(
        req_id, len(preflight.adopted_stages), assume_yes=assume_yes
    )
    if not proceed:
        if args.json:
            json.dump(
                _abort_to_json(req_id, abort_reason),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        return EXIT_NOT_READY

    timestamps = evidence_mod.make_timestamps()
    results = run_stages(root, preflight.adopted_stages)
    decision = decide(preflight.adopted_stages, results, phase)
    write = write_evidence(
        project_root=root,
        req_id=req_id,
        phase=phase,
        timestamps=timestamps,
        decision=decision,
        adopted=preflight.adopted_stages,
        results=results,
        policy=preflight.policy,
    )

    gate = json.loads(write.gate_path_curated.read_text(encoding="utf-8"))
    if args.json:
        json.dump(_run_result_to_json(gate), sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        _print_run_text(
            gate,
            sys.stdout if decision.status == "ALLOW" else sys.stderr,
        )

    return EXIT_OK if decision.status == "ALLOW" else EXIT_DENY


# ---- validate-policy -----------------------------------------------------


def _print_validate_policy_text(
    report: PreflightReport, req_id: str | None, stream
) -> None:
    blockers = report.blocking_issues()
    warnings_ = report.warnings()

    scope = req_id or "<project>"
    if not blockers and not warnings_:
        print(
            f"OK: design check passed for {scope}; no blockers or warnings.",
            file=stream,
        )
        return

    if blockers:
        print(
            f"NOT_READY: design check found {len(blockers)} blocker(s) "
            f"for {scope}.",
            file=stream,
        )
        for issue in blockers:
            print(f"  - [{issue.kind}] {issue.where}", file=stream)
            print(f"      {issue.message}", file=stream)

    if warnings_:
        if blockers:
            print("", file=stream)
        print(
            f"Warnings ({len(warnings_)}) - design quality advisories "
            f"(qgb run will still proceed):",
            file=stream,
        )
        for issue in warnings_:
            print(f"  - [{issue.kind}] {issue.where}", file=stream)
            print(f"      {issue.message}", file=stream)


def _validate_policy_to_json(
    report: PreflightReport, req_id: str | None
) -> dict[str, object]:
    return {
        "ok": not report.has_blockers(),
        "req_id": req_id,
        "status": "NOT_READY" if report.has_blockers() else "OK",
        "blockers": [
            {"kind": i.kind, "where": i.where, "message": i.message}
            for i in report.blocking_issues()
        ],
        "warnings": [
            {"kind": i.kind, "where": i.where, "message": i.message}
            for i in report.warnings()
        ],
        "summary": {
            "blockers": len(report.blocking_issues()),
            "warnings": len(report.warnings()),
        },
    }


def _handle_validate_policy(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(
            f"qgb validate-policy: path does not exist: {root}", file=sys.stderr
        )
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb validate-policy: --path must point at a project directory, "
            f"not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    req_id: str | None = args.req_id
    report = validate_policy_preflight(root, req_id)

    if args.json:
        json.dump(
            _validate_policy_to_json(report, req_id),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        # Blockers go to stderr (the user must fix them); warnings-only
        # output goes to stderr too so CI scripts that only consume
        # stdout do not silently accept advisories. OK output goes to
        # stdout (the conventional "no news is good news" channel).
        if report.has_blockers() or report.warnings():
            _print_validate_policy_text(report, req_id, sys.stderr)
        else:
            _print_validate_policy_text(report, req_id, sys.stdout)

    return EXIT_NOT_READY if report.has_blockers() else EXIT_OK


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

    # run: real handler (Step 5).
    run_p = subparsers.add_parser(
        "run",
        help="execute a REQ's adopted stages and write curated / volatile evidence",
        description=(
            "Run the adopted stages of <REQ-ID>, producing gate.json + summary.md "
            "+ per-stage logs in two trees: the volatile artifacts run-dir "
            "(.quality-system/artifacts/<REQ>/runs/<timestamp>/) and the "
            "curated evidence latest dir (.quality-system/evidence/<REQ>/latest/). "
            "Returns 0 on ALLOW, 1 on DENY, 2 on NOT_READY (preflight rejected "
            "the inputs without running any stage), 64 on usage errors."
        ),
    )
    run_p.add_argument(
        "req_id",
        metavar="REQ-ID",
        help="The REQ id whose adopted stages will be executed (e.g. REQ-APP-001)",
    )
    run_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    run_p.add_argument(
        "--phase",
        default="verify",
        choices=["red", "green", "refactor", "verify"],
        help=(
            "TDD phase tag recorded in gate.json. Phase 1 wires only 'verify' "
            "semantics; 'red' expected-failure handling is Step 7."
        ),
    )
    run_p.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Skip the interactive confirmation prompt. Required for "
            "non-TTY contexts (CI, scripts). See requirements doc F-008."
        ),
    )
    run_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    run_p.set_defaults(handler=_handle_run)

    # validate-policy: real handler (Step 6a Commit 3).
    vp_p = subparsers.add_parser(
        "validate-policy",
        help="check stage design quality (policy + REQ + contract integrity)",
        description=(
            "Validate stage design quality (stage-design.md §11). Checks "
            "policy.json structure (id uniqueness, depends_on DAG, "
            "recommended stage count), and when a REQ id is given, the "
            "REQ meta + contracts integrity "
            "(stage_id resolution, canonical contract layout, "
            "required_contract_fields coverage). "
            "Distinct from 'qgb validate' (per-file schema) and from "
            "'qgb run' preflight (which treats some advisories as blockers): "
            "manual_check / unsupported verification_type surface as "
            "warnings here, not blockers. "
            "Returns 0 on success (warnings allowed), 2 (NOT_READY) on any "
            "blocker, 64 on usage errors."
        ),
    )
    vp_p.add_argument(
        "req_id",
        metavar="REQ-ID",
        nargs="?",
        default=None,
        help=(
            "Optional REQ id (e.g. REQ-APP-001). Without it, only the "
            "project-wide policy graph is checked. With it, the REQ meta "
            "and its contracts are also resolved."
        ),
    )
    vp_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    vp_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    vp_p.set_defaults(handler=_handle_validate_policy)

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
