from __future__ import annotations

"""tests/test_build_skill.py -- Tests for tools/build_skill.py.

Covers Stage 2 (VALIDATION + PARSE) and Stage 3 (GENERATION: full/split
render, agent frontmatter, generator header, build_input_digest, INSTALL.md,
hooks/lint copies, path defenses, syntax verification, determinism).

Import strategy: sys.path manipulation to import directly from tools/.
"""

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup: make tools/ importable (must precede the build_skill import)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOOLS_DIR = _REPO_ROOT / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from build_skill import (  # noqa: E402
    CONVERTER_VERSION,
    BuildError,
    GenerationVerificationError,
    SourceValidationError,
    WritePolicyError,
    _check_delete_containment,
    _check_write_containment,
    _clean_cell_dir,
    _safe_write_bytes,
    _source_date_epoch_to_iso_utc,
    build_all,
    build_cell,
    build_frontmatter,
    build_generator_header,
    check_agent_docs,
    check_converter_version,
    check_source_files_bom,
    compute_build_input_digest,
    parse_markers,
    parse_semver,
    render_full,
    render_install_md,
    render_split,
    validate_and_parse,
    validate_metadata,
    validate_source_date_epoch,
    verify_generated_skill_md,
    verify_text_artifact,
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
    """metadata.yaml with no skill_id raises the SourceValidationError
    subclass (F4): a schema-validation failure is bad authored input, not
    a write-path refusal or a post-write verification failure."""
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
    with pytest.raises(SourceValidationError, match="skill_id"):
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
        encoding="utf-8-sig"
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
        encoding="utf-8-sig"
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(BuildError, match="[Uu]nclosed"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 11. test_fixture_nested_marker_fails
# ---------------------------------------------------------------------------


def test_fixture_nested_marker_fails():
    """nested-marker fixture raises SourceValidationError (F4): marker
    grammar violations are bad authored input (nesting forbidden)."""
    fixture_dir = _FIXTURES / "nested-marker"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig"
    ).replace("\r\n", "\n").replace("\r", "\n")
    with pytest.raises(SourceValidationError, match="nested"):
        parse_markers(body_text, source_files=["body.md"])


# ---------------------------------------------------------------------------
# 12. test_fixture_path_traversal_fails
# ---------------------------------------------------------------------------


def test_fixture_path_traversal_fails():
    """path-traversal fixture raises BuildError (.. in marker name)."""
    fixture_dir = _FIXTURES / "path-traversal"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig"
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
        encoding="utf-8-sig"
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
        encoding="utf-8-sig"
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
        encoding="utf-8-sig"
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
    """valid-minimal fixture parses to exactly 3 markers; block-comment examples ignored."""
    fixture_dir = _FIXTURES / "valid-minimal"
    body_text = (fixture_dir / "body.md").read_text(
        encoding="utf-8-sig"
    ).replace("\r\n", "\n").replace("\r", "\n")
    result = parse_markers(body_text, source_files=["body.md"])

    assert len(result.markers) == 3, (
        f"Expected 3 markers, got {len(result.markers)}: "
        f"{[m.name for m in result.markers]}"
    )
    assert result.markers[0].name == "helper-a.md"
    assert result.markers[1].name == "helper-b.md"
    assert result.markers[2].name == "prompts/helper-c.md"

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

    # prompts/helper-c.md content: subdirectory helper, single line.
    assert result.markers[2].content == [
        "Content of helper C (subdir).\n",
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
    body_text = body_path.read_text(encoding="utf-8-sig").replace(
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


# --- argparse-origin usage errors (Codex cross-review round 2 must-fix #3) --


def test_cli_unknown_option_exits_64_not_2():
    """An unrecognized CLI option is an argparse-origin usage error.  Before
    this fix, argparse's default error() exited 2, colliding with
    BuildError's own exit code 2 and making a CLI typo indistinguishable
    from a real build failure.  It must exit 64 (same convention as
    qgb.cli.QgbArgumentParser, reused here)."""
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--not-an-option",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64, (
        f"Expected exit code 64, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_cli_bad_option_value_exits_64():
    """An argparse value error (e.g. an option requiring a value that gets
    none) also exits 64, not argparse's default 2."""
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 64, (
        f"Expected exit code 64, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_cli_help_still_exits_0():
    """--help must keep exiting 0 (argparse's help action calls
    self.exit(0) directly, never self.error()); the exit-64 override for
    error() must not accidentally affect it."""
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit code 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "usage" in result.stdout.lower()


# ---------------------------------------------------------------------------
# 20. test_cli_bare_build_succeeds_and_writes_dist_dir
# ---------------------------------------------------------------------------


def test_cli_bare_build_succeeds_and_writes_dist_dir(tmp_path):
    """A bare build (no --check) performs the full generation build (stage 3).

    Uses --dist-dir so the test never touches the repo's real dist/ tree.
    Note: the valid-minimal fixture's metadata.yaml declares target_agents:
    [claude] only, so the agent doc lookup resolves against this repo's
    real development/docs/skill-converter/agent-claude.md (repo asset,
    same default-resolution contract as validate_and_parse).
    """
    fixture_dir = _FIXTURES / "valid-minimal"
    dist_dir = tmp_path / "dist_skills"
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
            str(fixture_dir),
            "--dist-dir",
            str(dist_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Expected exit code 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "BUILD OK" in result.stdout
    skill_md = dist_dir / "full" / "claude" / "SKILL.md"
    assert skill_md.exists()


def test_cli_build_with_max_source_date_epoch_end_to_end(tmp_path):
    """End-to-end regression for Codex cross-review round 2 must-fix #2:
    SOURCE_DATE_EPOCH=253402300799 (the new upper bound, 9999-12-31T23:59:59Z)
    must build successfully (exit 0) on every supported platform, including
    Windows where the old fromtimestamp-based conversion would have failed
    far below this value.  Asserts the generated header's build_date_utc
    line matches the exact ISO format build_generator_header emits."""
    fixture_dir = _FIXTURES / "valid-minimal"
    dist_dir = tmp_path / "dist_skills"
    child_env = dict(os.environ)
    child_env["SOURCE_DATE_EPOCH"] = "253402300799"
    result = subprocess.run(
        [
            sys.executable,
            str(_TOOLS_DIR / "build_skill.py"),
            "--source-dir",
            str(fixture_dir),
            "--dist-dir",
            str(dist_dir),
        ],
        capture_output=True,
        text=True,
        env=child_env,
    )
    assert result.returncode == 0, (
        f"Expected exit code 0, got {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    skill_md = dist_dir / "full" / "claude" / "SKILL.md"
    assert skill_md.exists()
    text = skill_md.read_text(encoding="utf-8")
    assert "build_date_utc: 9999-12-31T23:59:59Z" in text


# ---------------------------------------------------------------------------
# Stage 3: GENERATION phase tests
# ---------------------------------------------------------------------------


def _valid_minimal_parse():
    """Return (metadata, ParseResult) for the valid-minimal fixture."""
    fixture_dir = _FIXTURES / "valid-minimal"
    return validate_and_parse(fixture_dir, schema_path=_SCHEMA_PATH)


# --- full render -----------------------------------------------------------


def test_render_full_removes_only_marker_lines():
    """full render: marker start/end LINES removed, content left in place."""
    _, pr = _valid_minimal_parse()
    original_lines = pr.source_text.split("\n")
    rendered = render_full(pr.source_text, pr.markers)
    rendered_lines = rendered.split("\n")

    # Exactly 2 lines removed per marker (start + end), nothing else.
    assert len(rendered_lines) == len(original_lines) - 2 * len(pr.markers)

    # Content lines survive verbatim (spot-check a distinctive line).
    assert "Content of helper A." in rendered
    assert "Line one of B." in rendered
    assert "Content of helper C (subdir)." in rendered

    # Marker tag lines themselves must be gone (real markers only: the
    # helper-a.md / helper-b.md / prompts/helper-c.md start tags and their
    # matching end tags at column 0 with no leading whitespace).
    assert "<!-- split:helper_start helper-a.md -->" not in rendered
    assert "<!-- split:helper_start helper-b.md -->" not in rendered
    assert "<!-- split:helper_start prompts/helper-c.md -->" not in rendered
    # But the block-comment examples (never real markers, per the parser's
    # own grammar: indented "  <!-- split:helper_end -->" and the nested
    # start tag inside an open HTML comment) must survive verbatim, since
    # render_full only strips LINES that parse_markers recognized as real
    # start/end marker lines.
    assert "<!-- split:helper_start example-inside-comment.md -->" in rendered
    assert "  <!-- split:helper_end -->" in rendered


# --- split render ------------------------------------------------------------


def test_render_split_produces_exactly_one_see_line_per_marker():
    """split render: each marker replaced by exactly one '@see <name>' line."""
    _, pr = _valid_minimal_parse()
    body, helpers = render_split(pr.source_text, pr.markers)

    for mb in pr.markers:
        see_line = f"@see {mb.name}"
        assert body.count(see_line) == 1, (
            f"Expected exactly one {see_line!r} line, "
            f"found {body.count(see_line)}"
        )

    # Marker tag lines and inline content must not appear in the body.
    assert "<!-- split:helper_start helper-a.md -->" not in body
    assert "Content of helper A." not in body


def test_render_split_helper_content_matches_marker_block_verbatim():
    """Helper content returned by render_split equals MarkerBlock.content joined."""
    _, pr = _valid_minimal_parse()
    _, helpers = render_split(pr.source_text, pr.markers)

    for mb in pr.markers:
        assert helpers[mb.name] == "".join(mb.content)


def test_render_split_subdir_helper_present():
    """The prompts/helper-c.md subdirectory marker round-trips through render_split."""
    _, pr = _valid_minimal_parse()
    _, helpers = render_split(pr.source_text, pr.markers)
    assert "prompts/helper-c.md" in helpers
    assert helpers["prompts/helper-c.md"] == "Content of helper C (subdir).\n"


def test_build_cell_split_writes_helper_files_including_subdir(tmp_path):
    """build_cell in split mode writes helper files, including a subdir helper."""
    metadata, pr = _valid_minimal_parse()
    dist_dir = tmp_path / "dist_skills"
    cell = build_cell(
        mode="split",
        agent="claude",
        source_dir=_FIXTURES / "valid-minimal",
        dist_dir=dist_dir,
        metadata=metadata,
        parse_result=pr,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        repo_root=_REPO_ROOT,
        source_date_epoch=None,
    )
    helper_a = cell.cell_dir / "helper-a.md"
    helper_b = cell.cell_dir / "helper-b.md"
    helper_c = cell.cell_dir / "prompts" / "helper-c.md"
    assert helper_a.exists()
    assert helper_b.exists()
    assert helper_c.exists()
    assert helper_c.parent.is_dir()

    # Helper content = generator header + verbatim marker content.
    text = helper_c.read_text(encoding="utf-8")
    assert text.endswith("Content of helper C (subdir).\n")
    assert "GENERATED FILE" in text

    # Enumeration order in files_written follows marker appearance order.
    names_written = [
        str(p.relative_to(cell.cell_dir)).replace(os.sep, "/")
        for p in cell.files_written
    ]
    idx_a = names_written.index("helper-a.md")
    idx_b = names_written.index("helper-b.md")
    idx_c = [i for i, n in enumerate(names_written) if n.endswith("helper-c.md")][0]
    assert idx_a < idx_b < idx_c


# --- frontmatter -------------------------------------------------------------


def _parse_frontmatter_block(fm_text: str) -> dict:
    """Extract and YAML-parse the body between the leading/trailing '---' lines."""
    return yaml.safe_load(fm_text.split("---\n")[1].rsplit("---", 1)[0])


def test_frontmatter_claude_vs_codex_key_sets_differ():
    """Claude frontmatter has extra keys (allowed-tools, disable-model-invocation);
    Codex frontmatter has only the confirmed key set (name, description)."""
    metadata = {"skill_id": "qgb", "description": "Test description."}
    claude_fm_text = build_frontmatter("claude", metadata)
    codex_fm_text = build_frontmatter("codex", metadata)

    claude_fm = _parse_frontmatter_block(claude_fm_text)
    codex_fm = _parse_frontmatter_block(codex_fm_text)

    assert set(claude_fm.keys()) == {
        "name",
        "description",
        "allowed-tools",
        "disable-model-invocation",
    }
    assert set(codex_fm.keys()) == {"name", "description"}
    assert "allowed-tools" not in codex_fm


def test_frontmatter_key_order_is_declaration_order():
    """Frontmatter YAML key order matches the declared order (not alphabetical)."""
    metadata = {"skill_id": "qgb", "description": "Test description."}
    claude_fm_text = build_frontmatter("claude", metadata)
    fm_body = claude_fm_text.split("---\n")[1].rsplit("---", 1)[0]
    # Extract top-level keys in file order (lines not indented, ending with ':').
    keys_in_order = [
        line.split(":", 1)[0]
        for line in fm_body.splitlines()
        if line and not line.startswith((" ", "-")) and ":" in line
    ]
    assert keys_in_order == [
        "name",
        "description",
        "allowed-tools",
        "disable-model-invocation",
    ]


def test_frontmatter_description_comes_from_metadata():
    """description value in frontmatter matches metadata.yaml's description field."""
    metadata = {"skill_id": "qgb", "description": "Unique marker description XYZ."}
    fm_text = build_frontmatter("claude", metadata)
    fm_body = fm_text.split("---\n")[1].rsplit("---", 1)[0]
    fm = yaml.safe_load(fm_body)
    assert fm["description"] == "Unique marker description XYZ."


# --- generator header ---------------------------------------------------------


def test_generator_header_present_in_skill_md(tmp_path):
    """Generated SKILL.md contains the generator header after frontmatter."""
    metadata, pr = _valid_minimal_parse()
    dist_dir = tmp_path / "dist_skills"
    cell = build_cell(
        mode="full",
        agent="claude",
        source_dir=_FIXTURES / "valid-minimal",
        dist_dir=dist_dir,
        metadata=metadata,
        parse_result=pr,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        repo_root=_REPO_ROOT,
        source_date_epoch=None,
    )
    text = (cell.cell_dir / "SKILL.md").read_text(encoding="utf-8")
    assert "GENERATED FILE - DO NOT EDIT" in text
    assert f"converter_version: {CONVERTER_VERSION}" in text
    assert "build_input_digest:" in text
    assert "build_date_utc" not in text  # SOURCE_DATE_EPOCH unset


def test_generator_header_absent_in_copied_hooks_and_lint(tmp_path):
    """Copied hook/lint files carry no generator header (byte-verbatim copy)."""
    metadata, pr = validate_and_parse(_SKILLS_SOURCE, schema_path=_SCHEMA_PATH)
    dist_dir = tmp_path / "dist_skills"
    cell = build_cell(
        mode="full",
        agent="claude",
        source_dir=_SKILLS_SOURCE,
        dist_dir=dist_dir,
        metadata=metadata,
        parse_result=pr,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        repo_root=_REPO_ROOT,
        source_date_epoch=None,
    )
    hook_file = cell.cell_dir / "hooks" / "settings.example.json"
    assert hook_file.exists()
    text = hook_file.read_text(encoding="utf-8")
    assert "GENERATED FILE" not in text

    lint_file = cell.cell_dir / "lint" / "check-command-contract.py"
    assert lint_file.exists()
    lint_text = lint_file.read_text(encoding="utf-8")
    assert "GENERATED FILE" not in lint_text

    # Byte-verbatim: copied content matches the source file exactly.
    source_hook = _SKILLS_SOURCE / "hooks" / "claude-code" / "settings.example.json"
    assert hook_file.read_bytes() == source_hook.read_bytes()


def test_generator_header_no_build_date_when_epoch_unset(monkeypatch):
    """build_date_utc line is absent when SOURCE_DATE_EPOCH is unset."""
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    header = build_generator_header(build_input_digest="a" * 64, source_date_epoch=None)
    assert "build_date_utc" not in header


def test_generator_header_build_date_present_when_epoch_set(monkeypatch):
    """build_date_utc line is present with the correct ISO value when SOURCE_DATE_EPOCH is set."""
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1735689600")
    epoch = validate_source_date_epoch(os.environ["SOURCE_DATE_EPOCH"])
    header = build_generator_header(build_input_digest="a" * 64, source_date_epoch=epoch)
    assert "build_date_utc: 2025-01-01T00:00:00Z" in header


# --- build_input_digest --------------------------------------------------


def test_digest_two_builds_same_input_same_digest():
    """Two digest computations over the same inputs produce the same digest."""
    metadata, _ = _valid_minimal_parse()
    kwargs = dict(
        source_dir=_FIXTURES / "valid-minimal",
        metadata=metadata,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        converter_path=_TOOLS_DIR / "build_skill.py",
        repo_root=_REPO_ROOT,
        source_date_epoch=None,
    )
    d1 = compute_build_input_digest(**kwargs)
    d2 = compute_build_input_digest(**kwargs)
    assert d1 == d2


def test_digest_changes_when_hook_file_byte_flipped(tmp_path):
    """Flipping 1 byte in a category-4 hook file changes the digest.

    All digest inputs (source_dir, schema_path, agent_docs_dir, converter
    source) are mirrored under one tmp repo_root, so path-relativization
    stays consistent (compute_build_input_digest requires every input path
    to resolve under repo_root).
    """
    import shutil as _shutil

    tmp_repo_root = tmp_path / "tmp_repo"
    src_copy = tmp_repo_root / "skills" / "source"
    agent_docs_copy = tmp_repo_root / "development" / "docs" / "skill-converter"
    tools_copy = tmp_repo_root / "tools"
    _shutil.copytree(_SKILLS_SOURCE, src_copy)
    _shutil.copytree(_AGENT_DOCS_DIR, agent_docs_copy)
    tools_copy.mkdir(parents=True)
    _shutil.copy2(_TOOLS_DIR / "build_skill.py", tools_copy / "build_skill.py")

    schema_copy = src_copy / "metadata.schema.json"
    metadata, _ = validate_and_parse(src_copy, schema_path=schema_copy)

    kwargs = dict(
        metadata=metadata,
        schema_path=schema_copy,
        agent_docs_dir=agent_docs_copy,
        converter_path=tools_copy / "build_skill.py",
        repo_root=tmp_repo_root,
        source_date_epoch=None,
    )
    d_before = compute_build_input_digest(source_dir=src_copy, **kwargs)

    hook_file = src_copy / "hooks" / "claude-code" / "settings.example.json"
    data = bytearray(hook_file.read_bytes())
    # Flip one byte (safe: this is JSON prose text, flip a printable char).
    data[10] ^= 0x01
    hook_file.write_bytes(bytes(data))

    d_after = compute_build_input_digest(source_dir=src_copy, **kwargs)
    assert d_before != d_after


def test_digest_length_prefix_resolves_old_format_collision(tmp_path):
    """F3 (2026-07-04 review Medium): port the lens-1 repro.  Two crafted
    manifests that collided under the OLD concat format
    ("<cat>\\n<path>\\n<content>\\n", no length prefixes) must now produce
    DIFFERENT digests under the length-prefixed format, because a
    single file's content can no longer be crafted to forge a
    category/path/content boundary and impersonate two separate files.

    Scenario: source_files = ["a.md"] with content crafted to contain the
    exact bytes that a second category-3 entry (path "b.md", some
    content) would have produced under the old format, vs
    source_files = ["a.md", "b.md"] with the content actually split
    across two real files.  Under the OLD format these two source
    dirs produced byte-identical category-3 manifest contributions
    (verified separately); under the NEW length-prefixed format they
    must differ.
    """
    import shutil as _shutil

    def _build_repo_root(root: Path, source_files: list[str], contents: dict[str, bytes]):
        src = root / "skills" / "source"
        src.mkdir(parents=True)
        for rel, data in contents.items():
            (src / rel).write_bytes(data)
        metadata_yaml = (
            "skill_id: qgb\n"
            "version: 0.1.0\n"
            "description: test\n"
            "converter_min_version: 0.1.0\n"
            "source_files:\n"
            + "".join(f"  - {rel}\n" for rel in source_files)
            + "build_modes:\n  - full\n"
            "target_agents:\n  - claude\n"
        )
        (src / "metadata.yaml").write_text(metadata_yaml, encoding="utf-8")
        _shutil.copy2(_SCHEMA_PATH, src / "metadata.schema.json")

        agent_docs = root / "development" / "docs" / "skill-converter"
        agent_docs.mkdir(parents=True)
        _shutil.copy2(_AGENT_DOCS_DIR / "agent-claude.md", agent_docs / "agent-claude.md")

        tools_dir = root / "tools"
        tools_dir.mkdir(parents=True)
        _shutil.copy2(_TOOLS_DIR / "build_skill.py", tools_dir / "build_skill.py")
        return src, agent_docs, tools_dir

    # Under the OLD format ("<cat>\n<path>\n<content>\n"), a single
    # category-3 entry with path "a.md" and this content is
    # byte-identical to two entries (path "a.md" content "X", then
    # path "b.md" content "Y") concatenated back to back.
    forged_content = b"X\n3\nb.md\nY"

    root_one = tmp_path / "one_file"
    src_one, agent_docs_one, tools_one = _build_repo_root(
        root_one, ["a.md"], {"a.md": forged_content}
    )
    metadata_one, _ = validate_and_parse(
        src_one, agent_docs_dir=agent_docs_one, schema_path=src_one / "metadata.schema.json"
    )
    digest_one = compute_build_input_digest(
        source_dir=src_one,
        metadata=metadata_one,
        schema_path=src_one / "metadata.schema.json",
        agent_docs_dir=agent_docs_one,
        converter_path=tools_one / "build_skill.py",
        repo_root=root_one,
        source_date_epoch=None,
    )

    root_two = tmp_path / "two_files"
    src_two, agent_docs_two, tools_two = _build_repo_root(
        root_two, ["a.md", "b.md"], {"a.md": b"X", "b.md": b"Y"}
    )
    metadata_two, _ = validate_and_parse(
        src_two, agent_docs_dir=agent_docs_two, schema_path=src_two / "metadata.schema.json"
    )
    digest_two = compute_build_input_digest(
        source_dir=src_two,
        metadata=metadata_two,
        schema_path=src_two / "metadata.schema.json",
        agent_docs_dir=agent_docs_two,
        converter_path=tools_two / "build_skill.py",
        repo_root=root_two,
        source_date_epoch=None,
    )

    assert digest_one != digest_two, (
        "digest collision reproduced: the length-prefixed format (F3) "
        "should make a single crafted file's content unable to forge a "
        "category-3 file-boundary and impersonate two separate files"
    )


def test_digest_differs_with_source_date_epoch_set_vs_unset():
    """SOURCE_DATE_EPOCH set vs unset produces a different digest (category 8)."""
    metadata, _ = _valid_minimal_parse()
    kwargs = dict(
        source_dir=_FIXTURES / "valid-minimal",
        metadata=metadata,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        converter_path=_TOOLS_DIR / "build_skill.py",
        repo_root=_REPO_ROOT,
    )
    d_unset = compute_build_input_digest(source_date_epoch=None, **kwargs)
    d_set = compute_build_input_digest(source_date_epoch=1735689600, **kwargs)
    assert d_unset != d_set


# --- SOURCE_DATE_EPOCH validation ------------------------------------------


def test_source_date_epoch_valid_decimal_accepted():
    assert validate_source_date_epoch("12345") == 12345


def test_source_date_epoch_none_returns_none():
    assert validate_source_date_epoch(None) is None


@pytest.mark.parametrize(
    "raw",
    ["+1", " 1", "1 ", "1.5", "0x10", "-1", str(2**63)],
)
def test_source_date_epoch_invalid_forms_rejected(raw):
    with pytest.raises(BuildError):
        validate_source_date_epoch(raw)


def test_source_date_epoch_max_boundary_accepted():
    """253402300799 == 9999-12-31T23:59:59Z, the max ISO-8601 4-digit-year
    instant.  Codex cross-review round 2 must-fix #2: the bound was
    tightened from 2**63-1 down to this value because a value accepted by
    the old bound could traceback in _source_date_epoch_to_iso_utc well
    before 2**63-1 (and even lower on Windows), i.e. AFTER build_cell had
    already cleaned a stale cell dir -- a partial-state, non-exit-2
    failure.  253402300799 is the new, tightly-matched upper bound."""
    assert validate_source_date_epoch("253402300799") == 253402300799


def test_source_date_epoch_above_new_max_rejected():
    """253402300800 (one second past 9999-12-31T23:59:59Z) is rejected."""
    with pytest.raises(BuildError):
        validate_source_date_epoch("253402300800")


def test_source_date_epoch_to_iso_utc_at_new_max_boundary():
    """_source_date_epoch_to_iso_utc converts the new max bound without
    raising, on every supported platform (including Windows, whose C
    runtime's localtime/gmtime cannot represent year 9999 -- this is
    exactly why the conversion is built from timedelta arithmetic on top
    of the epoch origin rather than datetime.fromtimestamp)."""
    assert _source_date_epoch_to_iso_utc(253402300799) == "9999-12-31T23:59:59Z"


# --- determinism: two consecutive builds byte-identical --------------------


def _walk_files(root: Path) -> dict[str, Path]:
    result = {}
    for p in root.rglob("*"):
        if p.is_file():
            result[str(p.relative_to(root)).replace(os.sep, "/")] = p
    return result


def test_two_consecutive_builds_are_byte_identical(tmp_path):
    """Two builds into two different tmp dist dirs produce byte-identical trees."""
    dist_a = tmp_path / "dist_a"
    dist_b = tmp_path / "dist_b"

    build_all(source_dir=_SKILLS_SOURCE, dist_dir=dist_a, repo_root=_REPO_ROOT)
    build_all(source_dir=_SKILLS_SOURCE, dist_dir=dist_b, repo_root=_REPO_ROOT)

    files_a = _walk_files(dist_a)
    files_b = _walk_files(dist_b)
    assert set(files_a.keys()) == set(files_b.keys())

    mismatches = [
        rel
        for rel, pa in files_a.items()
        if pa.read_bytes() != files_b[rel].read_bytes()
    ]
    assert mismatches == [], f"Byte mismatches in: {mismatches}"


def test_full_build_produces_four_cells(tmp_path):
    """build_all on the real skills/source produces all 4 (mode, agent) cells."""
    dist_dir = tmp_path / "dist_skills"
    summary = build_all(source_dir=_SKILLS_SOURCE, dist_dir=dist_dir, repo_root=_REPO_ROOT)
    cells = {(c.mode, c.agent) for c in summary.cells}
    assert cells == {
        ("full", "claude"),
        ("full", "codex"),
        ("split", "claude"),
        ("split", "codex"),
    }
    for c in summary.cells:
        assert (c.cell_dir / "SKILL.md").exists()
        assert (c.cell_dir / "INSTALL.md").exists()


# --- clean build -------------------------------------------------------------


def test_clean_build_removes_stale_file(tmp_path):
    """A stale file pre-created in a dist cell is gone after build."""
    dist_dir = tmp_path / "dist_skills"
    cell_dir = dist_dir / "full" / "claude"
    cell_dir.mkdir(parents=True)
    stale = cell_dir / "stale-leftover.md"
    stale.write_text("should be removed", encoding="utf-8")

    metadata, pr = _valid_minimal_parse()
    build_cell(
        mode="full",
        agent="claude",
        source_dir=_FIXTURES / "valid-minimal",
        dist_dir=dist_dir,
        metadata=metadata,
        parse_result=pr,
        schema_path=_SCHEMA_PATH,
        agent_docs_dir=_AGENT_DOCS_DIR,
        repo_root=_REPO_ROOT,
        source_date_epoch=None,
    )
    assert not stale.exists()


# --- path defense ------------------------------------------------------------


def test_safe_write_bytes_rejects_target_outside_dist_root(tmp_path):
    """_safe_write_bytes refuses a target outside the dist root, raising
    WritePolicyError (F4): the write path itself said no, distinct from
    bad authored input or a broken rendered artifact."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    outside_target = tmp_path / "outside" / "evil.md"
    with pytest.raises(WritePolicyError, match="outside dist root"):
        _safe_write_bytes(dist_root, outside_target, b"evil content")


def test_check_write_containment_rejects_target_outside_dist_root(tmp_path):
    """_check_write_containment (F5: extracted pure containment policy)
    raises WritePolicyError directly, with no write side effects."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    outside_target = tmp_path / "outside" / "evil.md"
    with pytest.raises(WritePolicyError, match="outside dist root"):
        _check_write_containment(dist_root, outside_target)
    assert not outside_target.exists()


def test_check_write_containment_accepts_target_inside_dist_root(tmp_path):
    """_check_write_containment does not raise for an in-root target."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    target = dist_root / "sub" / "file.md"
    target.parent.mkdir(parents=True)
    _check_write_containment(dist_root, target)  # must not raise


def test_safe_write_bytes_writes_inside_dist_root(tmp_path):
    """_safe_write_bytes succeeds for a target inside the dist root."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    target = dist_root / "sub" / "file.md"
    _safe_write_bytes(dist_root, target, b"hello")
    assert target.read_bytes() == b"hello"


def test_safe_write_bytes_refuses_to_overwrite_existing_file(tmp_path):
    """_safe_write_bytes refuses to write over an existing path (clean-build
    invariant), raising WritePolicyError (F4)."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    target = dist_root / "file.md"
    target.write_text("existing", encoding="utf-8")
    with pytest.raises(WritePolicyError):
        _safe_write_bytes(dist_root, target, b"new content")


def test_safe_write_bytes_refuses_hardlink_at_target(tmp_path):
    """_safe_write_bytes refuses to write to a target path that is already a
    hardlink to another file (F9 test blind spot): the pre-create os.lstat
    absence check already refuses ANY existing path, hardlink or not, so
    this exercises that the hardlink case specifically hits the same
    clean-build-invariant refusal (not e.g. silently succeeding and
    corrupting the other hardlinked name)."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    other = tmp_path / "other-file.md"
    other.write_text("other content", encoding="utf-8")
    target = dist_root / "file.md"
    try:
        os.link(str(other), str(target))
    except OSError:
        pytest.skip("os.link is not available/permitted on this filesystem")
    with pytest.raises(WritePolicyError):
        _safe_write_bytes(dist_root, target, b"new content")
    # The other hardlinked name must be untouched by the refused write.
    assert other.read_text(encoding="utf-8") == "other content"


def test_safe_write_bytes_refuses_symlink_at_target(tmp_path):
    """_safe_write_bytes refuses a target path that is a symlink (POSIX;
    skipped where symlink creation is not permitted, e.g. Windows without
    Developer Mode / elevation) -- F9 test blind spot."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    other = tmp_path / "other-file.md"
    other.write_text("other content", encoding="utf-8")
    target = dist_root / "file.md"
    try:
        os.symlink(str(other), str(target))
    except OSError:
        pytest.skip("os.symlink is not available/permitted on this platform")
    with pytest.raises(WritePolicyError):
        _safe_write_bytes(dist_root, target, b"new content")
    assert other.read_text(encoding="utf-8") == "other content"


# --- delete-path containment (Codex cross-review round 2 must-fix #1) -------


def test_check_delete_containment_rejects_target_outside_dist_root(tmp_path):
    """_check_delete_containment refuses a target outside the dist root,
    mirroring _check_write_containment's literal-path containment check."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    outside_target = tmp_path / "outside" / "cell"
    with pytest.raises(WritePolicyError, match="outside dist root"):
        _check_delete_containment(dist_root, outside_target)


def test_check_delete_containment_accepts_target_inside_dist_root(tmp_path):
    """_check_delete_containment does not raise for a plain in-root target."""
    dist_root = tmp_path / "dist_skills"
    cell_dir = dist_root / "full" / "claude"
    cell_dir.mkdir(parents=True)
    _check_delete_containment(dist_root, cell_dir)  # must not raise


def test_check_delete_containment_rejects_symlinked_intermediate_component(
    tmp_path,
):
    """A symlinked intermediate component between dist_root and target is
    refused unconditionally by the no-symlink-component walk (must-fix #1's
    third check), even when its realpath resolves back INSIDE dist_root --
    i.e. even a case the literal + realpath containment checks alone (checks
    1-2) would consider safe still trips the walk, because rmtree follows
    the symlink at the filesystem level, not the realpath level."""
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()
    real_mode_dir = dist_root / "real_mode_dir"
    real_mode_dir.mkdir()
    symlinked_mode = dist_root / "full"
    try:
        os.symlink(str(real_mode_dir), str(symlinked_mode), target_is_directory=True)
    except OSError:
        pytest.skip("os.symlink is not available/permitted on this platform")
    cell_dir = symlinked_mode / "claude"
    with pytest.raises(WritePolicyError, match="symlink"):
        _check_delete_containment(dist_root, cell_dir)


def test_clean_cell_dir_refuses_rmtree_through_symlinked_parent_and_preserves_external_content(
    tmp_path,
):
    """Regression for Codex cross-review round 2 must-fix #1: before this
    fix, _clean_cell_dir called shutil.rmtree(cell_dir) with NO containment
    check at all.  If dist_dir/<mode> were a symlink pointing outside the
    dist tree, rmtree would recursively delete the EXTERNAL target instead
    of build output.  This test builds exactly that setup and asserts (a)
    the clean step now raises WritePolicyError instead of deleting anything,
    and (b) the external sentinel file the symlink points at is untouched.
    """
    dist_root = tmp_path / "dist_skills"
    dist_root.mkdir()

    external_dir = tmp_path / "external_target"
    external_dir.mkdir()
    sentinel = external_dir / "sentinel.txt"
    sentinel.write_text("do not delete me", encoding="utf-8")

    symlinked_mode_dir = dist_root / "full"
    try:
        os.symlink(
            str(external_dir), str(symlinked_mode_dir), target_is_directory=True
        )
    except OSError:
        pytest.skip("os.symlink is not available/permitted on this platform")

    cell_dir = symlinked_mode_dir / "claude"

    with pytest.raises(WritePolicyError):
        _clean_cell_dir(dist_root, cell_dir)

    # The external sentinel file must still exist: the fix must refuse
    # BEFORE any rmtree call, not attempt-then-catch after damage is done.
    assert sentinel.exists()
    assert sentinel.read_text(encoding="utf-8") == "do not delete me"


def test_clean_cell_dir_still_removes_stale_plain_dir(tmp_path):
    """Sanity check: _clean_cell_dir's normal (no-symlink) path still works
    after adding the containment check -- a plain stale directory inside
    dist_root is removed and recreated empty."""
    dist_root = tmp_path / "dist_skills"
    cell_dir = dist_root / "full" / "claude"
    cell_dir.mkdir(parents=True)
    stale = cell_dir / "stale.md"
    stale.write_text("stale", encoding="utf-8")

    _clean_cell_dir(dist_root, cell_dir)

    assert cell_dir.exists()
    assert not stale.exists()
    assert list(cell_dir.iterdir()) == []


# --- BOM guard on authored source_files (F7) ---------------------------------


def test_check_source_files_bom_rejects_bom_prefixed_source(tmp_path):
    """check_source_files_bom raises SourceValidationError when a
    source_files entry starts with a UTF-8 BOM (EF BB BF)."""
    (tmp_path / "body.md").write_bytes(b"\xef\xbb\xbfHello, this is BOM-prefixed.\n")
    metadata = {"source_files": ["body.md"]}
    with pytest.raises(SourceValidationError, match="BOM"):
        check_source_files_bom(metadata, tmp_path)


def test_check_source_files_bom_accepts_bom_less_source(tmp_path):
    """check_source_files_bom does not raise for a BOM-less source file."""
    (tmp_path / "body.md").write_bytes(b"Hello, no BOM here.\n")
    metadata = {"source_files": ["body.md"]}
    check_source_files_bom(metadata, tmp_path)  # must not raise


# --- syntax verification -----------------------------------------------------


def test_verify_generated_skill_md_catches_broken_frontmatter():
    """verify_generated_skill_md raises GenerationVerificationError (F4) on
    unparsable YAML frontmatter: this is a post-write syntax verification
    failure, distinct from bad authored input or a write-path refusal."""
    broken = "---\nname: [unclosed\n---\nBody content.\n"
    with pytest.raises(GenerationVerificationError):
        verify_generated_skill_md(broken, expected_keys={"name"})


def test_verify_generated_skill_md_catches_missing_expected_key():
    """verify_generated_skill_md raises BuildError when an expected key is absent."""
    text = "---\nname: qgb\n---\nBody content.\n"
    with pytest.raises(BuildError, match="missing expected keys"):
        verify_generated_skill_md(text, expected_keys={"name", "description"})


def test_verify_generated_skill_md_catches_unclosed_frontmatter():
    """verify_generated_skill_md raises BuildError when frontmatter never closes."""
    text = "---\nname: qgb\nBody without closing marker.\n"
    with pytest.raises(BuildError, match="never closes"):
        verify_generated_skill_md(text, expected_keys={"name"})


def test_verify_text_artifact_catches_empty_content():
    with pytest.raises(BuildError, match="empty"):
        verify_text_artifact("   \n  ", label="test artifact")


def test_verify_text_artifact_catches_nul_byte():
    with pytest.raises(BuildError, match="NUL"):
        verify_text_artifact("hello\x00world", label="test artifact")


# --- INSTALL.md --------------------------------------------------------------


def test_install_md_mentions_placement_paths_and_lint():
    metadata = {"skill_id": "qgb"}
    text = render_install_md(agent="claude", mode="full", metadata=metadata)
    assert "~/.claude/skills/qgb/" in text
    assert ".claude/skills/qgb/" in text
    assert "lint" in text
    assert "hooks" in text


def test_install_md_codex_paths():
    metadata = {"skill_id": "qgb"}
    text = render_install_md(agent="codex", mode="split", metadata=metadata)
    assert "~/.agents/skills/qgb/" in text
    assert ".agents/skills/qgb/" in text
    # Split mode mentions helper files explicitly.
    assert "helper" in text.lower()
