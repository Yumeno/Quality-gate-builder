"""Initialize a fresh .quality-system/ tree in the target project.

Responsibility (matches requirements doc §B-004, §3.6, F-002, F-003):

* Create the canonical .quality-system/ directory layout.
* Write minimal config.json and policy.json templates. The policy starts with
  an empty stages[] array; populating it is the job of `qgb design-stages`
  (Step 6, not this command).
* Create knowledge/ scaffolding (empty knowledge.jsonl + project-context.md).
* Append `.quality-system/artifacts/` to the project's .gitignore (creating
  it if needed). This corresponds to the volatile artifacts path that the
  `qgb run` command will use (Step 5).

Out of scope (delegated elsewhere):

* Detecting the target language / framework -> `qgb detect` (Step 6).
* Designing stages for the target -> `qgb design-stages` (Step 6).
* Generating REQ scaffolding -> `qgb scaffold` (Step 6).

Idempotency:

* Default behaviour does NOT overwrite existing files. Each file is reported
  as ``created`` or ``skipped (already exists)``.
* `force=True` overwrites existing files. Directories are always preserved.
* `.gitignore` is appended (not rewritten) when the artifacts line is absent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from qgb import __version__

# Files and directories the .quality-system/ tree consists of after init.
_QS_DIRS: tuple[str, ...] = (
    "req",
    "contracts",
    "knowledge",
    "evidence",
    "artifacts",
)

_GITIGNORE_HEADER = "# qgb volatile artifacts"
_GITIGNORE_ENTRY = ".quality-system/artifacts/"


@dataclass(frozen=True)
class FileOutcome:
    """What happened to a single file during init."""

    path: Path
    action: str   # "created" | "skipped" | "overwritten"
    note: str = ""


@dataclass
class InitReport:
    """Aggregated outcome of qgb init."""

    project_root: Path
    file_outcomes: list[FileOutcome] = field(default_factory=list)
    dirs_ensured: list[Path] = field(default_factory=list)
    gitignore_action: str = ""   # "created" | "appended" | "already-present" | "skipped"


def _read_template(name: str) -> str:
    """Read a bundled init template (kept under qgb/templates/)."""
    resource = resources.files("qgb").joinpath("templates", name)
    with resource.open("r", encoding="utf-8") as fh:
        return fh.read()


def _materialise_config(project_name: str) -> str:
    raw = _read_template("config.initial.json")
    # Lightweight substitution; templates are small and JSON-shaped.
    populated = raw.replace("{project_name}", project_name).replace(
        "{qgb_version}", __version__
    )
    # Round-trip through json to normalise whitespace and catch broken templates early.
    return json.dumps(json.loads(populated), ensure_ascii=False, indent=2) + "\n"


def _materialise_policy() -> str:
    raw = _read_template("policy.initial.json")
    return json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n"


def _materialise_project_context() -> str:
    return _read_template("project-context.initial.md")


def _write_file(
    path: Path,
    content: str,
    *,
    force: bool,
    report: InitReport,
) -> None:
    if path.exists():
        if not force:
            report.file_outcomes.append(
                FileOutcome(path=path, action="skipped", note="file already exists")
            )
            return
        action = "overwritten"
    else:
        action = "created"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    report.file_outcomes.append(FileOutcome(path=path, action=action))


def _ensure_dir(path: Path, report: InitReport) -> None:
    path.mkdir(parents=True, exist_ok=True)
    report.dirs_ensured.append(path)


def _update_gitignore(project_root: Path, report: InitReport) -> None:
    """Append the qgb artifacts entry to .gitignore (idempotent)."""
    gitignore = project_root / ".gitignore"
    if gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        existing_lines = {line.strip() for line in existing.splitlines()}
        if _GITIGNORE_ENTRY in existing_lines:
            report.gitignore_action = "already-present"
            return
        # Ensure a trailing newline before appending.
        suffix = "" if existing.endswith("\n") or not existing else "\n"
        addition = f"{suffix}\n{_GITIGNORE_HEADER}\n{_GITIGNORE_ENTRY}\n"
        gitignore.write_text(existing + addition, encoding="utf-8")
        report.gitignore_action = "appended"
        return
    gitignore.write_text(
        f"{_GITIGNORE_HEADER}\n{_GITIGNORE_ENTRY}\n", encoding="utf-8"
    )
    report.gitignore_action = "created"


def run_init(
    project_root: Path,
    *,
    project_name: str | None = None,
    force: bool = False,
) -> InitReport:
    """Initialise .quality-system/ at ``project_root``.

    ``project_name`` defaults to the basename of ``project_root``. Pass an
    explicit value when initialising under a directory whose name does not
    match the desired project identifier.
    """
    project_root = project_root.resolve()
    if project_name is None:
        project_name = project_root.name or "qgb-project"

    report = InitReport(project_root=project_root)

    qs = project_root / ".quality-system"
    _ensure_dir(qs, report)
    for sub in _QS_DIRS:
        _ensure_dir(qs / sub, report)

    _write_file(qs / "config.json", _materialise_config(project_name), force=force, report=report)
    _write_file(qs / "policy.json", _materialise_policy(), force=force, report=report)
    _write_file(
        qs / "knowledge" / "knowledge.jsonl",
        "",
        force=force,
        report=report,
    )
    _write_file(
        qs / "knowledge" / "project-context.md",
        _materialise_project_context(),
        force=force,
        report=report,
    )

    _update_gitignore(project_root, report)

    return report
