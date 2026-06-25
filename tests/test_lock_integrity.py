"""Lock-file integrity tests (Phase 3 Step 3.2).

These tests don't run pip; they verify static properties of the committed
``requirements.lock`` / ``requirements-dev.lock`` files. The CI job
``lock-integrity`` exercises the dynamic side (regenerating with
``pip-compile`` and diffing against the committed locks).

The intent here is to keep the lock files structurally well-formed so a
malformed lock cannot pass review unnoticed.

References:
- ``development/docs/journal/phase3-step3-2-prejournal.md`` §E
- ``SECURITY.md`` "Dependency Lock Policy"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on Python 3.10 in CI
    import tomli as tomllib  # type: ignore[no-redef]

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"
RUNTIME_LOCK = REPO_ROOT / "requirements.lock"
DEV_LOCK = REPO_ROOT / "requirements-dev.lock"

# Lines that pin a package: ``name==version[ ; env_marker] \\`` followed by hash lines.
# Package names follow PEP 503: letters, digits, ``.``, ``-``, ``_``.
# pip-tools 7.5.x emits markers in the ``# via`` comment block rather than
# inline, but a future version (or a different lock tool) may emit them
# inline; the ``(?:\s*;[^\\]*?)?`` makes the parse robust to that.
_PIN_LINE = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+?)(?:\s*;[^\\]*?)?\s*\\?\s*$"
)
_HASH_LINE = re.compile(r"^\s+--hash=sha256:[0-9a-f]{64}\s*\\?\s*$")


def _parse_lock(path: Path) -> dict[str, list[str]]:
    """Return ``{package_name_lowered: [hashes...]}`` for a pip-compile lock.

    Comment / blank / via-comment lines are ignored. We do not attempt to
    distinguish ``--allow-unsafe`` packages from regular ones; for the
    purposes of these tests, every pinned ``name==version`` block must
    carry at least one ``--hash=sha256:...`` line.
    """
    pkgs: dict[str, list[str]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        m_pin = _PIN_LINE.match(line)
        if m_pin:
            current = m_pin.group(1).lower()
            pkgs.setdefault(current, [])
            continue
        m_hash = _HASH_LINE.match(line)
        if m_hash and current is not None:
            pkgs[current].append(line.strip())
            continue
        # via-comment or continuation noise — ignore
    return pkgs


def _read_pyproject_runtime_deps() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8-sig"))
    project = data.get("project", {})
    return {
        _split_name(spec).lower()
        for spec in project.get("dependencies", [])
    }


def _read_pyproject_dev_extras() -> set[str]:
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8-sig"))
    project = data.get("project", {})
    opt = project.get("optional-dependencies", {})
    return {_split_name(spec).lower() for spec in opt.get("dev", [])}


def _split_name(requirement_spec: str) -> str:
    """Extract the bare distribution name from a PEP 508 requirement string.

    Handles ``foo``, ``foo>=1.2``, ``foo[extra]``, ``foo>=1.2,<2`` and trims
    surrounding whitespace. We don't need a full PEP 508 parser; only the
    leading name token matters for set comparison.
    """
    s = requirement_spec.strip()
    # cut at the first non-name character
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", s)
    assert m is not None, f"Cannot parse requirement: {requirement_spec!r}"
    return m.group(1)


def test_runtime_lock_exists() -> None:
    assert RUNTIME_LOCK.is_file(), "requirements.lock must be committed"


def test_dev_lock_exists() -> None:
    assert DEV_LOCK.is_file(), "requirements-dev.lock must be committed"


def test_runtime_lock_has_hashes_for_every_pin() -> None:
    pkgs = _parse_lock(RUNTIME_LOCK)
    assert pkgs, "runtime lock parsed empty — file may be malformed"
    missing = [name for name, hashes in pkgs.items() if not hashes]
    assert not missing, (
        f"runtime lock has packages without --hash lines: {missing}. "
        "pip install --require-hashes will refuse these."
    )


def test_dev_lock_has_hashes_for_every_pin() -> None:
    pkgs = _parse_lock(DEV_LOCK)
    assert pkgs, "dev lock parsed empty — file may be malformed"
    missing = [name for name, hashes in pkgs.items() if not hashes]
    assert not missing, (
        f"dev lock has packages without --hash lines: {missing}. "
        "pip install --require-hashes will refuse these."
    )


def test_runtime_lock_contains_all_declared_runtime_deps() -> None:
    declared = _read_pyproject_runtime_deps()
    pinned = set(_parse_lock(RUNTIME_LOCK).keys())
    missing = declared - pinned
    assert not missing, (
        f"runtime lock is missing packages declared in "
        f"pyproject.toml [project.dependencies]: {missing}. "
        "The lock is stale — regenerate per SECURITY.md."
    )


def test_dev_lock_contains_all_declared_dev_extras() -> None:
    declared = _read_pyproject_dev_extras()
    pinned = set(_parse_lock(DEV_LOCK).keys())
    missing = declared - pinned
    assert not missing, (
        f"dev lock is missing packages declared in "
        f"pyproject.toml [project.optional-dependencies.dev]: {missing}. "
        "The lock is stale — regenerate per SECURITY.md."
    )


def test_dev_lock_is_layered_on_runtime_lock() -> None:
    """``requirements-dev.lock`` must declare ``-c requirements.lock`` in its
    pip-compile invocation header. This is how layered locking prevents the
    dev install from overriding runtime pins (see SECURITY.md).
    """
    head = DEV_LOCK.read_text(encoding="utf-8-sig")
    # pip-compile records the exact command in the header comment block.
    # We accept either --constraint= or -c form.
    assert (
        "--constraint=requirements.lock" in head
        or "-c requirements.lock" in head
    ), (
        "dev lock header does not show the runtime-lock constraint. "
        "Regenerate with --constraint=requirements.lock per SECURITY.md."
    )


def test_runtime_lock_packages_appear_in_dev_lock_at_same_version() -> None:
    """Because dev lock is generated with ``-c requirements.lock``, every
    runtime-locked package that also appears in the dev resolution must be
    pinned to the same version. This is the structural payoff of layered
    locking — if it fails, the layering broke.
    """
    runtime = _parse_runtime_versions()
    dev = _parse_dev_versions()
    for name, runtime_version in runtime.items():
        dev_version = dev.get(name)
        if dev_version is None:
            # Some runtime packages may not appear in the dev resolution at
            # all (e.g. if dev tooling doesn't transitively depend on them).
            # That is fine; we only check shared packages.
            continue
        assert dev_version == runtime_version, (
            f"package {name!r} pinned to {runtime_version} in runtime lock "
            f"but {dev_version} in dev lock — layering is broken. "
            "Regenerate dev lock with --constraint=requirements.lock."
        )


def _parse_runtime_versions() -> dict[str, str]:
    return _parse_versions(RUNTIME_LOCK)


def _parse_dev_versions() -> dict[str, str]:
    return _parse_versions(DEV_LOCK)


def _parse_versions(path: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.rstrip()
        m = _PIN_LINE.match(line)
        if m:
            versions[m.group(1).lower()] = m.group(2)
    return versions


@pytest.mark.parametrize("lock_path", [RUNTIME_LOCK, DEV_LOCK])
def test_lock_does_not_contain_editable_or_git_refs(lock_path: Path) -> None:
    """A hash-pinned lock must not contain ``-e`` / ``--editable`` /
    ``git+https://...`` references; those defeat hash verification because
    pip cannot compute a stable hash for a moving source.
    """
    text = lock_path.read_text(encoding="utf-8-sig")
    forbidden_markers = [
        "\n-e ",
        "\n--editable",
        "git+http",
        "git+ssh",
        "file://",
    ]
    found = [m for m in forbidden_markers if m in text]
    assert not found, (
        f"{lock_path.name} contains forbidden install markers: {found}. "
        "These bypass --require-hashes."
    )


def test_pin_line_regex_parses_inline_env_marker(tmp_path: Path) -> None:
    """Guard against regression of M3 (Codex 段 3 r1 code fix follow-up).

    Phase 3 Step 3.2 補修 M3 extended ``_PIN_LINE`` to optionally match
    PEP 508-style inline environment markers (``; python_version < "3.13"``)
    that some pip-compile versions or alternative lock tools emit. The
    committed locks in this repo don't currently exercise that path —
    pip-tools 7.5.3 keeps markers in the ``# via`` comment block — so we
    pin the behaviour with a tiny synthetic lock fixture. If a future
    refactor narrows ``_PIN_LINE`` again the test catches it before
    a pip-tools bump silently breaks parsing of real locks.
    """
    fake_lock = tmp_path / "fake.lock"
    fake_lock.write_text(
        "#\n"
        "# Synthetic test fixture, not a real pip-compile output.\n"
        "#\n"
        "marker-pkg==1.2.3 ; python_version < \"3.13\" \\\n"
        "    --hash=sha256:" + "a" * 64 + "\n"
        "plain-pkg==4.5.6 \\\n"
        "    --hash=sha256:" + "b" * 64 + "\n",
        encoding="utf-8",
    )
    parsed = _parse_lock(fake_lock)
    assert "marker-pkg" in parsed, (
        "_PIN_LINE failed to match a name==version line that carries an "
        "inline PEP 508 environment marker. M3 補修 was meant to handle "
        "this; the regex regressed."
    )
    assert len(parsed["marker-pkg"]) == 1, (
        "Hash line after a marker-bearing pin should still be attributed "
        "to the marker-bearing package."
    )
    versions = _parse_versions(fake_lock)
    assert versions["marker-pkg"] == "1.2.3"
    assert versions["plain-pkg"] == "4.5.6"
