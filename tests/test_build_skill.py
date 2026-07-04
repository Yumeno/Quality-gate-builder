from __future__ import annotations

"""tests/test_build_skill.py -- Tests for tools/build_skill.py (Stage 2: VALIDATION + PARSE).

Import strategy: sys.path manipulation to import directly from tools/.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Path setup: make tools/ importable
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from build_skill import (  # noqa: E402
    CONVERTER_VERSION,
    BuildError,
    UsageError,
    MarkerBlock,
    ParseResult,
    check_agent_docs,
    check_converter_version,
    check_source_files,
    parse_markers,
    parse_semver,
    validate_and_parse,
    validate_metadata,
)

# ---------------------------------------------------------------------------
# Paths to real assets
# ---------------------------------------------------------------------------

_SKILLS_SOURCE = _REPO_ROOT / "skills" / "source"
_AGENT_DOCS_DIR = _REPO_ROOT / "development" / "docs" / "skill-converter"
_SCHEMA_PATH = _SKILLS_SOURCE / "metadata.schema.json"
_FIXTURES = _REPO_ROOT / "tests" / "fixtures" / "build-skill"


# ---------------------------------------------------------------------------
# 1. test_valid_metadata_passes
# ---------------------------------------------------------------------------


def test_valid_metadata_passes():
    """Real skills/source/metadata.yaml passes JSON-schema validation."""
    metadata = validate_metadata(_SKILLS_SOURCE, schema_path=_SCHEMA_PATH)
    assert metadata["skill_id"] == "qgb"
    assert "converter_min_version" in metadata
    assert "source_files" in metadata


# ---------------------------------------------------------------------------
# 2. test_missing_skill_id_fails
# ---------------------------------------------------------------------------


def test_missing_skill_id_fails(tmp_path):
    """metadata.yaml with no skill_id raises BuildError."""
    bad_yaml = textwrap.dedent("""\
        version: 0.1.0
        description: Missing skill_id field
        converter_min_version: 0.1.0
        source_files:
          - body.md
        build_modes:
          - full
        target_agents:
          - claude
    """)
    (tmp_path / "metadata.yaml").write_text(bad_yaml, encoding="utf-8")
    with pytest.raises(BuildError, match="skill_id"):
        validate_metadata(tmp_path, schema_path=_SCHEMA_PATH)


# ---------------------------------------------------------------------------
# 3. test_converter_version_equal_passes
# ---------------------------------------------------------------------------


def test_converter_version_equal_passes():
    """converter_min_version == CONVERTER_VERSION passes without error."""
    metadata = {"converter_min_version": CONVERTER_VERSION}
    check_converter_version(metadata)  # must not raise


# ---------------------------------------------------------------------------
# 4. test_converter_version_lower_min_refuses
# ---------------------------------------------------------------------------


def test_converter_version_lower_min_refuses():
    """converter_min_version > CONVERTER_VERSION raises BuildError."""
    # Bump the patch component to a higher value to guarantee > current.
    major, minor, patch = parse_semver(CONVERTER_VERSION)
    higher = f"{major}.{minor}.{patch + 1}"
    metadata = {"converter_min_version": higher}
    with pytest.raises(BuildError, match="older than"):
        check_converter_version(metadata)


# ---------------------------------------------------------------------------
# 5. test_converter_version_malformed_refuses
# ---------------------------------------------------------------------------


def test_converter_version_malformed_refuses():
    """converter_min_version that is not semver raises BuildError."""
    metadata = {"converter_min_version": "not.a.version"}
    with pytest.raises(BuildError, match="not a valid semver"):
        check_converter_version(metadata)


# ---------------------------------------------------------------------------
# 6. test_agent_status_all_supported_passes
# ---------------------------------------------------------------------------


def test_agent_status_all_supported_passes():
    """Real agent docs (claude + codex) both have status: supported."""
    metadata = {"target_agents": ["claude", "codex"]}
    check_agent_docs(metadata, _AGENT_DOCS_DIR)  # must not raise


# ---------------------------------------------------------------------------
# 7. test_agent_missing_doc_fails
# ---------------------------------------------------------------------------


def test_agent_missing_doc_fails(tmp_path):
    """A target_agent with no doc file raises BuildError."""
    # tmp_path is an empty directory: no agent-claude.md exists there.
    metadata = {"target_agents": ["claude"]}
    with pytest.raises(BuildError, match="Agent doc not found"):
        check_agent_docs(metadata, tmp_path)


# ---------------------------------------------------------------------------
# 8. test_agent_status_not_supported_fails
# ---------------------------------------------------------------------------


def test_agent_status_not_supported_fails(tmp_path):
    """Agent doc with status: unsupported raises BuildError."""
    doc = textwrap.dedent("""\
        ---
        agent: claude-code
        status: unsupported
        ---
        # Claude Code memo
    """)
    (tmp_path / "agent-claude.md").write_text(doc, encoding="utf-8")
    metadata = {"target_agents": ["claude"]}
    with pytest.raises(BuildError, match="not supported"):
        check_agent_docs(metadata, tmp_path)


# ---------------------------------------------------------------------------
# 9. test_fixture_duplicate_marker_fails
# ---------------------------------------------------------------------------


def test_fixture_duplicate_marker_fails():
    """duplicate-marker fixture raises BuildError (duplicate name rule)."""
    fixture_dir = _FIXTURES / "duplicate-marker"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="duplicate"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 10. test_fixture_unclosed_marker_fails
# ---------------------------------------------------------------------------


def test_fixture_unclosed_marker_fails():
    """unclosed-marker fixture raises BuildError (unclosed start marker)."""
    fixture_dir = _FIXTURES / "unclosed-marker"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="[Uu]nclosed"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 11. test_fixture_nested_marker_fails
# ---------------------------------------------------------------------------


def test_fixture_nested_marker_fails():
    """nested-marker fixture raises BuildError (nesting forbidden)."""
    fixture_dir = _FIXTURES / "nested-marker"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="nested"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 12. test_fixture_path_traversal_fails
# ---------------------------------------------------------------------------


def test_fixture_path_traversal_fails():
    """path-traversal fixture raises BuildError (.. in marker name)."""
    fixture_dir = _FIXTURES / "path-traversal"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match=r"\.\.|path"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 13. test_fixture_case_collision_fails
# ---------------------------------------------------------------------------


def test_fixture_case_collision_fails():
    """case-collision fixture raises BuildError (casefold duplicate)."""
    fixture_dir = _FIXTURES / "case-collision"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="duplicate"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 14. test_fixture_source_output_collision_fails
# ---------------------------------------------------------------------------


def test_fixture_source_output_collision_fails():
    """source-output-collision fixture raises BuildError (collides with source_files)."""
    fixture_dir = _FIXTURES / "source-output-collision"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="collides"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 15. test_fixture_empty_helper_fails
# ---------------------------------------------------------------------------


def test_fixture_empty_helper_fails():
    """empty-helper fixture raises BuildError (zero content lines)."""
    fixture_dir = _FIXTURES / "empty-helper"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="empty"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 15b. Marker-name whitelist (mirrors metadata.schema.json source_files)
# ---------------------------------------------------------------------------


def _parse_single_marker_body(name: str) -> None:
    """Parse a minimal body with one marker named *name* (test helper)."""
    text = (
        f"<!-- split:helper_start {name} -->\n"
        "content line\n"
        "<!-- split:helper_end -->\n"
    )
    parse_markers(text, source_files=["body.md"])


def test_marker_name_invalid_character_fails():
    """NAME with a character outside the whitelist (e.g. '<') is rejected."""
    with pytest.raises(BuildError, match="whitelist"):
        _parse_single_marker_body("bad<name.md")


def test_marker_name_missing_md_extension_fails():
    """NAME without the mandatory '.md' extension is rejected."""
    with pytest.raises(BuildError, match="whitelist"):
        _parse_single_marker_body("noext")


# ---------------------------------------------------------------------------
# 16. test_valid_minimal_parses_correctly
# ---------------------------------------------------------------------------


def test_valid_minimal_parses_correctly():
    """valid-minimal fixture parses to exactly 2 markers; block-comment examples ignored."""
    fixture_dir = _FIXTURES / "valid-minimal"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig", newline=""
    ).replace("\r\n", "\n").replace("\r", "\n")
    result = parse_markers(body_text, source_files=["body.md"])

    assert len(result.markers) == 2, (
        f"Expected 2 markers, got {len(result.markers)}: "
        f"{[m.name for m in result.markers]}"
    )
    assert result.markers[0].name == "helper-a.md"
    assert result.markers[1].name == "helper-b.md"

    # helper-a.md content preserved EXACTLY: leading and trailing blank
    # lines between the markers must survive (no trimming).
    assert result.markers[0].content == [
        "\n",
        "Content of helper A.\n",
        "\n",
    ]

    # helper-b.md content: two named lines, no surrounding blanks.
    assert result.markers[1].content == [
        "Line one of B.\n",
        "Line two of B.\n",
    ]

    # The example-inside-comment.md from the HTML block comment must NOT appear.
    all_names = {m.name for m in result.markers}
    assert "example-inside-comment.md" not in all_names


# ---------------------------------------------------------------------------
# 17. test_real_body_md_parses_four_markers
# ---------------------------------------------------------------------------


def test_real_body_md_parses_four_markers():
    """Real skills/source/body.md parses to exactly 4 markers in declared order."""
    body_path = _SKILLS_SOURCE / "body.md"
    body_text = body_path.read_text(encoding="utf-8-sig", newline="").replace(
        "\r\n", "\n"
    ).replace("\r", "\n")

    result = parse_markers(body_text, source_files=["body.md"])

    expected_order = [
        "workflow.md",
        "references.md",
        "prompts/design-stages.md",
        "prompts/review-policy.md",
    ]
    actual_order = [m.name for m in result.markers]
    assert actual_order == expected_order, (
        f"Expected marker order {expected_order}, got {actual_order}"
    )

    # Sanity: each block has non-zero content.
    for m in result.markers:
        assert len(m.content) > 0, f"Marker {m.name!r} has zero content lines"


# ---------------------------------------------------------------------------
# 18. test_cli_exit_code_2_on_failure
# ---------------------------------------------------------------------------


def test_cli_exit_code_2_on_failure():
    """CLI returns exit code 2 when the source dir has a parse error (unclosed marker)."""
    fixture_dir = _FIXTURES / "unclosed-marker"
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
            str(fixture_dir),
            "--check",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    # The failure must come from the unclosed marker itself, not from an
    # incidental missing repo asset (schema / agent docs are repo-level
    # defaults and must resolve even for fixture source dirs).
    assert "nclosed" in result.stderr, (
        f"Expected an unclosed-marker error, got stderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 19. test_cli_exit_code_64_on_usage_error
# ---------------------------------------------------------------------------


def test_cli_exit_code_64_on_usage_error(tmp_path):
    """CLI returns exit code 64 when --source-dir does not exist."""
    nonexistent = tmp_path / "does_not_exist"
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
            str(nonexistent),
            "--check",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64, (
        f"Expected exit code 64, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


# ---------------------------------------------------------------------------
# 20. test_cli_bare_build_fails_closed_before_stage3
# ---------------------------------------------------------------------------


def test_cli_bare_build_fails_closed_before_stage3():
    """A bare build (no --check) exits 2 until stage 3 implements generation.

    Validation itself passes on the valid-minimal fixture, but reporting
    success for a build that produced nothing would let CI misread a no-op
    as a completed build (fail-closed discipline).
    """
    fixture_dir = _FIXTURES / "valid-minimal"
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
            str(fixture_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2, (
        f"Expected exit code 2, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "not implemented" in result.stderr
