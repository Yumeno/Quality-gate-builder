"""build_skill.py -- Phase 5 Step 5.b: converter for skills/source/ -> dist/skills/.

Stage 2 (VALIDATION + PARSE) + Stage 3 (GENERATION) are both implemented here.
A bare invocation (no --check) now performs a full deterministic build across
all build_modes x target_agents declared in metadata.yaml.

Exit codes:
  0  -- success (--check passed, or a full build completed)
  2  -- validation / parse / generation failure (BuildError)
  64 -- usage error (UsageError)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------

CONVERTER_VERSION = "0.1.0"

# ---------------------------------------------------------------------------
# Repo-relative defaults
#
# build_skill.py is a repo-bound tool (it lives in <repo_root>/tools/).
# The metadata schema and the agent capability docs are part of THIS repo,
# not of the source dir being built: test fixtures carry only their own
# metadata.yaml + body.md, while the schema is always loaded from
# skills/source/metadata.schema.json and agent docs from
# development/docs/skill-converter/ unless explicitly overridden.
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCHEMA_PATH = _REPO_ROOT / "skills" / "source" / "metadata.schema.json"
DEFAULT_AGENT_DOCS_DIR = _REPO_ROOT / "development" / "docs" / "skill-converter"
DEFAULT_SOURCE_DIR = _REPO_ROOT / "skills" / "source"
DEFAULT_DIST_DIR = _REPO_ROOT / "dist" / "skills"

# skills/source/hooks/<dirname> -> target_agents short name mapping is the
# inverse of this table.  The source tree's hook directories are named after
# the human-facing agent product ("claude-code", "codex") while
# metadata.yaml#target_agents / dist/skills/<mode>/<agent>/ use the short
# agent key ("claude", "codex").  Codex K=2 r2 spec fix #2.
AGENT_TO_HOOK_DIRNAME = {
    "claude": "claude-code",
    "codex": "codex",
}

# Agent-independent lint bundle, copied verbatim into every agent/mode cell.
LINT_SOURCE_DIRNAME = "lint"

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BuildError(Exception):
    """Raised for validation / parse failures (exit code 2)."""


class UsageError(Exception):
    """Raised for CLI usage errors (exit code 64)."""


# ---------------------------------------------------------------------------
# Helpers: semver
# ---------------------------------------------------------------------------


def parse_semver(s: str) -> tuple[int, int, int]:
    """Parse a strict three-part semver string 'X.Y.Z' into (major, minor, patch).

    Raises ValueError if the string does not match X.Y.Z where each part is
    a non-negative integer.  Pre-release / build-metadata suffixes are NOT
    accepted here (converter_min_version must be bare).
    """
    pattern = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
    m = pattern.match(s)
    if not m:
        raise ValueError(f"Not a valid semver: {s!r}")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class MarkerBlock:
    """One parsed split:helper_start / helper_end pair.

    Attributes:
        name       -- The NAME from <!-- split:helper_start NAME -->.
        start_line -- 1-based line number of the start marker line.
        end_line   -- 1-based line number of the end marker line.
        content    -- Lines strictly between start and end markers.
                      Each element is the raw line string INCLUDING its
                      trailing newline character (\\n) if present, so that
                      stage 3 can write them back verbatim.  An empty list
                      means zero content lines (empty-helper error is caught
                      during parse).
    """

    name: str
    start_line: int
    end_line: int
    content: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    """Result returned by parse_markers().

    Attributes:
        markers     -- Ordered list of MarkerBlock (appearance order).
        source_text -- The full text of body.md as read (after universal
                       newline translation applied by open(..., newline='\\n')).
    """

    markers: list[MarkerBlock]
    source_text: str


# ---------------------------------------------------------------------------
# Internal: path safety for marker NAMEs
# ---------------------------------------------------------------------------

_RE_CONSEC_SLASH = re.compile(r"//")
_RE_DOTDOT_SEG = re.compile(r"(^|/)\.\.(/|$)")
_RE_DOTSLASH = re.compile(r"(^|/)\./")

# Whitelist for marker NAMEs.  This mirrors the source_files items pattern
# in skills/source/metadata.schema.json (the spec requires the same
# discipline for marker names): path segments of [A-Za-z0-9][A-Za-z0-9_-]*
# joined by single '/', with a mandatory '.md' extension.  Everything else
# (spaces, '<', non-ASCII, missing extension, dots inside segments, ...)
# is rejected.  Keep in sync with metadata.schema.json.
_RE_NAME_WHITELIST = re.compile(
    r"^(?!.*//)(?!.*/\.\.?/)(?!.*/\.\.?$)(?!\.\.?/)"
    r"[A-Za-z0-9][A-Za-z0-9_-]*(?:/[A-Za-z0-9][A-Za-z0-9_-]*)*\.md$"
)


def _check_name_path_safety(name: str, line_no: int) -> None:
    """Raise BuildError if NAME fails the helper-name path rules.

    The blacklist checks below produce specific, friendly messages for the
    classic traversal patterns; the whitelist match at the end is the final
    gate and enforces the full metadata.schema.json source_files discipline
    (allowed segment characters + mandatory '.md' extension).

    Forbidden (blacklist, checked first for clearer messages):
    - Contains backslash
    - Contains consecutive // (after any normalization)
    - Contains .. segments (/../ or starts with ../ or ends with /..)
    - Starts or ends with /
    - Contains ./ (current-dir reference)

    Required (whitelist, final gate):
    - Matches _RE_NAME_WHITELIST (same pattern as metadata.schema.json
      source_files items).
    """
    if "\\" in name:
        raise BuildError(
            f"Line {line_no}: marker name contains backslash: {name!r}"
        )
    if name.startswith("/") or name.endswith("/"):
        raise BuildError(
            f"Line {line_no}: marker name starts or ends with '/': {name!r}"
        )
    if _RE_CONSEC_SLASH.search(name):
        raise BuildError(
            f"Line {line_no}: marker name contains consecutive '//': {name!r}"
        )
    # Check for .. segments: /../, /../.. at end, or ../ at start
    if (
        "/.." in name
        or name.startswith("..")
        or _RE_DOTDOT_SEG.search(name)
    ):
        raise BuildError(
            f"Line {line_no}: marker name contains '..' path segment: {name!r}"
        )
    if _RE_DOTSLASH.search(name) or name.startswith("./"):
        raise BuildError(
            f"Line {line_no}: marker name contains current-dir reference './': {name!r}"
        )
    # Final gate: full whitelist (same discipline as metadata.schema.json
    # source_files items pattern).
    if not _RE_NAME_WHITELIST.match(name):
        raise BuildError(
            f"Line {line_no}: marker name {name!r} does not match the "
            f"helper-name whitelist (path segments of "
            f"[A-Za-z0-9][A-Za-z0-9_-]* joined by '/', '.md' extension "
            f"required; same rule as metadata.schema.json source_files)"
        )


# ---------------------------------------------------------------------------
# Internal: marker regex
# ---------------------------------------------------------------------------

# A real start marker is EXACTLY:  <!-- split:helper_start NAME -->
# anchored at col 0, single-space separators, --> immediately before EOL.
_RE_MARKER_START = re.compile(
    r"^<!-- split:helper_start ([^\s>]+) -->$"
)
# A real end marker is EXACTLY:  <!-- split:helper_end -->
# anchored at col 0, no trailing whitespace before EOL.
_RE_MARKER_END = re.compile(r"^<!-- split:helper_end -->$")

# Complete single-line HTML comment  <!-- ... -->  (used to exclude block state)
_RE_COMPLETE_COMMENT = re.compile(r"<!--.*?-->")


def _line_is_complete_html_comment(raw: str) -> bool:
    """Return True if the line (stripped of trailing newline) is a
    self-contained HTML comment, i.e. every <!-- on the line is closed by
    a --> on the same line and the line has no residual open state.
    """
    # Remove all complete <!-- ... --> pairs.
    stripped = _RE_COMPLETE_COMMENT.sub("", raw)
    # After removal, no <!-- or --> should remain for a fully-closed line.
    return ("<!--" not in stripped) and ("-->" not in stripped)


# ---------------------------------------------------------------------------
# Core: parse_markers
# ---------------------------------------------------------------------------


def parse_markers(text: str, source_files: list[str]) -> ParseResult:
    """Parse split:helper_start/end markers from *text*.

    Parameters:
        text         -- The full content of body.md (read with universal
                        newlines so line endings are normalized to \\n).
        source_files -- List of source_files entries from metadata.yaml.
                        A marker NAME equal to any entry here is an error.

    Returns a ParseResult with markers in appearance order.

    Raises BuildError for any of the following:
    - Unclosed start marker (start with no following end)
    - End marker without a preceding start
    - Nested start markers (start inside an open block)
    - Duplicate marker name (case-insensitively, after NFC normalization)
    - Marker name fails path safety rules
    - Marker name collides with a source_files entry
    - Empty helper (zero content lines between start and end)
    """
    # Normalize source_files for collision detection (NFC + casefold)
    source_set = {
        unicodedata.normalize("NFC", sf).casefold() for sf in source_files
    }

    # Split into lines, keeping the line terminators so content round-trips.
    # text has already been translated to \\n by the caller.
    lines_raw = text.split("\n")
    # split("\\n") loses the trailing \\n; we restore it for content lines.
    # Strategy: work with "line + \\n" for all but possibly the last line.
    # The last element after split may be "" (trailing newline) or non-empty.
    lines: list[str] = []
    for i, ln in enumerate(lines_raw):
        if i < len(lines_raw) - 1:
            lines.append(ln + "\n")
        else:
            # Last segment: keep as-is (may be empty string if file ends with \\n)
            lines.append(ln)

    in_block_comment = False
    open_block: MarkerBlock | None = None  # currently open (unclosed) marker
    seen_names: dict[str, int] = {}  # NFC+casefold -> first line_no
    result_markers: list[MarkerBlock] = []

    for idx, raw_line in enumerate(lines):
        line_no = idx + 1
        # Strip the trailing newline for matching purposes only.
        stripped = raw_line.rstrip("\n").rstrip("\r")

        # 1. Block-comment state: lines inside a multi-line HTML comment are
        #    documentation examples, never markers.  A line containing -->
        #    closes the state; that line itself still belongs to the comment.
        if in_block_comment:
            if "-->" in stripped:
                in_block_comment = False
            if open_block is not None:
                open_block.content.append(raw_line)
            continue

        # 2. Match both marker patterns exactly once.  Real markers are
        #    self-contained single-line comments anchored at column 0, so
        #    they never open block-comment state.
        m_start = _RE_MARKER_START.match(stripped)
        m_end = _RE_MARKER_END.match(stripped)

        if m_start is not None:
            # --- Start marker ---
            name = m_start.group(1)

            # Path safety check.
            _check_name_path_safety(name, line_no)

            # Duplicate name check (NFC + casefold).
            norm_name = unicodedata.normalize("NFC", name).casefold()
            if norm_name in seen_names:
                raise BuildError(
                    f"Line {line_no}: duplicate marker name {name!r} "
                    f"(first seen at line {seen_names[norm_name]})"
                )

            # Source/output collision check.
            if norm_name in source_set:
                raise BuildError(
                    f"Line {line_no}: marker name {name!r} collides with "
                    f"a source_files entry"
                )

            # Nesting check.
            if open_block is not None:
                raise BuildError(
                    f"Line {line_no}: nested start marker {name!r} inside "
                    f"unclosed marker {open_block.name!r} "
                    f"(opened at line {open_block.start_line})"
                )

            seen_names[norm_name] = line_no
            open_block = MarkerBlock(
                name=name,
                start_line=line_no,
                end_line=0,  # filled in at end marker
                content=[],
            )

        elif m_end is not None:
            # --- End marker ---
            if open_block is None:
                raise BuildError(
                    f"Line {line_no}: end marker without a preceding "
                    f"start marker"
                )

            # Empty-helper check.
            if len(open_block.content) == 0:
                raise BuildError(
                    f"Line {line_no}: empty helper block for marker "
                    f"{open_block.name!r} (zero content lines between "
                    f"start at line {open_block.start_line} and end)"
                )

            open_block.end_line = line_no
            result_markers.append(open_block)
            open_block = None

        else:
            # 3. Non-marker line.  It may open a multi-line HTML comment:
            #    a <!-- without its --> on the same line puts subsequent
            #    lines into comment state (marker-shaped lines inside such
            #    a block are documentation examples, handled in step 1).
            if "<!--" in stripped and not _line_is_complete_html_comment(
                stripped
            ):
                in_block_comment = True
            # 4. Ordinary content: accumulate if inside an open marker.
            if open_block is not None:
                open_block.content.append(raw_line)

    # After all lines: check for unclosed marker.
    if open_block is not None:
        raise BuildError(
            f"Unclosed start marker {open_block.name!r} "
            f"(opened at line {open_block.start_line}, no matching end found)"
        )

    return ParseResult(markers=result_markers, source_text=text)


# ---------------------------------------------------------------------------
# Metadata validation
# ---------------------------------------------------------------------------


def validate_metadata(
    source_dir: Path,
    schema_path: Path | None = None,
) -> dict[str, Any]:
    """Load and JSON-schema-validate metadata.yaml from *source_dir*.

    Parameters:
        source_dir  -- Directory containing metadata.yaml.
        schema_path -- Path to metadata.schema.json.  Defaults to
                       DEFAULT_SCHEMA_PATH (this repo's
                       skills/source/metadata.schema.json); fixtures do
                       not carry their own schema copy.

    Returns the parsed metadata dict on success.
    Raises BuildError on any failure.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError:
        # Fallback: use the stdlib-only yaml subset if PyYAML is absent.
        # For Phase 5.b Stage 2 we require PyYAML; raise a clear error.
        raise BuildError(
            "PyYAML is required to parse metadata.yaml.  "
            "Install it with: pip install pyyaml"
        )

    meta_path = source_dir / "metadata.yaml"
    if not meta_path.exists():
        raise BuildError(f"metadata.yaml not found: {meta_path}")

    try:
        raw = meta_path.read_text(encoding="utf-8-sig")
        metadata = yaml.safe_load(raw)
    except Exception as exc:  # noqa: BLE001
        raise BuildError(f"Failed to read metadata.yaml: {exc}") from exc

    if not isinstance(metadata, dict):
        raise BuildError("metadata.yaml must be a YAML mapping at the top level")

    # Resolve schema path.  The schema is a repo asset, not a per-source
    # file: default to this repo's skills/source/metadata.schema.json.
    if schema_path is None:
        schema_path = DEFAULT_SCHEMA_PATH
    if not schema_path.exists():
        raise BuildError(f"metadata.schema.json not found: {schema_path}")

    try:
        schema_text = schema_path.read_text(encoding="utf-8-sig")
        schema = json.loads(schema_text)
    except Exception as exc:  # noqa: BLE001
        raise BuildError(f"Failed to read metadata.schema.json: {exc}") from exc

    try:
        import jsonschema  # type: ignore[import]

        validator_cls = jsonschema.validators.validator_for(schema)
        validator_cls.check_schema(schema)
        validator = validator_cls(schema)
        errors = list(validator.iter_errors(metadata))
        if errors:
            # Report the first (and most significant) error.
            err = errors[0]
            raise BuildError(
                f"metadata.yaml schema validation failed: {err.message} "
                f"(path: {'/'.join(str(p) for p in err.absolute_path)})"
            )
    except BuildError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise BuildError(
            f"jsonschema validation error: {exc}"
        ) from exc

    return metadata


# ---------------------------------------------------------------------------
# Converter version check
# ---------------------------------------------------------------------------


def check_converter_version(metadata: dict[str, Any]) -> None:
    """Verify that CONVERTER_VERSION satisfies metadata.converter_min_version.

    Raises BuildError if:
    - converter_min_version is missing or malformed.
    - CONVERTER_VERSION < converter_min_version.
    """
    raw_min = metadata.get("converter_min_version", "")
    if not raw_min:
        raise BuildError(
            "metadata.yaml missing required field 'converter_min_version'"
        )

    try:
        min_ver = parse_semver(str(raw_min))
    except ValueError as exc:
        raise BuildError(
            f"converter_min_version is not a valid semver: {raw_min!r} ({exc})"
        ) from exc

    try:
        cur_ver = parse_semver(CONVERTER_VERSION)
    except ValueError as exc:  # pragma: no cover  (CONVERTER_VERSION is hardcoded)
        raise BuildError(
            f"CONVERTER_VERSION constant is not a valid semver: "
            f"{CONVERTER_VERSION!r} ({exc})"
        ) from exc

    if cur_ver < min_ver:
        raise BuildError(
            f"This build_skill.py ({CONVERTER_VERSION}) is older than "
            f"converter_min_version ({raw_min}).  "
            f"Update tools/build_skill.py to {raw_min} or newer."
        )


# ---------------------------------------------------------------------------
# Agent doc check
# ---------------------------------------------------------------------------


def check_agent_docs(
    metadata: dict[str, Any],
    agent_docs_dir: Path,
) -> None:
    """Verify that each target_agent has a 'status: supported' agent doc.

    The agent doc is expected at agent_docs_dir / f"agent-{name}.md".
    The front matter (YAML between the first '---' and the next '---' line)
    must contain ``status: supported``.

    Raises BuildError if:
    - An agent doc is missing.
    - The front matter cannot be parsed.
    - status != "supported".
    """
    try:
        import yaml  # type: ignore[import]  # noqa: F401
    except ImportError as exc:
        raise BuildError(
            "PyYAML is required to parse agent doc front matter."
        ) from exc

    target_agents: list[str] = metadata.get("target_agents", [])

    for agent_name in target_agents:
        doc_path = agent_docs_dir / f"agent-{agent_name}.md"
        if not doc_path.exists():
            raise BuildError(
                f"Agent doc not found for target agent {agent_name!r}: "
                f"{doc_path}"
            )

        try:
            doc_text = doc_path.read_text(encoding="utf-8-sig")
        except Exception as exc:  # noqa: BLE001
            raise BuildError(
                f"Failed to read agent doc {doc_path}: {exc}"
            ) from exc

        # Extract YAML front matter between first '---' and second '---'.
        front_matter = _extract_front_matter(doc_text, doc_path)

        status = front_matter.get("status", "")
        if status != "supported":
            raise BuildError(
                f"Agent {agent_name!r} is not supported: "
                f"agent doc {doc_path} has status: {status!r} "
                f"(must be 'supported')"
            )


def _extract_front_matter(text: str, path: Path) -> dict[str, Any]:
    """Parse YAML front matter from Markdown text.

    The front matter is between the first '---' line and the next '---' line.
    Returns an empty dict if no front matter is found.
    Raises BuildError on parse failure.
    """
    try:
        import yaml  # type: ignore[import]
    except ImportError as exc:
        raise BuildError("PyYAML is required.") from exc

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        raise BuildError(
            f"Agent doc {path}: front matter opened with '---' but never closed"
        )

    fm_text = "\n".join(lines[1:end_idx])
    try:
        parsed = yaml.safe_load(fm_text)
    except Exception as exc:  # noqa: BLE001
        raise BuildError(
            f"Agent doc {path}: YAML front matter parse failed: {exc}"
        ) from exc

    if not isinstance(parsed, dict):
        raise BuildError(
            f"Agent doc {path}: front matter must be a YAML mapping"
        )
    return parsed


# ---------------------------------------------------------------------------
# Source files check
# ---------------------------------------------------------------------------


def check_source_files(
    metadata: dict[str, Any],
    source_dir: Path,
) -> None:
    """Verify that every source_files entry exists under source_dir.

    Raises BuildError if any entry is missing.
    """
    source_files: list[str] = metadata.get("source_files", [])
    for rel in source_files:
        target = source_dir / rel
        if not target.exists():
            raise BuildError(
                f"source_files entry not found: {rel!r} "
                f"(expected at {target})"
            )


# ---------------------------------------------------------------------------
# Combined validate + parse entry point
# ---------------------------------------------------------------------------


def validate_and_parse(
    source_dir: Path,
    agent_docs_dir: Path | None = None,
    schema_path: Path | None = None,
) -> tuple[dict[str, Any], ParseResult]:
    """Run all validation + parse steps in sequence.

    Steps:
      1. validate_metadata       -- load + JSON-schema check metadata.yaml
      2. check_converter_version -- compare min_version vs CONVERTER_VERSION
      3. check_agent_docs        -- verify target_agents docs exist + supported
      4. check_source_files      -- verify source_files entries exist
      5. parse_markers           -- parse body.md for split:helper_start/end

    Parameters:
        source_dir     -- Directory containing metadata.yaml + body.md.
        agent_docs_dir -- Dir containing agent-*.md docs.  Defaults to
                          DEFAULT_AGENT_DOCS_DIR (this repo's
                          development/docs/skill-converter/).  Override
                          in tests to simulate missing / unsupported
                          agent docs.
        schema_path    -- Path to metadata.schema.json.  Defaults to
                          DEFAULT_SCHEMA_PATH (this repo's
                          skills/source/metadata.schema.json).

    Returns (metadata, ParseResult) on success.
    Raises BuildError on any failure.
    Raises UsageError if source_dir does not exist.
    """
    if not source_dir.exists():
        raise UsageError(f"source_dir does not exist: {source_dir}")

    # Default agent_docs_dir: this repo's development/docs/skill-converter.
    # Agent capability docs are a repo asset (like the schema), independent
    # of which source dir is being built.
    if agent_docs_dir is None:
        agent_docs_dir = DEFAULT_AGENT_DOCS_DIR

    # Step 1: validate metadata
    metadata = validate_metadata(source_dir, schema_path=schema_path)

    # Step 2: converter version
    check_converter_version(metadata)

    # Step 3: agent docs
    check_agent_docs(metadata, agent_docs_dir)

    # Step 4: source files exist
    check_source_files(metadata, source_dir)

    # Step 5: parse markers from body.md
    # Phase 5 Step 5.a-1' established body.md as the single authoritative
    # source.  We read only body.md for markers (the first source_files entry
    # or the hard-coded "body.md" convention).
    source_files: list[str] = metadata.get("source_files", [])
    body_rel = source_files[0] if source_files else "body.md"
    body_path = source_dir / body_rel

    try:
        # Read with utf-8-sig (BOM-tolerant) and translate to universal newlines.
        raw_text = body_path.read_text(encoding="utf-8-sig", newline="")
        # Normalize line endings to \n for the parser.
        body_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    except Exception as exc:  # noqa: BLE001
        raise BuildError(f"Failed to read {body_path}: {exc}") from exc

    parse_result = parse_markers(body_text, source_files)

    return metadata, parse_result


# ---------------------------------------------------------------------------
# SOURCE_DATE_EPOCH validation (prejournal Sec.3.2)
# ---------------------------------------------------------------------------

_RE_BARE_NONNEG_INT = re.compile(r"^[0-9]+$")
_SOURCE_DATE_EPOCH_MAX = 2**63 - 1


def validate_source_date_epoch(raw: str | None) -> int | None:
    """Validate the SOURCE_DATE_EPOCH environment variable value.

    Accepts ONLY a bare decimal non-negative integer string: no leading
    '+'/'-', no surrounding whitespace, no decimals, no hex.  Range is
    0..2**63-1 inclusive.

    Returns None if *raw* is None (unset).  Returns the parsed int
    otherwise.  Raises BuildError on any format or range violation
    (fail-closed, prejournal Sec.3.2).
    """
    if raw is None:
        return None
    if not _RE_BARE_NONNEG_INT.match(raw):
        raise BuildError(
            f"SOURCE_DATE_EPOCH must be a bare decimal non-negative integer "
            f"string (no leading +/-, no whitespace, no decimals, no hex); "
            f"got {raw!r}"
        )
    value = int(raw)
    if value > _SOURCE_DATE_EPOCH_MAX:
        raise BuildError(
            f"SOURCE_DATE_EPOCH out of range (0..{_SOURCE_DATE_EPOCH_MAX}); "
            f"got {value}"
        )
    return value


def _source_date_epoch_to_iso_utc(epoch: int) -> str:
    """Convert a validated SOURCE_DATE_EPOCH value to an ISO-8601 UTC string."""
    import datetime

    dt = datetime.datetime.fromtimestamp(epoch, tz=datetime.timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# build_input_digest (acceptance-matrix.md "build_input_digest の構成")
#
# 8 categories, canonical order:
#   1. metadata.yaml
#   2. metadata.schema.json
#   3. source_files (authored source, e.g. body.md)
#   4. bundled hook files for target_agents (AGENT_TO_HOOK_DIRNAME mapping)
#   5. bundled lint files (agent-independent)
#   6. agent docs (agent-{name}.md) for each target agent
#   7. converter source itself (tools/build_skill.py)
#   8. SOURCE_DATE_EPOCH value (or "unset")
#
# Concat format per file: "<category id>\n<path utf-8>\n<content bytes>\n"
# Category 8: "8\nSOURCE_DATE_EPOCH\n<value or unset>\n"
# Within each category, relative paths are ASCII-sorted (lexicographic
# bytewise) POSIX-style paths relative to the repo root.
# ---------------------------------------------------------------------------


def _posix_rel(path: Path, base: Path) -> str:
    """Return path relative to base, POSIX-style ('/' separators)."""
    return path.resolve().relative_to(base.resolve()).as_posix()


# Extensions eligible for hook / lint bundling in the digest (category 4/5).
# Mirrors the acceptance-matrix wording: json/ps1/md/sh (+ py for lint, which
# ships a cross-platform Python implementation alongside the .ps1 one).
_BUNDLE_EXTENSIONS = (".json", ".ps1", ".md", ".sh", ".py")


def _iter_bundle_files(root: Path) -> list[Path]:
    """Recursively collect files under *root* with a bundle-eligible extension.

    Returns paths sorted by their string form (ASCII/bytewise order is what
    Python's default str sort gives us for our path alphabet).
    """
    if not root.exists():
        return []
    found = [
        p
        for p in root.rglob("*")
        if p.is_file() and p.suffix in _BUNDLE_EXTENSIONS
    ]
    return sorted(found, key=lambda p: p.as_posix())


def compute_build_input_digest(
    *,
    source_dir: Path,
    metadata: dict[str, Any],
    schema_path: Path,
    agent_docs_dir: Path,
    converter_path: Path,
    repo_root: Path,
    source_date_epoch: int | None,
) -> str:
    """Compute the build_input_digest per acceptance-matrix.md.

    Returns the full lowercase hex sha256 digest (callers take the first 16
    chars for the generator header).
    """
    chunks: list[bytes] = []

    def add_file(category: int, rel_path: str, content: bytes) -> None:
        chunks.append(f"{category}\n{rel_path}\n".encode())
        chunks.append(content)
        chunks.append(b"\n")

    # Category 1: metadata.yaml
    meta_path = source_dir / "metadata.yaml"
    add_file(1, _posix_rel(meta_path, repo_root), meta_path.read_bytes())

    # Category 2: metadata.schema.json
    add_file(2, _posix_rel(schema_path, repo_root), schema_path.read_bytes())

    # Category 3: source_files (authored source), ASCII-sorted relative paths.
    source_files: list[str] = list(metadata.get("source_files", []))
    for rel in sorted(source_files):
        p = source_dir / rel
        add_file(3, _posix_rel(p, repo_root), p.read_bytes())

    # Category 4: bundled hook files for target_agents.
    target_agents: list[str] = list(metadata.get("target_agents", []))
    hook_files: list[Path] = []
    for agent in target_agents:
        dirname = AGENT_TO_HOOK_DIRNAME.get(agent)
        if dirname is None:
            continue
        hook_root = source_dir / "hooks" / dirname
        hook_files.extend(_iter_bundle_files(hook_root))
    hook_files_sorted = sorted(
        {_posix_rel(p, repo_root) for p in hook_files}
    )
    for rel in hook_files_sorted:
        p = repo_root / rel
        add_file(4, rel, p.read_bytes())

    # Category 5: bundled lint files (agent-independent).
    lint_root = source_dir / LINT_SOURCE_DIRNAME
    lint_files = _iter_bundle_files(lint_root)
    lint_rels = sorted(_posix_rel(p, repo_root) for p in lint_files)
    for rel in lint_rels:
        p = repo_root / rel
        add_file(5, rel, p.read_bytes())

    # Category 6: agent docs for each target agent.
    agent_doc_rels = sorted(
        _posix_rel(agent_docs_dir / f"agent-{a}.md", repo_root)
        for a in target_agents
    )
    for rel in agent_doc_rels:
        p = repo_root / rel
        add_file(6, rel, p.read_bytes())

    # Category 7: converter source itself.
    add_file(
        7, _posix_rel(converter_path, repo_root), converter_path.read_bytes()
    )

    # Category 8: SOURCE_DATE_EPOCH value or "unset" (not a file; literal).
    epoch_value = "unset" if source_date_epoch is None else str(source_date_epoch)
    chunks.append(f"8\nSOURCE_DATE_EPOCH\n{epoch_value}\n".encode())

    digest = hashlib.sha256(b"".join(chunks)).hexdigest()
    return digest


# ---------------------------------------------------------------------------
# Generator header (item 9)
# ---------------------------------------------------------------------------


def build_generator_header(
    *, build_input_digest: str, source_date_epoch: int | None
) -> str:
    """Return the deterministic HTML-comment generator header block.

    Placed immediately after frontmatter in SKILL.md, or at the very top of
    helper files / INSTALL.md.  No source commit hash.  No timestamp unless
    SOURCE_DATE_EPOCH is set (build_date_utc line then appended).
    """
    short_digest = build_input_digest[:16]
    lines = [
        "<!--",
        "  GENERATED FILE - DO NOT EDIT.",
        "  これは生成物。skills/source/body.md を編集すること。",
        f"  converter_version: {CONVERTER_VERSION}",
        f"  build_input_digest: {short_digest}",
    ]
    if source_date_epoch is not None:
        lines.append(
            f"  build_date_utc: {_source_date_epoch_to_iso_utc(source_date_epoch)}"
        )
    lines.append("-->")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Rendering: full / split (items 6-7)
# ---------------------------------------------------------------------------

_RE_MARKER_START_LINE = re.compile(r"^<!-- split:helper_start [^\s>]+ -->\r?\n?$")
_RE_MARKER_END_LINE = re.compile(r"^<!-- split:helper_end -->\r?\n?$")


def render_full(source_text: str, markers: list[MarkerBlock]) -> str:
    """Render full-mode body: marker start/end LINES removed, content kept in place.

    Nothing else altered.  *source_text* must already be LF-normalized
    (ParseResult.source_text).
    """
    lines = source_text.split("\n")
    # Re-attach the trailing "\n" convention used elsewhere: split("\n") loses
    # separators, so rebuild lines-with-newline for all but the last element.
    marker_start_lines = {m.start_line for m in markers}
    marker_end_lines = {m.end_line for m in markers}

    out_lines: list[str] = []
    for idx, raw in enumerate(lines):
        line_no = idx + 1
        if line_no in marker_start_lines or line_no in marker_end_lines:
            continue
        out_lines.append(raw)
    return "\n".join(out_lines)


def render_split(
    source_text: str, markers: list[MarkerBlock]
) -> tuple[str, dict[str, str]]:
    """Render split-mode body + helper file contents.

    Returns (body_with_see_refs, {marker_name: helper_content}).

    Each marker pair (start line + content + end line) is replaced by
    EXACTLY ONE line: "@see <marker-name>".  Helper content is the marker's
    verbatim content (joined), NOT prefixed with the generator header here
    (the caller prepends the header when writing the helper file).
    """
    lines = source_text.split("\n")
    marker_by_start: dict[int, MarkerBlock] = {m.start_line: m for m in markers}
    marker_content_line_ranges: list[tuple[int, int]] = [
        (m.start_line, m.end_line) for m in markers
    ]

    def in_any_marker(line_no: int) -> bool:
        return any(start <= line_no <= end for start, end in marker_content_line_ranges)

    out_lines: list[str] = []
    idx = 0
    n = len(lines)
    while idx < n:
        line_no = idx + 1
        if line_no in marker_by_start:
            mb = marker_by_start[line_no]
            out_lines.append(f"@see {mb.name}")
            # Skip forward past the entire marker block (start..end lines).
            idx = mb.end_line  # end_line is 1-based; next unprocessed index.
            continue
        if in_any_marker(line_no):
            # Should not happen (content lines are only reached via the
            # marker skip above), but guard defensively.
            idx += 1
            continue
        out_lines.append(lines[idx])
        idx += 1

    helper_contents = {m.name: "".join(m.content) for m in markers}
    return "\n".join(out_lines), helper_contents


# ---------------------------------------------------------------------------
# Agent frontmatter (item 8)
#
# Key order = declaration order documented in the agent doc (NOT alphabetical).
# ---------------------------------------------------------------------------


def build_frontmatter(agent: str, metadata: dict[str, Any]) -> str:
    """Build the YAML frontmatter block for *agent*.

    claude: name, description, allowed-tools, disable-model-invocation
      (the key set + order documented in agent-claude.md "qgb 向け
      frontmatter 設計案").
    codex: name, description only (the only keys confirmed in
      agent-codex.md "qgb 向け SKILL.md 設計案"; other keys are
      unconfirmed/known_gaps and must not be emitted).

    description comes from metadata.yaml's agent-neutral `description`.
    Returns the frontmatter block INCLUDING the leading/trailing '---' lines
    and a trailing newline.
    """
    import yaml

    description = metadata.get("description", "")
    skill_id = metadata.get("skill_id", "")

    if agent == "claude":
        # Declaration order per agent-claude.md's frontmatter design sample:
        # name, description, allowed-tools, disable-model-invocation.
        fm: dict[str, Any] = {
            "name": skill_id,
            "description": description,
            "allowed-tools": [
                "Read",
                "Glob",
                "Grep",
                "Write",
                "Edit",
                "Bash(python -m qgb *)",
                "Bash(git *)",
            ],
            "disable-model-invocation": False,
        }
    elif agent == "codex":
        # Only the confirmed key set (agent-codex.md known_gaps: other keys
        # are unconfirmed and intentionally omitted).
        fm = {
            "name": skill_id,
            "description": description,
        }
    else:
        raise BuildError(f"No frontmatter spec for agent {agent!r}")

    # Dump preserving declaration order (sort_keys=False), block style,
    # literal-safe unicode, and a trailing newline collapse to keep output
    # deterministic.
    yaml_text = yaml.safe_dump(
        fm,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )
    return f"---\n{yaml_text}---\n"


# ---------------------------------------------------------------------------
# INSTALL.md (item 10)
# ---------------------------------------------------------------------------

_AGENT_INSTALL_PATHS = {
    "claude": ("~/.claude/skills/qgb/", ".claude/skills/qgb/"),
    "codex": ("~/.agents/skills/qgb/", ".agents/skills/qgb/"),
}


def render_install_md(*, agent: str, mode: str, metadata: dict[str, Any]) -> str:
    """Render INSTALL.md body (without the generator header; caller prepends it)."""
    user_path, project_path = _AGENT_INSTALL_PATHS[agent]
    skill_id = metadata.get("skill_id", "qgb")

    if mode == "full":
        files_desc = (
            "- `SKILL.md` (1 ファイルだけ。"
            "helper 内容はすべて本文に埋め込み済み)"
        )
    else:
        files_desc = (
            "- `SKILL.md` (本体。helper の位置に `@see <helper-path>` "
            "の参照行が入る)\n"
            "- helper files (`workflow.md` / `references.md` / `prompts/*.md` 等、"
            "SKILL.md と同じディレクトリに配置)"
        )

    lines = [
        f"# {skill_id} skill インストールガイド ({agent} / {mode})",
        "",
        "## 配置先",
        "",
        f"- 個人全プロジェクト共通: `{user_path}`",
        f"- プロジェクト単位: `{project_path}`",
        "",
        "## コピーするファイル",
        "",
        files_desc,
        "",
        "## hooks (任意, opt-in)",
        "",
        (
            "`hooks/` 配下に hook テンプレと `README.md` を同梱しています。"
            "利用する場合は `hooks/README.md` の手順に従って "
            "opt-in / dry-run / validate / 非破壊の後で既存設定へ merge してください。"
        ),
        "",
        "## lint (verification_type=command 契約作成時)",
        "",
        (
            "`lint/` 配下に `check-command-contract.py` / "
            "`check-command-contract.ps1` を同梱しています。"
            "skill agent は `verification_type=command` の contract を"
            "起草・編集した直後にこの lint を実行し、"
            "fix-required の finding がないことを確認してから "
            "`qgb design-stages adopt` へ進むこと。"
            "詳細は `lint/README.md` を参照。"
        ),
        "",
        "## Windows についての注意",
        "",
        (
            "Windows native 環境では symlink race 防御 "
            "(`O_NOFOLLOW` 相当) が POSIX より弱いことがあります。"
            "clean build + exclusive create の防御は有効ですが、"
            "信頼できない共有環境での build は推奨しません "
            "(詳細: `development/docs/journal/phase5-step5-a-2.md` "
            "§6.3 item 5)。"
        ),
        "",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Path defenses + safe write (item: path defenses)
# ---------------------------------------------------------------------------


def _safe_write_bytes(dist_root: Path, target: Path, data: bytes) -> None:
    """Write *data* to *target* with layered path + TOCTOU defenses.

    Defenses (Codex K=2 r1 recommendation #2 + K=2 r2/r3/r4 spec fixes, see
    phase5-step5-a-2.md Sec.6.3 item 5):
      1. normpath containment check against dist_root (literal prefix compare)
      2. realpath containment check (symlink defense, final component)
      3. os.lstat absence check before create
      4. exclusive create (O_CREAT | O_EXCL [| O_NOFOLLOW on POSIX])
      5. os.fstat(fd).st_nlink == 1 sanity check (hardlink defense, best-effort)

    Threat model: parent-directory symlink races are explicitly out of
    scope for Phase 5 (no openat() equivalent in Python's stdlib os.open());
    see phase5-step5-a-2.md Sec.6.3 item 5 for the documented boundary.
    """
    dist_root_norm = os.path.normpath(str(dist_root))
    target_norm = os.path.normpath(str(target))
    if not (
        target_norm == dist_root_norm
        or target_norm.startswith(dist_root_norm + os.sep)
    ):
        raise BuildError(
            f"Refusing to write outside dist root: {target} "
            f"(dist_root={dist_root})"
        )

    dist_root_real = os.path.realpath(str(dist_root))
    target_parent_real = os.path.realpath(str(target.parent))
    if not (
        target_parent_real == dist_root_real
        or target_parent_real.startswith(dist_root_real + os.sep)
    ):
        raise BuildError(
            f"Refusing to write outside dist root (realpath check failed): "
            f"{target} (dist_root={dist_root})"
        )

    target.parent.mkdir(parents=True, exist_ok=True)

    try:
        os.lstat(str(target))
        raise BuildError(
            f"Refusing to overwrite existing path (clean build invariant "
            f"violated): {target}"
        )
    except FileNotFoundError:
        pass

    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY

    fd = os.open(str(target), flags, 0o644)
    try:
        os.write(fd, data)
        st = os.fstat(fd)
        if st.st_nlink != 1:
            raise BuildError(
                f"Sanity check failed: newly-created file has st_nlink="
                f"{st.st_nlink} (expected 1), possible hardlink attack: "
                f"{target}"
            )
    finally:
        os.close(fd)


# ---------------------------------------------------------------------------
# Copies: hooks/ and lint/ (item 11) -- NOT generated artifacts.
#
# These are copied byte-verbatim with NO header injection.  JSON cannot
# carry comments, and the digest (category 4/5) already covers these files
# as build inputs, so there is no deterministic-build gap left by skipping
# header injection here.
# ---------------------------------------------------------------------------


def _copy_tree_verbatim(dist_root: Path, src_root: Path, dest_root: Path) -> list[Path]:
    """Copy every file under src_root to dest_root, preserving the tree shape.

    Returns the list of written destination paths (for reporting).  Uses
    _safe_write_bytes for every file so the same path defenses apply to
    copies as to generated content.
    """
    written: list[Path] = []
    if not src_root.exists():
        return written
    for p in sorted(src_root.rglob("*"), key=lambda x: x.as_posix()):
        if p.is_file():
            rel = p.relative_to(src_root)
            dest = dest_root / rel
            _safe_write_bytes(dist_root, dest, p.read_bytes())
            written.append(dest)
    return written


# ---------------------------------------------------------------------------
# Syntax verification (item 12)
# ---------------------------------------------------------------------------


def verify_generated_skill_md(text: str, *, expected_keys: set[str]) -> None:
    """Verify a generated SKILL.md: split frontmatter, YAML-parse it, sanity-check body.

    Raises BuildError on any failure.
    """
    import yaml

    if "\x00" in text:
        raise BuildError("Generated SKILL.md contains NUL byte(s)")
    if not text.strip():
        raise BuildError("Generated SKILL.md is empty")
    if not text.startswith("---\n"):
        raise BuildError("Generated SKILL.md does not start with frontmatter '---'")

    lines = text.split("\n")
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            end_idx = i
            break
    if end_idx is None:
        raise BuildError("Generated SKILL.md frontmatter never closes with '---'")

    fm_text = "\n".join(lines[1:end_idx])
    try:
        fm = yaml.safe_load(fm_text)
    except Exception as exc:  # noqa: BLE001
        raise BuildError(f"Generated SKILL.md frontmatter failed to parse: {exc}") from exc

    if not isinstance(fm, dict):
        raise BuildError("Generated SKILL.md frontmatter did not parse to a mapping")

    missing = expected_keys - set(fm.keys())
    if missing:
        raise BuildError(
            f"Generated SKILL.md frontmatter missing expected keys: {missing}"
        )

    body_after_fm = "\n".join(lines[end_idx + 1 :])
    if not body_after_fm.strip():
        raise BuildError("Generated SKILL.md has no body content after frontmatter")


def verify_text_artifact(text: str, *, label: str) -> None:
    """Verify a helper file or INSTALL.md: UTF-8 decodable, non-empty, no NUL."""
    if "\x00" in text:
        raise BuildError(f"{label}: contains NUL byte(s)")
    if not text.strip():
        raise BuildError(f"{label}: is empty")
    try:
        text.encode("utf-8")
    except UnicodeEncodeError as exc:  # pragma: no cover  (str is already unicode)
        raise BuildError(f"{label}: failed to encode as UTF-8: {exc}") from exc


# ---------------------------------------------------------------------------
# Clean build (items 13-15)
# ---------------------------------------------------------------------------


def _clean_cell_dir(cell_dir: Path) -> None:
    """Remove *cell_dir* if it exists, then recreate it empty.

    Codex K=2 r1 spec fix #2 "stale output 除去 or clean build": clean
    build is the default; this also serves as the primary hardlink defense
    (see phase5-step5-a-2.md Sec.6.3 item 5(a)).
    """
    if cell_dir.exists():
        shutil.rmtree(cell_dir)
    cell_dir.mkdir(parents=True, exist_ok=True)


def _write_text_file(dist_root: Path, target: Path, text: str) -> None:
    """Write *text* as UTF-8 (no BOM), LF newlines, via _safe_write_bytes."""
    data = text.encode("utf-8")
    _safe_write_bytes(dist_root, target, data)


# ---------------------------------------------------------------------------
# Orchestration: build one (mode, agent) cell
# ---------------------------------------------------------------------------


@dataclass
class BuildCellResult:
    mode: str
    agent: str
    cell_dir: Path
    files_written: list[Path] = field(default_factory=list)
    build_input_digest: str = ""


def _frontmatter_expected_keys(agent: str) -> set[str]:
    if agent == "claude":
        return {"name", "description", "allowed-tools", "disable-model-invocation"}
    if agent == "codex":
        return {"name", "description"}
    raise BuildError(f"No frontmatter key spec for agent {agent!r}")


def build_cell(
    *,
    mode: str,
    agent: str,
    source_dir: Path,
    dist_dir: Path,
    metadata: dict[str, Any],
    parse_result: ParseResult,
    schema_path: Path,
    agent_docs_dir: Path,
    repo_root: Path,
    source_date_epoch: int | None,
) -> BuildCellResult:
    """Build a single (mode, agent) output cell under dist_dir.

    Performs: clean build, digest computation, SKILL.md render + frontmatter
    + generator header, helper file writes (split mode), INSTALL.md, hooks/
    + lint/ copies, and syntax verification of every generated artifact.
    """
    cell_dir = dist_dir / mode / agent
    _clean_cell_dir(cell_dir)

    converter_path = Path(__file__).resolve()
    digest = compute_build_input_digest(
        source_dir=source_dir,
        metadata=metadata,
        schema_path=schema_path,
        agent_docs_dir=agent_docs_dir,
        converter_path=converter_path,
        repo_root=repo_root,
        source_date_epoch=source_date_epoch,
    )
    header = build_generator_header(
        build_input_digest=digest, source_date_epoch=source_date_epoch
    )

    result = BuildCellResult(mode=mode, agent=agent, cell_dir=cell_dir, build_input_digest=digest)

    # --- SKILL.md ---
    frontmatter = build_frontmatter(agent, metadata)

    if mode == "full":
        body = render_full(parse_result.source_text, parse_result.markers)
    elif mode == "split":
        body, helper_contents = render_split(
            parse_result.source_text, parse_result.markers
        )
    else:
        raise BuildError(f"Unknown build mode: {mode!r}")

    skill_md_text = frontmatter + header + body
    if not skill_md_text.endswith("\n"):
        skill_md_text += "\n"

    verify_generated_skill_md(
        skill_md_text, expected_keys=_frontmatter_expected_keys(agent)
    )

    skill_md_path = cell_dir / "SKILL.md"
    _write_text_file(dist_dir, skill_md_path, skill_md_text)
    result.files_written.append(skill_md_path)

    # --- helper files (split mode only), enumeration order = marker
    # appearance order (Codex K=2 r1 spec fix "deterministic ordering") ---
    if mode == "split":
        for mb in parse_result.markers:
            helper_text = header + helper_contents[mb.name]
            verify_text_artifact(helper_text, label=f"helper {mb.name}")
            helper_path = cell_dir / mb.name
            _write_text_file(dist_dir, helper_path, helper_text)
            result.files_written.append(helper_path)

    # --- INSTALL.md ---
    install_body = render_install_md(agent=agent, mode=mode, metadata=metadata)
    install_text = header + install_body
    verify_text_artifact(install_text, label="INSTALL.md")
    install_path = cell_dir / "INSTALL.md"
    _write_text_file(dist_dir, install_path, install_text)
    result.files_written.append(install_path)

    # --- hooks/ copy (verbatim, no header) ---
    hook_dirname = AGENT_TO_HOOK_DIRNAME.get(agent)
    if hook_dirname is not None:
        hooks_src = source_dir / "hooks" / hook_dirname
        hooks_dest = cell_dir / "hooks"
        result.files_written.extend(
            _copy_tree_verbatim(dist_dir, hooks_src, hooks_dest)
        )

    # --- lint/ copy (verbatim, no header, agent-independent) ---
    lint_src = source_dir / LINT_SOURCE_DIRNAME
    lint_dest = cell_dir / "lint"
    result.files_written.extend(_copy_tree_verbatim(dist_dir, lint_src, lint_dest))

    return result


# ---------------------------------------------------------------------------
# Full build: all build_modes x target_agents
# ---------------------------------------------------------------------------


@dataclass
class BuildSummary:
    cells: list[BuildCellResult] = field(default_factory=list)


def build_all(
    *,
    source_dir: Path,
    dist_dir: Path,
    agent_docs_dir: Path | None = None,
    schema_path: Path | None = None,
    repo_root: Path | None = None,
    source_date_epoch_raw: str | None = None,
) -> BuildSummary:
    """Run validate_and_parse, then generate every (mode, agent) cell.

    Parameters mirror validate_and_parse, plus:
      dist_dir             -- output root (dist/skills equivalent).
      repo_root             -- root used for digest path-relativization;
                                defaults to this script's repo root.
      source_date_epoch_raw -- raw string from the SOURCE_DATE_EPOCH env var
                                (or None if unset).  Validated here.
    """
    if agent_docs_dir is None:
        agent_docs_dir = DEFAULT_AGENT_DOCS_DIR
    if schema_path is None:
        schema_path = DEFAULT_SCHEMA_PATH
    if repo_root is None:
        repo_root = _REPO_ROOT

    source_date_epoch = validate_source_date_epoch(source_date_epoch_raw)

    metadata, parse_result = validate_and_parse(
        source_dir, agent_docs_dir=agent_docs_dir, schema_path=schema_path
    )

    build_modes: list[str] = list(metadata.get("build_modes", []))
    target_agents: list[str] = list(metadata.get("target_agents", []))

    summary = BuildSummary()
    for mode in build_modes:
        for agent in target_agents:
            cell = build_cell(
                mode=mode,
                agent=agent,
                source_dir=source_dir,
                dist_dir=dist_dir,
                metadata=metadata,
                parse_result=parse_result,
                schema_path=schema_path,
                agent_docs_dir=agent_docs_dir,
                repo_root=repo_root,
                source_date_epoch=source_date_epoch,
            )
            summary.cells.append(cell)

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="build_skill",
        description=(
            "build_skill.py -- Phase 5 skill converter "
            f"(version {CONVERTER_VERSION})"
        ),
    )
    p.add_argument(
        "--source-dir",
        default=None,
        help=(
            "Path to the skills/source directory.  "
            "Defaults to <repo_root>/skills/source where repo_root is "
            "inferred from this script's location."
        ),
    )
    p.add_argument(
        "--check",
        action="store_true",
        default=False,
        help=(
            "Run validation + parse only and report results.  "
            "Does not produce any output files."
        ),
    )
    p.add_argument(
        "--dist-dir",
        default=None,
        help=(
            "Output root for generated skills.  "
            "Defaults to <repo_root>/dist/skills."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns an integer exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Resolve source_dir / dist_dir relative to this script's repo root.
    repo_root = Path(__file__).resolve().parent.parent
    if args.source_dir is not None:
        source_dir = Path(args.source_dir).resolve()
    else:
        source_dir = repo_root / "skills" / "source"

    if args.dist_dir is not None:
        dist_dir = Path(args.dist_dir).resolve()
    else:
        dist_dir = DEFAULT_DIST_DIR

    try:
        if args.check:
            metadata, parse_result = validate_and_parse(source_dir)
            print(
                f"[build_skill] VALIDATION OK  "
                f"(skill_id={metadata.get('skill_id')!r}, "
                f"converter_version={CONVERTER_VERSION}, "
                f"markers={len(parse_result.markers)})"
            )
            for mb in parse_result.markers:
                print(
                    f"  marker {mb.name!r}: "
                    f"lines {mb.start_line}-{mb.end_line}, "
                    f"{len(mb.content)} content lines"
                )
            return 0
        else:
            source_date_epoch_raw = os.environ.get("SOURCE_DATE_EPOCH")
            summary = build_all(
                source_dir=source_dir,
                dist_dir=dist_dir,
                repo_root=repo_root,
                source_date_epoch_raw=source_date_epoch_raw,
            )
            print(
                f"[build_skill] BUILD OK  "
                f"(converter_version={CONVERTER_VERSION}, "
                f"cells={len(summary.cells)})"
            )
            for cell in summary.cells:
                print(
                    f"  {cell.mode}/{cell.agent}: "
                    f"{len(cell.files_written)} files written, "
                    f"digest={cell.build_input_digest[:16]}  "
                    f"({cell.cell_dir})"
                )
            return 0

    except UsageError as exc:
        print(f"[build_skill] USAGE ERROR: {exc}", file=sys.stderr)
        return 64
    except BuildError as exc:
        print(f"[build_skill] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
