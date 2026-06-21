"""Initialize a fresh .quality-system/ tree in the target project.

Responsibility (matches requirements doc B-004 / 3.6 / F-002 / F-003):

* Create the canonical .quality-system/ directory layout.
* Write minimal config.json and policy.json templates. The policy starts with
  an empty stages[] array; populating it is the job of `qgb design-stages`
  (Step 6, not this command).
* Create knowledge/ scaffolding (empty knowledge.jsonl + project-context.md).
* Append `.quality-system/artifacts/` to the project's .gitignore (creating
  it if needed). This corresponds to the volatile artifacts path that the
  `qgb run` command will use (Step 5).

Out of scope (delegated elsewhere):

* Designing stages for the target -> `qgb design-stages` (Step 6).
* Generating REQ scaffolding -> `qgb scaffold` (Step 6).

Phase 3 Step 3.0 で `qgb detect` は廃止された (対象プロジェクトの分析は
Phase 5 スキル責務に統合)。対象プロジェクトの自己定義は init が生成する
``.quality-system/project-context.json`` (機械正本、空欄テンプレ) と
``.quality-system/knowledge/project-context.md`` (人間正本) に書く。

Idempotency and integrity:

* Default behaviour does NOT overwrite existing files. Each file is reported
  as ``created`` or ``skipped (already exists)``.
* ``force=True`` overwrites existing files. Directories are always preserved.
* ``.gitignore`` is appended (not rewritten) when the artifacts line is absent.
* When the target tree contains type collisions (a regular file at a path
  that must be a directory, or vice versa, or a non-file ``.gitignore``),
  ``run_init`` records an ``InitError`` and refuses to corrupt the tree.
  The CLI surfaces these as ``NOT_READY`` (exit 2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from typing import Literal

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

# Literal type aliases used by the report dataclasses.
FileAction = Literal["created", "skipped", "overwritten"]
GitignoreAction = Literal["created", "appended", "already-present", "skipped"]
ErrorKind = Literal[
    "path_is_file_expected_dir",
    "path_is_dir_expected_file",
    "gitignore_not_a_regular_file",
    "gitignore_unreadable",
]


@dataclass(frozen=True)
class FileOutcome:
    """What happened to a single file during init."""

    path: Path
    action: FileAction
    note: str = ""


@dataclass(frozen=True)
class InitError:
    """A structural problem that prevented init from completing safely."""

    kind: ErrorKind
    path: Path
    message: str


@dataclass
class InitReport:
    """Aggregated outcome of qgb init."""

    project_root: Path
    file_outcomes: list[FileOutcome] = field(default_factory=list)
    dirs_ensured: list[Path] = field(default_factory=list)
    gitignore_action: GitignoreAction | None = None
    errors: list[InitError] = field(default_factory=list)

    def has_problems(self) -> bool:
        return bool(self.errors)


def _read_template(name: str) -> str:
    """Read a bundled init template (kept under qgb/templates/)."""
    resource = resources.files("qgb").joinpath("templates", name)
    with resource.open("r", encoding="utf-8") as fh:
        return fh.read()


def _materialise_config(project_name: str) -> str:
    """Produce the initial config.json text with structured assignment.

    String interpolation into JSON would let exotic project names (with
    quotes, backslashes, or newlines) break the document. Parse the template
    first, then assign the project name and qgb version through Python
    objects so json.dumps performs the escaping.
    """
    data = json.loads(_read_template("config.initial.json"))
    data["project"]["name"] = project_name
    data["qgb"]["version"] = __version__
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _materialise_policy() -> str:
    raw = _read_template("policy.initial.json")
    return json.dumps(json.loads(raw), ensure_ascii=False, indent=2) + "\n"


def _materialise_project_context() -> str:
    return _read_template("project-context.initial.md")


def _materialise_project_context_json(
    *, now: datetime | None = None
) -> str:
    """Produce the initial project-context.json text.

    Phase 3 Step 3.0: 対象プロジェクトの自己定義の機械正本。空欄テンプレを
    生成し、``human_reviewed: false`` を初期値にする (人間が中身を書き、
    レビューを経て true に手で書き換える運用)。``generated_by: "human"``
    が初期値なのは、init 直後は人間が雛形を編集する想定だからで、
    補佐 Agent が後で更新する場合は agent 側がこのフィールドを
    ``"agent-assisted"`` に書き換える。

    ``now`` is injectable so tests can pin the timestamp; production code
    leaves it as ``None`` and uses ``datetime.now(timezone.utc)``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    # Strip microseconds so the generated_at matches the RFC3339 shape
    # qgb's format checker accepts (YYYY-MM-DDTHH:MM:SSZ).
    stamp = now.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")
    data = {
        "schema_version": "1.0",
        "human_reviewed": False,
        "project_kind": "",
        "purpose": "",
        "scope": {"in_scope": [], "out_of_scope": []},
        "technologies": [],
        "artifact_kinds": [],
        "platform": [],
        "non_adopted_methods": [],
        "references": [],
        "source_metadata": {
            "generated_by": "human",
            "generated_at": stamp,
        },
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def _ensure_dir(path: Path, report: InitReport) -> bool:
    """Ensure a directory exists. Returns True on success, False on collision."""
    if path.exists() and not path.is_dir():
        report.errors.append(
            InitError(
                kind="path_is_file_expected_dir",
                path=path,
                message=(
                    f"expected directory at {path}, but a non-directory entry exists"
                ),
            )
        )
        return False
    path.mkdir(parents=True, exist_ok=True)
    report.dirs_ensured.append(path)
    return True


def _write_file(
    path: Path,
    content: str,
    *,
    force: bool,
    report: InitReport,
) -> None:
    if path.exists() and not path.is_file():
        report.errors.append(
            InitError(
                kind="path_is_dir_expected_file",
                path=path,
                message=(
                    f"expected file at {path}, but a non-file entry "
                    f"(directory or other) exists"
                ),
            )
        )
        return
    if path.exists():
        if not force:
            report.file_outcomes.append(
                FileOutcome(path=path, action="skipped", note="file already exists")
            )
            return
        action: FileAction = "overwritten"
    else:
        action = "created"
    # Parent dir may be a freshly-created directory or an existing one; either
    # is fine. If parent is somehow a non-dir we'd have caught it in
    # _ensure_dir already, since every spec file lives under .quality-system/.
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    report.file_outcomes.append(FileOutcome(path=path, action=action))


def _gitignore_lines_match_entry(existing: str) -> bool:
    """Detect whether the artifacts entry is already present.

    Treats trailing slash as optional so '.quality-system/artifacts' and
    '.quality-system/artifacts/' are considered the same ignore rule.
    """
    target = _GITIGNORE_ENTRY.rstrip("/")
    for raw in existing.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.rstrip("/") == target:
            return True
    return False


def _update_gitignore(project_root: Path, report: InitReport) -> None:
    """Append the qgb artifacts entry to .gitignore (idempotent and safe)."""
    gitignore = project_root / ".gitignore"
    if gitignore.exists() and not gitignore.is_file():
        report.errors.append(
            InitError(
                kind="gitignore_not_a_regular_file",
                path=gitignore,
                message=(
                    f"{gitignore} exists but is not a regular file; "
                    f"qgb init will not modify it"
                ),
            )
        )
        report.gitignore_action = "skipped"
        return

    if gitignore.exists():
        try:
            existing = gitignore.read_text(encoding="utf-8")
        except OSError as exc:
            report.errors.append(
                InitError(
                    kind="gitignore_unreadable",
                    path=gitignore,
                    message=f"failed to read {gitignore}: {exc}",
                )
            )
            report.gitignore_action = "skipped"
            return

        if _gitignore_lines_match_entry(existing):
            report.gitignore_action = "already-present"
            return

        if existing == "":
            gitignore.write_text(
                f"{_GITIGNORE_HEADER}\n{_GITIGNORE_ENTRY}\n", encoding="utf-8"
            )
            report.gitignore_action = "appended"
            return

        suffix = "" if existing.endswith("\n") else "\n"
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

    Path-type collisions (e.g. a regular file where a directory is required)
    are recorded as ``InitError`` entries on the returned report rather than
    raising; the CLI surfaces this as exit code 2 (NOT_READY).
    """
    project_root = project_root.resolve()
    if project_name is None:
        project_name = project_root.name or "qgb-project"

    report = InitReport(project_root=project_root)

    qs = project_root / ".quality-system"
    if not _ensure_dir(qs, report):
        # Cannot proceed if the top-level directory cannot be created.
        return report

    for sub in _QS_DIRS:
        _ensure_dir(qs / sub, report)
    # Even if a subdir collides, we continue trying to write files; each
    # _write_file does its own collision check. This keeps the report
    # comprehensive instead of bailing on the first issue.

    _write_file(qs / "config.json", _materialise_config(project_name), force=force, report=report)
    _write_file(qs / "policy.json", _materialise_policy(), force=force, report=report)
    # Phase 3 Step 3.0: 機械正本の project-context.json (空欄テンプレ、
    # human_reviewed:false の初期値で書き出し、利用者または補佐 Agent が
    # 中身を埋めてレビュー後に true に変える)。
    _write_file(
        qs / "project-context.json",
        _materialise_project_context_json(),
        force=force,
        report=report,
    )
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
