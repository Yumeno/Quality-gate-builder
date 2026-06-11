"""Command-line interface for qgb."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

# Phase 2 Step 2.2: imported only for type hints to avoid hot import on every
# CLI entry. ``_handle_patch`` imports them at call time for the same reason
# (keeps `python -m qgb --help` fast for users who never touch `qgb patch`).
from typing import TYPE_CHECKING

from qgb import __version__
from qgb.adapters.base import DetectionResult
from qgb.core import evidence as evidence_mod
from qgb.core.decision import decide
from qgb.core.design_stages import (
    CommitOutcome,
    DesignProposal,
    commit_design,
    propose_design,
)
from qgb.core.detect import run_detect
from qgb.core.evidence import write_evidence
from qgb.core.init import InitReport, run_init
from qgb.core.preflight import (
    PreflightReport,
    run_preflight,
    validate_policy_preflight,
)
from qgb.core.runner import run_stages
from qgb.core.scaffold import ScaffoldOutcome, scaffold_req
from qgb.core.validate import ValidateReport, run_validate

if TYPE_CHECKING:
    from qgb.core.patch_apply import PatchApplyError, PatchApplyResult

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


# ---- detect --------------------------------------------------------------


def _print_detect_text(result: DetectionResult, stream) -> None:
    sel = result.selected
    parts: list[str] = [f"Detected: {sel.language}"]
    if sel.framework:
        parts.append(f"framework={sel.framework}")
    if sel.test_runner:
        parts.append(f"test_runner={sel.test_runner}")
    parts.append(f"confidence={sel.confidence:.2f}")
    parts.append(f"adapter={sel.adapter_name}")
    print(" / ".join(parts), file=stream)

    if sel.evidence:
        print("Evidence:", file=stream)
        for ev in sel.evidence:
            tail = f" ({ev.note})" if ev.note else ""
            print(f"  - [{ev.kind}] {ev.where}{tail}", file=stream)

    if len(result.candidates) > 1:
        print("", file=stream)
        print(
            f"Other candidates ({len(result.candidates) - 1}):", file=stream
        )
        for cand in result.candidates:
            if cand is sel:
                continue
            print(
                f"  - {cand.language} (confidence={cand.confidence:.2f}, "
                f"adapter={cand.adapter_name})",
                file=stream,
            )


def _detect_to_json(result: DetectionResult) -> dict[str, object]:
    def profile_dict(p) -> dict[str, object]:
        return {
            "language": p.language,
            "framework": p.framework,
            "test_runner": p.test_runner,
            "confidence": p.confidence,
            "adapter_name": p.adapter_name,
            "evidence": [
                {"kind": ev.kind, "where": ev.where, "note": ev.note}
                for ev in p.evidence
            ],
        }

    return {
        # Codex 補修 7: schema_version is the integration contract for
        # downstream consumers (Step 6d design-stages, future skills).
        # Bump on any breaking change to the JSON shape.
        "schema_version": 1,
        "ok": True,
        "selected": profile_dict(result.selected),
        "candidates": [profile_dict(p) for p in result.candidates],
    }


def _handle_detect(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb detect: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb detect: --path must point at a project directory, "
            f"not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    result = run_detect(root)

    if args.json:
        json.dump(
            _detect_to_json(result), sys.stdout, ensure_ascii=False, indent=2
        )
        sys.stdout.write("\n")
    else:
        _print_detect_text(result, sys.stdout)

    return EXIT_OK


# ---- design-stages -------------------------------------------------------


def _proposal_to_json(proposal: DesignProposal) -> dict[str, object]:
    # Codex 補修 7: `committed` lives on the envelope (CLI-level state),
    # not on the proposal dataclass itself. Proposal carries pure data.
    return {
        "schema_version": 1,
        "ok": True,
        "committed": False,
        "detect": {
            "selected": _detect_profile_dict(proposal.detect.selected),
            "candidates": [
                _detect_profile_dict(p) for p in proposal.detect.candidates
            ],
        },
        "proposed": {
            "template": proposal.template,
            "stages": [
                {
                    "id": s.id,
                    "name": s.name,
                    "responsibility": s.responsibility,
                    "depends_on": list(s.depends_on),
                    "verification_type": s.verification_type,
                    "required_contract_fields": list(s.required_contract_fields),
                }
                for s in proposal.stages
            ],
        },
    }


def _detect_profile_dict(p) -> dict[str, object]:
    return {
        "language": p.language,
        "framework": p.framework,
        "test_runner": p.test_runner,
        "confidence": p.confidence,
        "adapter_name": p.adapter_name,
        "evidence": [
            {"kind": ev.kind, "where": ev.where, "note": ev.note}
            for ev in p.evidence
        ],
    }


def _print_proposal_text(proposal: DesignProposal, stream) -> None:
    sel = proposal.detect.selected
    banner = f"Detected: {sel.language}"
    if sel.framework:
        banner += f" / framework={sel.framework}"
    if sel.test_runner:
        banner += f" / test_runner={sel.test_runner}"
    print(banner, file=stream)
    print(f"Recommended template: {proposal.template}", file=stream)
    print("", file=stream)
    print("Proposed stages:", file=stream)
    for s in proposal.stages:
        deps = ", ".join(s.depends_on) if s.depends_on else ""
        print(
            f"  {s.id}: {s.name} (verification_type={s.verification_type}, "
            f"depends_on=[{deps}])",
            file=stream,
        )
    print("", file=stream)
    print(
        "Note: this is a proposal only. policy.json was not modified. "
        "Run `qgb design-stages --commit` to adopt.",
        file=stream,
    )


def _commit_outcome_to_json(outcome: CommitOutcome) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": outcome.ok,
        "committed": outcome.ok,
        "message": outcome.message,
        "policy_path": (
            str(outcome.policy_path) if outcome.policy_path else None
        ),
        "blockers": list(outcome.blockers),
        "warnings": list(outcome.warnings),
    }


def _print_commit_outcome_text(outcome: CommitOutcome, stream) -> None:
    if outcome.ok:
        print(f"Committed: {outcome.policy_path}", file=stream)
        if outcome.warnings:
            print(
                f"validate-policy warnings ({len(outcome.warnings)}):",
                file=stream,
            )
            for w in outcome.warnings:
                print(f"  - [{w['kind']}] {w['where']}", file=stream)
                print(f"      {w['message']}", file=stream)
    else:
        print(f"Refused: {outcome.message}", file=stream)
        if outcome.blockers:
            print("Blockers:", file=stream)
            for b in outcome.blockers:
                print(f"  - [{b['kind']}] {b['where']}", file=stream)
                print(f"      {b['message']}", file=stream)


def _handle_design_stages(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(
            f"qgb design-stages: path does not exist: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb design-stages: --path must point at a project directory, "
            f"not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    proposal = propose_design(root)

    if not args.commit:
        if args.json:
            json.dump(
                _proposal_to_json(proposal),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            _print_proposal_text(proposal, sys.stdout)
        return EXIT_OK

    # --commit branch.
    outcome = commit_design(root, proposal, force=args.force)
    if args.json:
        json.dump(
            _commit_outcome_to_json(outcome),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        _print_commit_outcome_text(
            outcome, sys.stdout if outcome.ok else sys.stderr
        )
    return EXIT_OK if outcome.ok else EXIT_NOT_READY


# ---- scaffold ------------------------------------------------------------


def _scaffold_outcome_to_json(outcome: ScaffoldOutcome) -> dict[str, object]:
    return {
        "schema_version": 1,
        "ok": outcome.ok,
        "req_id": outcome.req_id,
        "message": outcome.message,
        "created": list(outcome.created),
    }


def _print_scaffold_text(outcome: ScaffoldOutcome, stream) -> None:
    if outcome.ok:
        print(f"Scaffolded {outcome.req_id}:", file=stream)
        for path in outcome.created:
            print(f"  + {path}", file=stream)
        print("", file=stream)
        print(
            "Generated contracts are schema-valid placeholders. "
            "Fill in real values before `qgb run`.",
            file=stream,
        )
    else:
        print(f"Refused: {outcome.message}", file=stream)


def _handle_scaffold(args: argparse.Namespace) -> int:
    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb scaffold: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb scaffold: --path must point at a project directory, "
            f"not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    outcome = scaffold_req(root, args.req_id, force=args.force)

    # Invalid REQ id is a usage error (caller passed bad input), not a
    # state error.
    if not outcome.ok and outcome.message.startswith("invalid REQ id"):
        if args.json:
            json.dump(
                _scaffold_outcome_to_json(outcome),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            print(f"qgb scaffold: {outcome.message}", file=sys.stderr)
        return EXIT_USAGE

    if args.json:
        json.dump(
            _scaffold_outcome_to_json(outcome),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        _print_scaffold_text(
            outcome, sys.stdout if outcome.ok else sys.stderr
        )

    return EXIT_OK if outcome.ok else EXIT_NOT_READY


# ---- qgb patch (Phase 2 Step 2.2) ---------------------------------------


def _patch_result_to_json(
    result: PatchApplyResult,
    *,
    dry_run: bool,
) -> dict[str, object]:
    """Serialize PatchApplyResult into a JSON-friendly dict."""
    return {
        "ok": True,
        "target": str(result.target),
        "target_kind": result.target_kind.value,
        "would_write": result.would_write,
        "written": result.written,
        "dry_run": dry_run,
        "warnings": result.warnings,
        "warning_count": len(result.warnings),
    }


def _patch_error_to_json(
    err: PatchApplyError,
    *,
    target_rel: str,
    patch_path: str,
    dry_run: bool,
) -> dict[str, object]:
    """Serialize PatchApplyError into a JSON-friendly dict."""
    payload: dict[str, object] = {
        "ok": False,
        "target": target_rel,
        "patch": patch_path,
        "dry_run": dry_run,
        "reason": err.reason,
        "message": err.message,
    }
    if err.detail:
        payload["detail"] = err.detail
    return payload


def _handle_patch(args: argparse.Namespace) -> int:
    """Apply a JSON Patch file to a target under .quality-system/.

    Phase 2 Step 2.2 (prejournal §6.5). Exit codes:

    * ``EXIT_OK`` (0): patch applied successfully (or dry-run succeeded)
    * ``EXIT_DENY`` (1): validate-policy blocker prevented application
    * ``EXIT_NOT_READY`` (2): schema / path / parse error
    * ``EXIT_USAGE`` (64): argument-level problem
    """
    from qgb.core.patch_apply import (
        PatchApplyError,
        apply_patch_to_target,
    )

    project_root = Path(args.path).resolve()
    patch_path = Path(args.patch)
    target_rel = args.target
    dry_run = bool(args.dry_run)

    if not patch_path.exists():
        if args.json:
            json.dump(
                {
                    "ok": False,
                    "target": target_rel,
                    "patch": str(patch_path),
                    "dry_run": dry_run,
                    "reason": "patch_not_found",
                    "message": f"patch file does not exist: {patch_path}",
                },
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            print(
                f"qgb patch: patch file does not exist: {patch_path}",
                file=sys.stderr,
            )
        return EXIT_NOT_READY

    try:
        result = apply_patch_to_target(
            project_root,
            target_rel,
            patch_path,
            dry_run=dry_run,
        )
    except PatchApplyError as exc:
        if args.json:
            json.dump(
                _patch_error_to_json(
                    exc,
                    target_rel=target_rel,
                    patch_path=str(patch_path),
                    dry_run=dry_run,
                ),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            print(f"qgb patch: {exc}", file=sys.stderr)
            for line in exc.detail.get("blockers", []) or []:
                if isinstance(line, dict):
                    print(
                        f"  blocker: {line.get('kind')} at {line.get('where')}: "
                        f"{line.get('message')}",
                        file=sys.stderr,
                    )
            for issue in exc.detail.get("issues", []) or []:
                if isinstance(issue, dict):
                    print(
                        f"  schema: {issue.get('path')} - {issue.get('message')}",
                        file=sys.stderr,
                    )
        # validate_policy_blocker is the only "soft" DENY; other reasons are
        # schema/path/parse problems → NOT_READY (Codex 計画レビュー指摘 11).
        if exc.reason == "validate_policy_blocker":
            return EXIT_DENY
        return EXIT_NOT_READY

    # Success path (including dry-run).
    if args.json:
        json.dump(
            _patch_result_to_json(result, dry_run=dry_run),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        if dry_run:
            print(
                f"qgb patch: would write {result.target} "
                f"({result.target_kind.value})",
                file=sys.stdout,
            )
        else:
            print(
                f"qgb patch: wrote {result.target} "
                f"({result.target_kind.value})",
                file=sys.stdout,
            )
        if result.warnings:
            print(
                f"qgb patch: applied with {len(result.warnings)} warning(s):",
                file=sys.stderr,
            )
            for w in result.warnings:
                print(f"  - {w}", file=sys.stderr)
    return EXIT_OK


# ---- qgb add-waiver / add-knowledge (Phase 2 Step 2.3) -------------------


def _edit_error_to_json(err, *, command: str, dry_run: bool) -> dict[str, object]:
    payload: dict[str, object] = {
        "ok": False,
        "command": command,
        "dry_run": dry_run,
        "reason": err.reason,
        "message": err.message,
    }
    if err.detail:
        payload["detail"] = err.detail
    return payload


def _handle_add_waiver(args: argparse.Namespace) -> int:
    """Waive a REQ stage via the patch substrate + knowledge store.

    Exit codes: 0 success (including no-op), 1 validate-policy blocker,
    2 other errors (REQ/stage not found, waiver conflict, schema issues).
    """
    from qgb.core.edit_commands import EditError, add_waiver

    project_root = Path(args.path).resolve()
    dry_run = bool(args.dry_run)

    try:
        result = add_waiver(
            project_root,
            args.req_id,
            args.stage_id,
            args.reason,
            decided_by=args.decided_by,
            force=bool(args.force),
            dry_run=dry_run,
        )
    except EditError as exc:
        if args.json:
            json.dump(
                _edit_error_to_json(exc, command="add-waiver", dry_run=dry_run),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            print(f"qgb add-waiver: {exc}", file=sys.stderr)
            for b in exc.detail.get("blockers", []) or []:
                if isinstance(b, dict):
                    print(
                        f"  blocker: {b.get('kind')} at {b.get('where')}: "
                        f"{b.get('message')}",
                        file=sys.stderr,
                    )
        return EXIT_DENY if exc.reason == "validate_policy_blocker" else EXIT_NOT_READY

    if args.json:
        json.dump(
            {
                "ok": True,
                "command": "add-waiver",
                "req_id": result.req_id,
                "stage_id": result.stage_id,
                "no_op": result.no_op,
                "meta_changed": result.meta_changed,
                "knowledge_appended": result.knowledge_appended,
                "forced": result.forced,
                "dry_run": dry_run,
                "would_write": result.would_write,
                "warnings": result.warnings,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        if result.no_op:
            print(
                f"qgb add-waiver: {result.req_id}/{result.stage_id} is "
                f"already waived with this reason (no-op)",
                file=sys.stdout,
            )
        elif dry_run:
            print(
                f"qgb add-waiver: would waive {result.req_id}/{result.stage_id}",
                file=sys.stdout,
            )
        else:
            print(
                f"qgb add-waiver: waived {result.req_id}/{result.stage_id}"
                + (" (meta updated)" if result.meta_changed else "")
                + (" (knowledge recorded)" if result.knowledge_appended else ""),
                file=sys.stdout,
            )
        for w in result.warnings:
            print(f"qgb add-waiver: warning: {w}", file=sys.stderr)
    return EXIT_OK


def _handle_add_knowledge(args: argparse.Namespace) -> int:
    """Append knowledge entries from a JSON file (append-only store).

    Exit codes: 0 success (including all-skip), 2 schema / parse errors.
    """
    from qgb.core.edit_commands import EditError, add_knowledge

    project_root = Path(args.path).resolve()
    dry_run = bool(args.dry_run)

    try:
        result = add_knowledge(
            project_root, Path(args.file), dry_run=dry_run
        )
    except EditError as exc:
        if args.json:
            json.dump(
                _edit_error_to_json(
                    exc, command="add-knowledge", dry_run=dry_run
                ),
                sys.stdout,
                ensure_ascii=False,
                indent=2,
            )
            sys.stdout.write("\n")
        else:
            print(f"qgb add-knowledge: {exc}", file=sys.stderr)
            for issue in exc.detail.get("issues", []) or []:
                if isinstance(issue, dict):
                    print(
                        f"  entry[{issue.get('index')}] "
                        f"{issue.get('path') or '/'}: {issue.get('message')}",
                        file=sys.stderr,
                    )
        return EXIT_NOT_READY

    if args.json:
        json.dump(
            {
                "ok": True,
                "command": "add-knowledge",
                "appended": result.appended_ids,
                "skipped": result.skipped_ids,
                "appended_count": len(result.appended_ids),
                "skipped_count": len(result.skipped_ids),
                "dry_run": dry_run,
                "would_write": result.would_write,
                "written": result.written,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        verb = "would append" if dry_run else "appended"
        print(
            f"qgb add-knowledge: {verb} {len(result.appended_ids)} "
            f"entr(y/ies), skipped {len(result.skipped_ids)} existing",
            file=sys.stdout,
        )
    return EXIT_OK


# ---- check / dev (Phase 2 Step 2.4) ---------------------------------------


def _orphan_advisories_payload(orphan_findings) -> list[dict[str, object]]:
    return [
        {
            "knowledge_id": f.knowledge_id,
            "kind": f.knowledge_kind,
            "applies_to": f.applies_to,
            "stage_id": f.stage_id,
            "severity": f.severity,
            "message": f.message,
        }
        for f in orphan_findings
    ]


def _check_result_to_json(outcome) -> dict[str, object]:
    gate = outcome.gate
    return {
        "ok": gate["status"] == "ALLOW",
        "command": "check",
        "rehearsal": True,
        "req_id": gate["req_id"],
        "status": gate["status"],
        "failed_stage": gate["failed_stage"],
        "phase": gate["phase"],
        "check_dir": gate["paths"]["run_dir"],
        "orphan_advisories": _orphan_advisories_payload(
            outcome.orphan_findings
        ),
        "gate": gate,
    }


def _print_check_text(outcome, stream) -> None:
    gate = outcome.gate
    status = gate["status"]
    verdict = "would ALLOW" if status == "ALLOW" else "would DENY"
    print(
        f"CHECK {status}: an official run of {gate['req_id']} {verdict} "
        f"(phase={gate['phase']})",
        file=stream,
    )
    print(
        "  note: rehearsal only - not an official gate; curated evidence "
        "was not updated",
        file=stream,
    )
    print(f"  meaning: {gate['decision']['meaning']}", file=stream)
    print(f"  check_dir: {gate['paths']['run_dir']}", file=stream)
    if status == "DENY":
        print(f"  failed_stage: {gate['failed_stage']}", file=stream)
    print("  stages:", file=stream)
    for stage in gate["stages"]:
        print(
            f"    - {stage['id']} ({stage['verification_type']}): {stage['result']}",
            file=stream,
        )
    if outcome.orphan_findings:
        print(
            f"  knowledge orphan advisories ({len(outcome.orphan_findings)}) "
            f"- informational; do not affect this check's exit code "
            f"(enforced by 'qgb validate-policy' / REQ-less 'qgb check'):",
            file=stream,
        )
        for f in outcome.orphan_findings:
            print(
                f"    - [{f.severity}] {f.knowledge_id}: {f.message}",
                file=stream,
            )


def _handle_check(args: argparse.Namespace) -> int:
    """`qgb check [REQ-ID]` — daily verification channel (Step 2.4).

    Per-REQ path = official run rehearsal: shares run_preflight /
    run_stages / decide with `qgb run`, writes volatile check artifacts
    only (never curated evidence, never knowledge.jsonl), exit code
    mirrors `qgb run` (0=would ALLOW, 1=would DENY, 2=NOT_READY).
    Knowledge orphans are shown as advisories and never block this path.

    REQ-less path = project-wide design diagnostics: delegates to
    validate_policy_preflight(req_id=None) (which does enforce orphan
    blockers), executes no verification, writes nothing.

    No F-008 confirmation prompt in either path: F-008 protects the
    curated evidence mutation, and check never mutates curated state.
    Verification commands declared in contracts DO run (the rehearsal's
    value) — check is "does not update curated evidence", not
    "read-only".
    """
    # Imported at call time, matching `qgb patch` (keeps --help fast).
    from qgb.core.check import run_check

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"qgb check: path does not exist: {root}", file=sys.stderr)
        return EXIT_USAGE
    if not root.is_dir():
        print(
            f"qgb check: --path must point at a project directory, "
            f"not a file: {root}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    req_id: str | None = args.req_id

    if req_id is None:
        # Project-wide design diagnostics (no verification, no artifacts).
        # 段 1 edge-cases 指摘: a forgotten REQ-ID with --phase silently
        # falls into this path where phase is meaningless; warn so the
        # user does not misread exit 0 as "would ALLOW".
        if args.phase != "verify":
            print(
                "qgb check: --phase is ignored without REQ-ID "
                "(project-wide diagnostics execute no stages).",
                file=sys.stderr,
            )
        report = validate_policy_preflight(root, None)
        if args.json:
            payload = _validate_policy_to_json(report, None)
            payload["command"] = "check"
            payload["scope"] = "project"
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            print(
                "qgb check (project-wide design diagnostics; no "
                "verification executed, no artifacts written):",
                file=sys.stderr if report.has_blockers() or report.warnings()
                else sys.stdout,
            )
            if report.has_blockers() or report.warnings():
                _print_validate_policy_text(report, None, sys.stderr)
            else:
                _print_validate_policy_text(report, None, sys.stdout)
        return EXIT_NOT_READY if report.has_blockers() else EXIT_OK

    outcome = run_check(root, req_id, phase=args.phase)

    if outcome.gate is None:
        # Preflight rejected the REQ; mirror `qgb run`'s NOT_READY shape.
        if args.json:
            payload = _preflight_to_json(outcome.preflight, req_id)
            payload["command"] = "check"
            json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        else:
            sys.stderr.write(_format_preflight_text(outcome.preflight))
        return EXIT_NOT_READY

    if args.json:
        json.dump(
            _check_result_to_json(outcome),
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
    else:
        _print_check_text(
            outcome,
            sys.stdout if outcome.gate["status"] == "ALLOW" else sys.stderr,
        )

    return EXIT_OK if outcome.gate["status"] == "ALLOW" else EXIT_DENY


def _handle_dev(args: argparse.Namespace) -> int:
    """`qgb dev` — thin alias of `qgb check` (Step 2.4).

    Phase 2 keeps dev as a reserved entry point: identical behaviour to
    check (single execution). Watch mode / changed-files narrowing are
    Phase 3 (P3 tension: requires a REQ <-> source dependency mapping).
    """
    return _handle_check(args)


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

    # Phase 1 commands. As of Step 6d, all Phase 1 required commands have
    # real handlers; the stub mechanism is retained for any future Phase 2+
    # subcommand placeholders.

    # design-stages: real handler (Step 6d).
    ds_p = subparsers.add_parser(
        "design-stages",
        help="propose verification stages for the target project",
        description=(
            "Suggest a set of stages for the target project based on "
            "`qgb detect` output and a Phase 1 template (generic-minimal). "
            "Without --commit, this prints the proposal only; with --commit "
            "the proposal is validated by `validate-policy` and, if it "
            "passes, atomically written to .quality-system/policy.json. "
            "Returns 0 on success, 2 (NOT_READY) on commit refusal or "
            "validate-policy blockers, 64 on usage errors."
        ),
    )
    ds_p.add_argument(
        "--path",
        default=".",
        help="Project root (default: current directory)",
    )
    ds_p.add_argument(
        "--commit",
        action="store_true",
        help=(
            "Adopt the proposed stages: validate the candidate policy and, "
            "if it passes, overwrite .quality-system/policy.json#stages."
        ),
    )
    ds_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "With --commit, replace an existing non-empty stages[] list. "
            "Without this flag commits refuse to overwrite previous work."
        ),
    )
    ds_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    ds_p.set_defaults(handler=_handle_design_stages)

    # scaffold: real handler (Step 6d).
    sc_p = subparsers.add_parser(
        "scaffold",
        help="generate a REQ skeleton (meta + contract placeholders + tests)",
        description=(
            "Generate the .quality-system/req/<REQ>.meta.json, "
            "contract placeholders under .quality-system/contracts/<REQ>/, "
            "and minimal tests/quality/L1_behavior/ + L5_contract/ scaffolds. "
            "Generated contracts are schema-valid placeholders (TODO markers) "
            "so `qgb validate` and `qgb validate-policy` both pass on the "
            "fresh tree; `qgb run` will DENY until you fill in real values. "
            "Returns 0 on success, 2 (NOT_READY) when the project is not "
            "ready or the REQ already exists, 64 on usage errors "
            "(missing path, invalid REQ id, etc.)."
        ),
    )
    sc_p.add_argument(
        "req_id",
        metavar="REQ-ID",
        help="REQ id following ^REQ-[A-Z0-9]+-[0-9]{3,}$ (e.g. REQ-APP-001)",
    )
    sc_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    sc_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite an existing REQ scaffold (meta + contracts only). "
            "Other REQs and policy.json are never touched."
        ),
    )
    sc_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    sc_p.set_defaults(handler=_handle_scaffold)

    # detect: real handler (Step 6c).
    detect_p = subparsers.add_parser(
        "detect",
        help="detect target project language, framework, and test runner",
        description=(
            "Inspect the target project tree (no policy / no contracts) "
            "and propose a language/framework/test_runner profile. Phase 1 "
            "ships PythonAdapter and GenericAdapter; the latter always "
            "matches as a fallback. Output is a single 'selected' profile "
            "plus the full 'candidates' list. The confidence value is a "
            "heuristic ranking score (not a probability). "
            "Returns 0 always (generic is the safety net); 64 on usage errors."
        ),
    )
    detect_p.add_argument(
        "--path",
        default=".",
        help="Target project root (default: current directory)",
    )
    detect_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    detect_p.set_defaults(handler=_handle_detect)

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
            "TDD phase tag recorded in gate.json. All four phases (red / "
            "green / refactor / verify) emit phase-specific decision.meaning "
            "wording (F-016): phase=red treats DENY as the expected failure "
            "of an un-implemented test, and ALLOW under phase=red is flagged "
            "as 'unexpected pass'. The CLI exit code is aligned with status "
            "(ALLOW=0, DENY=1) regardless of phase."
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

    # ---- qgb patch (Phase 2 Step 2.2) -----------------------------------
    patch_p = subparsers.add_parser(
        "patch",
        help=(
            "Apply a JSON Patch (RFC 6902 subset) to a .quality-system/ "
            "target with atomic swap and validate-policy gating "
            "(Phase 2 Step 2.2)"
        ),
        description=(
            "Apply a JSON Patch to a target file under .quality-system/. "
            "The patch is validated against patch.schema.json (Phase 2 op "
            "subset: add/replace/remove/test), applied in-memory, then the "
            "patched document is validated against its own schema and the "
            "project-wide validate-policy preflight. Only if every check "
            "passes is the target replaced atomically via sibling tmp + "
            "os.replace. This guarantees target-file atomicity; quality-"
            "system-wide transactions are NOT provided (Codex 計画レビュー "
            "指摘 7、Phase 3 送り)."
        ),
    )
    patch_p.add_argument(
        "target",
        help=(
            "Project-relative target path. Accepts "
            ".quality-system/policy.json, "
            ".quality-system/req/<REQ>.meta.json, or "
            ".quality-system/contracts/<REQ>/<stage>.json. "
            "Absolute paths and out-of-tree paths are rejected."
        ),
    )
    patch_p.add_argument(
        "patch",
        help="Path to the JSON Patch file (any location).",
    )
    patch_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    patch_p.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Run all validations (patch schema, target schema, "
            "validate-policy) but do not write. Returns the same exit "
            "code that a real run would have produced."
        ),
    )
    patch_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    patch_p.set_defaults(handler=_handle_patch)

    # ---- qgb add-waiver (Phase 2 Step 2.3) -------------------------------
    aw_p = subparsers.add_parser(
        "add-waiver",
        help=(
            "Waive a stage of a REQ with a recorded reason "
            "(req-meta via patch substrate + knowledge.jsonl evidence, "
            "Phase 2 Step 2.3)"
        ),
        description=(
            "Mark a stage as waived in the REQ meta (validated through the "
            "Step 2.2 patch substrate: schema + validate-policy gated, "
            "atomic swap) and record the decision as a kind=waiver entry "
            "in knowledge.jsonl (append-only, idempotent). Re-running with "
            "the same reason is a no-op; a different reason requires "
            "--force, which updates the req-meta only and keeps the "
            "existing knowledge entry as audit history (formal revision is "
            "Phase 3 revoke/supersede). Atomicity is per-file with "
            "idempotent recovery: if the knowledge append fails after the "
            "meta update, re-running the command converges."
        ),
    )
    aw_p.add_argument("req_id", help="REQ id (e.g. REQ-APP-001)")
    aw_p.add_argument("stage_id", help="Stage id declared in the REQ meta")
    aw_p.add_argument(
        "--reason",
        required=True,
        help="Justification recorded as evidence (F-007; non-empty)",
    )
    aw_p.add_argument(
        "--decided-by",
        default="user",
        help="Who decided the waiver (recorded in knowledge.jsonl; default: user)",
    )
    aw_p.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite the req-meta reason when the stage is already waived "
            "with a different reason (the existing knowledge entry is kept)"
        ),
    )
    aw_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate everything but write nothing",
    )
    aw_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    aw_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    aw_p.set_defaults(handler=_handle_add_waiver)

    # ---- qgb add-knowledge (Phase 2 Step 2.3) ----------------------------
    ak_p = subparsers.add_parser(
        "add-knowledge",
        help=(
            "Append knowledge entries from a JSON file to knowledge.jsonl "
            "(append-only, schema-validated, Phase 2 Step 2.3)"
        ),
        description=(
            "Validate one entry (object) or several (array) against "
            "knowledge.schema.json and append them to "
            ".quality-system/knowledge/knowledge.jsonl. The input file is "
            "the source of truth: no fields are backfilled (created_at "
            "must be present). Entries whose id already exists are "
            "skipped (idempotent). If any entry fails validation, nothing "
            "is appended (all-or-nothing). There is no --force: the store "
            "is append-only and entry removal is Phase 3."
        ),
    )
    ak_p.add_argument(
        "file",
        help="Path to a JSON file containing one entry or an array of entries",
    )
    ak_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report what would be appended, write nothing",
    )
    ak_p.add_argument(
        "--path",
        default=".",
        help="Project root containing .quality-system/ (default: current directory)",
    )
    ak_p.add_argument(
        "--json",
        action="store_true",
        help="Emit a machine-readable JSON report to stdout instead of text",
    )
    ak_p.set_defaults(handler=_handle_add_knowledge)

    # ---- qgb check / qgb dev (Phase 2 Step 2.4) -------------------------
    check_description = (
        "Rehearse an official run without updating curated evidence. "
        "With REQ-ID: shares the exact preflight / stage execution / "
        "judgement with 'qgb run', but writes gate.json + summary.md + "
        "stage logs ONLY to the volatile check dir "
        "(.quality-system/artifacts/<REQ>/checks/<timestamp>-<run_id>/); "
        "curated evidence/<REQ>/latest/ and knowledge.jsonl are never "
        "touched. Verification commands declared in contracts DO run - "
        "check does not update curated evidence, but it is not read-only. "
        "Knowledge orphan findings are shown as advisories and do not "
        "affect the exit code (they are enforced by 'qgb validate-policy' "
        "and by the REQ-less form). Without REQ-ID: project-wide design "
        "diagnostics only (validate-policy; no verification, no "
        "artifacts). No confirmation prompt (F-008 protects curated "
        "evidence, which check never mutates). Old check dirs are pruned "
        "per QGB_KEEP_RUNS (default 10). "
        "Returns 0 when an official run would ALLOW (or project-wide "
        "diagnostics found no blocker), 1 when it would DENY, 2 on "
        "NOT_READY / blockers, 64 on usage errors."
    )
    check_p = subparsers.add_parser(
        "check",
        help="rehearse a run without updating curated evidence (daily channel)",
        description=check_description,
    )
    dev_p = subparsers.add_parser(
        "dev",
        help="daily development loop entry (currently equivalent to 'qgb check')",
        description=(
            "Currently equivalent to 'qgb check' (single execution). "
            "Reserved as the daily development loop entry point: watch "
            "mode and changed-files narrowing are planned for Phase 3. "
            + check_description
        ),
    )
    for p, cmd in ((check_p, "check"), (dev_p, "dev")):
        p.add_argument(
            "req_id",
            metavar="REQ-ID",
            nargs="?",
            default=None,
            help=(
                "Optional REQ id (e.g. REQ-APP-001). With it, rehearse the "
                "REQ's adopted stages. Without it, run project-wide design "
                "diagnostics only."
            ),
        )
        p.add_argument(
            "--path",
            default=".",
            help=(
                "Project root containing .quality-system/ "
                "(default: current directory)"
            ),
        )
        p.add_argument(
            "--phase",
            default="verify",
            choices=["red", "green", "refactor", "verify"],
            help=(
                "TDD phase tag recorded in the rehearsal gate.json; same "
                "decision.meaning wording as 'qgb run' plus a check-"
                "rehearsal note. Exit code is aligned with status "
                "(would-ALLOW=0, would-DENY=1) regardless of phase."
            ),
        )
        p.add_argument(
            "--json",
            action="store_true",
            help="Emit a machine-readable JSON report to stdout instead of text",
        )
        p.set_defaults(handler=_handle_check if cmd == "check" else _handle_dev)

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
