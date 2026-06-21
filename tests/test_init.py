"""Tests for the init command (Step 3)."""

from __future__ import annotations

import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from qgb.cli import EXIT_NOT_READY, EXIT_OK, EXIT_USAGE, main
from qgb.core.init import FileOutcome, InitError, run_init
from qgb.core.validate import run_validate

# ---- run_init (core) -----------------------------------------------------


def test_run_init_creates_expected_layout(tmp_path: Path) -> None:
    report = run_init(tmp_path, project_name="demo")

    qs = tmp_path / ".quality-system"
    assert qs.is_dir()
    for sub in ("req", "contracts", "knowledge", "evidence", "artifacts"):
        assert (qs / sub).is_dir(), f"expected directory {sub} to be created"

    config_path = qs / "config.json"
    policy_path = qs / "policy.json"
    knowledge_path = qs / "knowledge" / "knowledge.jsonl"
    ctx_path = qs / "knowledge" / "project-context.md"

    assert config_path.is_file()
    assert policy_path.is_file()
    assert knowledge_path.is_file()
    assert ctx_path.is_file()

    # Report mirrors the filesystem.
    paths = {fo.path for fo in report.file_outcomes}
    assert config_path in paths
    assert policy_path in paths
    assert knowledge_path in paths
    assert ctx_path in paths
    # All file_outcomes for a fresh tree should be "created".
    assert all(fo.action == "created" for fo in report.file_outcomes)


def test_run_init_config_contains_project_name(tmp_path: Path) -> None:
    run_init(tmp_path, project_name="my-app")
    config = json.loads((tmp_path / ".quality-system" / "config.json").read_text("utf-8"))
    assert config["project"]["name"] == "my-app"
    assert config["schema_version"] == "1.0"
    assert config["qgb"]["core_language"] == "python"


def test_run_init_policy_starts_with_empty_stages(tmp_path: Path) -> None:
    run_init(tmp_path)
    policy = json.loads((tmp_path / ".quality-system" / "policy.json").read_text("utf-8"))
    assert policy["stages"] == []
    assert policy["policy_id"] == "default"


def test_run_init_defaults_project_name_to_basename(tmp_path: Path) -> None:
    workdir = tmp_path / "demoproj"
    workdir.mkdir()
    run_init(workdir)
    config = json.loads((workdir / ".quality-system" / "config.json").read_text("utf-8"))
    assert config["project"]["name"] == "demoproj"


def test_run_init_is_idempotent_without_force(tmp_path: Path) -> None:
    run_init(tmp_path)
    # Modify config so we can detect overwrites.
    config_path = tmp_path / ".quality-system" / "config.json"
    config_path.write_text('{"manually-edited": true}\n', encoding="utf-8")

    report = run_init(tmp_path)
    skipped = [fo for fo in report.file_outcomes if fo.path == config_path]
    assert len(skipped) == 1
    assert skipped[0].action == "skipped"
    # The manual edit must still be present.
    assert config_path.read_text("utf-8") == '{"manually-edited": true}\n'


def test_run_init_with_force_overwrites(tmp_path: Path) -> None:
    run_init(tmp_path)
    config_path = tmp_path / ".quality-system" / "config.json"
    config_path.write_text('{"manually-edited": true}\n', encoding="utf-8")

    report = run_init(tmp_path, force=True)
    overwritten = [fo for fo in report.file_outcomes if fo.path == config_path]
    assert len(overwritten) == 1
    assert overwritten[0].action == "overwritten"
    # The default content is restored.
    config = json.loads(config_path.read_text("utf-8"))
    assert config["schema_version"] == "1.0"


def test_run_init_creates_gitignore_when_missing(tmp_path: Path) -> None:
    report = run_init(tmp_path)
    gi = tmp_path / ".gitignore"
    assert gi.is_file()
    content = gi.read_text("utf-8")
    assert ".quality-system/artifacts/" in content
    assert report.gitignore_action == "created"


def test_run_init_appends_to_existing_gitignore(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text("__pycache__/\n.venv/\n", encoding="utf-8")
    report = run_init(tmp_path)
    content = gi.read_text("utf-8")
    assert "__pycache__/" in content, "pre-existing entries must be preserved"
    assert ".quality-system/artifacts/" in content
    assert report.gitignore_action == "appended"


def test_run_init_does_not_double_append_gitignore_entry(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text(".quality-system/artifacts/\n", encoding="utf-8")
    report = run_init(tmp_path)
    assert report.gitignore_action == "already-present"
    # No duplicates.
    assert gi.read_text("utf-8").count(".quality-system/artifacts/") == 1


def test_run_init_handles_gitignore_without_trailing_newline(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    gi.write_text("__pycache__/", encoding="utf-8")  # no trailing newline
    run_init(tmp_path)
    content = gi.read_text("utf-8")
    # No "__pycache__/.quality-system/" line should be created.
    assert "__pycache__/\n" in content
    assert ".quality-system/artifacts/\n" in content


# ---- integration: init followed by validate ------------------------------


def test_init_output_passes_validate(tmp_path: Path) -> None:
    """Step 4's contract: a freshly-initialised tree must validate cleanly.

    Phase 3 Step 3.0: project-context.json も init で生成されるので
    validate target set に追加 ('project-context')。
    """
    run_init(tmp_path, project_name="round-trip")
    report = run_validate(tmp_path)
    assert not report.has_problems(), report
    # After Step 9, knowledge.jsonl is also part of the validate target
    # set (Phase 1 受け入れ条件 17/18).
    # Phase 3 Step 3.0: project-context.json も追加。
    schema_names = sorted(name for _, name in report.files_checked)
    assert schema_names == ["config", "knowledge", "policy", "project-context"]


# ---- CLI: in-process via main() ------------------------------------------


def test_cli_init_creates_layout(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main(["init", "--path", str(tmp_path), "--name", "demo"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "Initialised .quality-system/" in captured.out
    assert (tmp_path / ".quality-system" / "config.json").is_file()


def test_cli_init_skipped_actions_visible(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(["init", "--path", str(tmp_path)])
    capsys.readouterr()  # discard first output
    exit_code = main(["init", "--path", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "skipped" in captured.out


def test_cli_init_force_marks_overwritten(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    main(["init", "--path", str(tmp_path)])
    capsys.readouterr()
    exit_code = main(["init", "--path", str(tmp_path), "--force"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    assert "overwritten" in captured.out


def test_cli_init_with_file_path_exits_usage(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    f = tmp_path / "not-a-dir.json"
    f.write_text("{}", encoding="utf-8")
    exit_code = main(["init", "--path", str(f)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE
    assert "directory" in captured.err.lower()


def test_cli_init_with_nonexistent_path_exits_usage(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    bogus = tmp_path / "does-not-exist"
    exit_code = main(["init", "--path", str(bogus)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_USAGE
    assert "does not exist" in captured.err


# ---- CLI: --json flag ----------------------------------------------------


def test_cli_init_json_output(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main(["init", "--path", str(tmp_path), "--name", "demo", "--json"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["project_root"] == str(tmp_path.resolve())
    assert payload["gitignore_action"] == "created"
    # No stderr noise in JSON mode.
    assert captured.err == ""
    # Confirmed file outcomes include config and policy.
    paths = {item["path"] for item in payload["files"]}
    assert any(p.endswith("config.json") for p in paths)
    assert any(p.endswith("policy.json") for p in paths)


# ---- helper unit-tests ---------------------------------------------------


def test_file_outcome_dataclass_is_frozen() -> None:
    fo = FileOutcome(path=Path("x"), action="created")
    with pytest.raises(dataclasses.FrozenInstanceError):
        fo.action = "overwritten"  # type: ignore[misc]


# ---- structural collision (path-type) handling ---------------------------


def test_run_init_reports_when_quality_system_is_a_regular_file(tmp_path: Path) -> None:
    """Codex review item 1: a file where .quality-system/ should be must NOT silently succeed."""
    (tmp_path / ".quality-system").write_text("garbage", encoding="utf-8")
    report = run_init(tmp_path)
    assert report.has_problems()
    kinds = [e.kind for e in report.errors]
    assert "path_is_file_expected_dir" in kinds
    # No bogus files should have been written.
    assert (tmp_path / ".quality-system").is_file()  # still the original sentinel.


def test_run_init_reports_when_config_path_is_a_directory(tmp_path: Path) -> None:
    """A directory at config.json's path must produce an InitError, not 'skipped'."""
    qs = tmp_path / ".quality-system"
    qs.mkdir()
    (qs / "config.json").mkdir()
    report = run_init(tmp_path)
    assert report.has_problems()
    kinds = [e.kind for e in report.errors]
    assert "path_is_dir_expected_file" in kinds
    # The other top-level files should still be attempted.
    paths_written = {o.path for o in report.file_outcomes}
    assert qs / "policy.json" in paths_written


def test_run_init_reports_when_gitignore_is_directory(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").mkdir()
    report = run_init(tmp_path)
    assert report.has_problems()
    kinds = [e.kind for e in report.errors]
    assert "gitignore_not_a_regular_file" in kinds
    assert report.gitignore_action == "skipped"


# ---- structured project_name substitution --------------------------------


@pytest.mark.parametrize(
    "name",
    [
        'a"b',
        "a\\b",
        "with spaces",
        "改行を\n含む",
        "tab\tin name",
        "日本語プロジェクト",
        '"quoted"',
    ],
)
def test_run_init_handles_special_chars_in_project_name(name: str, tmp_path: Path) -> None:
    """Codex review item 2: structured assignment must keep the config valid JSON."""
    report = run_init(tmp_path, project_name=name)
    assert not report.has_problems(), report
    config_path = tmp_path / ".quality-system" / "config.json"
    config = json.loads(config_path.read_text("utf-8"))
    assert config["project"]["name"] == name


def test_run_init_writes_qgb_version_into_config(tmp_path: Path) -> None:
    """The qgb.version field must come from importlib.metadata, not the template."""
    from qgb import __version__

    run_init(tmp_path, project_name="demo")
    config = json.loads((tmp_path / ".quality-system" / "config.json").read_text("utf-8"))
    assert config["qgb"]["version"] == __version__


# ---- .gitignore edge cases -----------------------------------------------


def test_run_init_gitignore_empty_existing_has_no_leading_blank_line(tmp_path: Path) -> None:
    """Codex review item 5: empty .gitignore must not gain a leading blank line."""
    (tmp_path / ".gitignore").write_text("", encoding="utf-8")
    run_init(tmp_path)
    content = (tmp_path / ".gitignore").read_text("utf-8")
    assert not content.startswith("\n")
    assert content.startswith("# qgb volatile artifacts")


def test_run_init_gitignore_trailing_slash_variants_are_equivalent(tmp_path: Path) -> None:
    """Codex review item 4: trailing-slash variants count as the same ignore rule."""
    (tmp_path / ".gitignore").write_text(".quality-system/artifacts\n", encoding="utf-8")
    report = run_init(tmp_path)
    assert report.gitignore_action == "already-present"


def test_run_init_gitignore_is_byte_for_byte_stable_on_second_run(tmp_path: Path) -> None:
    """Codex review item 10: a second run must not mutate .gitignore in any way."""
    run_init(tmp_path)
    first = (tmp_path / ".gitignore").read_bytes()
    run_init(tmp_path)
    second = (tmp_path / ".gitignore").read_bytes()
    assert first == second


# ---- partial-deletion recovery -------------------------------------------


def test_run_init_recovers_when_only_config_missing(tmp_path: Path) -> None:
    run_init(tmp_path)
    config_path = tmp_path / ".quality-system" / "config.json"
    policy_path = tmp_path / ".quality-system" / "policy.json"
    policy_bytes_before = policy_path.read_bytes()
    config_path.unlink()

    report = run_init(tmp_path)
    assert not report.has_problems(), report
    assert config_path.is_file()
    # Policy file must not be modified.
    assert policy_path.read_bytes() == policy_bytes_before


def test_run_init_recovers_when_knowledge_dir_missing(tmp_path: Path) -> None:
    import shutil

    run_init(tmp_path)
    knowledge_dir = tmp_path / ".quality-system" / "knowledge"
    shutil.rmtree(knowledge_dir)

    report = run_init(tmp_path)
    assert not report.has_problems(), report
    assert (knowledge_dir / "knowledge.jsonl").is_file()
    assert (knowledge_dir / "project-context.md").is_file()


# ---- CLI: NOT_READY surface ----------------------------------------------


def test_cli_init_reports_not_ready_on_collision(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / ".quality-system").write_text("oops", encoding="utf-8")
    exit_code = main(["init", "--path", str(tmp_path)])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    assert "Initialisation errors" in captured.err


def test_cli_init_json_output_includes_ok_and_summary(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    exit_code = main(["init", "--path", str(tmp_path), "--name", "demo", "--json"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_OK
    payload = json.loads(captured.out)
    assert payload["ok"] is True
    assert "summary" in payload
    assert payload["summary"]["ok"] is True
    assert payload["summary"]["errors"] == 0
    assert payload["errors"] == []


def test_cli_init_json_output_on_collision(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    (tmp_path / ".quality-system").write_text("oops", encoding="utf-8")
    exit_code = main(["init", "--path", str(tmp_path), "--json"])
    captured = capsys.readouterr()
    assert exit_code == EXIT_NOT_READY
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert payload["summary"]["ok"] is False
    assert payload["summary"]["errors"] >= 1
    kinds = {e["kind"] for e in payload["errors"]}
    assert "path_is_file_expected_dir" in kinds


def test_init_error_dataclass_is_frozen() -> None:
    err = InitError(
        kind="path_is_file_expected_dir",
        path=Path("x"),
        message="msg",
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        err.message = "other"  # type: ignore[misc]


# ---- subprocess smoke ----------------------------------------------------


def _run_qgb(*args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "qgb", *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def test_subprocess_init_then_validate(tmp_path: Path) -> None:
    init_result = _run_qgb("init", "--path", str(tmp_path), "--name", "smoke")
    assert init_result.returncode == EXIT_OK, init_result
    assert "Initialised" in init_result.stdout

    validate_result = _run_qgb("validate", "--path", str(tmp_path))
    assert validate_result.returncode == EXIT_OK, validate_result
    assert "OK:" in validate_result.stdout
