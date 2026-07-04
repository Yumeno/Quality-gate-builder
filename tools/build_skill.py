"""build_skill.py -- Phase 5 Step 5.b Stage 2: VALIDATION + PARSE phase only.

Stage 3 will add: full/split render, digest, and output writing.

Exit codes:
  0  -- success (--check passed; bare builds succeed once stage 3 lands)
  2  -- validation / parse failure, or bare build before stage 3 (BuildError)
  64 -- usage error (UsageError)
"""

from __future__ import annotations

import argparse
import json
import re
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
        import yaml  # type: ignore[import]
    except ImportError:
        raise BuildError(
            "PyYAML is required to parse agent doc front matter."
        )

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
    except ImportError:
        raise BuildError("PyYAML is required.")

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
    return p


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.  Returns an integer exit code."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    # Resolve source_dir.
    if args.source_dir is not None:
        source_dir = Path(args.source_dir).resolve()
    else:
        # Default: <repo_root>/skills/source
        # repo_root = parent of this script's parent (tools/ -> repo_root).
        repo_root = Path(__file__).resolve().parent.parent
        source_dir = repo_root / "skills" / "source"

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
            # Fail-closed: a build was requested but generation is not
            # implemented until stage 3.  Reporting success for a no-op
            # build would let CI treat "nothing was built" as a completed
            # build.  Validation still runs first for early feedback (its
            # failures surface with their own messages, same exit code).
            validate_and_parse(source_dir)
            print(
                "[build_skill] ERROR: generation is not implemented yet "
                "(stage 3); no output was produced.  "
                "Use --check for validation-only runs.",
                file=sys.stderr,
            )
            return 2

    except UsageError as exc:
        print(f"[build_skill] USAGE ERROR: {exc}", file=sys.stderr)
        return 64
    except BuildError as exc:
        print(f"[build_skill] ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
