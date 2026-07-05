"""qgb skill lint: check verification_type=command contract authoring.

Phase 5 Step 5.a-2-4 で実装。`verification_type=command` の contract.json と
それが起動する script を skill 内部で検査する portable helper. qgb 本体には
変更を加えない (philosophy P9 + framework-shape §5 「対象判定を qgb 本体へ
戻さない」境界遵守)。

Cross-platform Python implementation (Windows / macOS / Linux 共通).
PowerShell sibling: check-command-contract.ps1 (Windows native, PS5/7 両対応).

Usage:
    python check-command-contract.py <contract.json> [--script <script_path>]
                                                     [--evidence <stage.log>]

Behaviour notes:
    - If --script is omitted, the script path is derived from
      contract.command for PowerShell runtimes ("-File" -> next arg).
      If derivation fails, C1/C2/C4 emit a hard finding (not a silent skip).
    - C5 (runtime PATH check) emits an advisory note (not a fix-required
      finding) when the runtime is missing on the authoring host, because
      the skill agent's host may differ from the target user environment.

Checks (skills/source/body.md §6.5 + design-stages prompt sec 5.5):
    C1  script extension and confirmed runtime match
    C2  PowerShell 5 target + non-ASCII .ps1 must have UTF-8 BOM
    C3  contract.command is a complete, explicit PowerShell argv
        - first arg basename is exactly powershell.exe / pwsh / pwsh.exe
        - runtime 5 ↔ powershell(.exe), runtime 7 ↔ pwsh(.exe) consistency
        - required flags (-NoLogo -NoProfile -NonInteractive -ExecutionPolicy
          Bypass / for PS7 omit -ExecutionPolicy is acceptable)
        - -File present with a script path immediately after
        - -File argument matches the --script path (if provided)
    C4  PowerShell .ps1 sets [Console]::OutputEncoding to UTF8 (required;
        $OutputEncoding is recommended but does not satisfy C4)
    C5  runtime executable on PATH (advisory; "may differ on user host")
    C6  qgb check stage log contains U+FFFD (mojibake sentinel)

Exit codes:
    0: no fix-required findings (advisories may have been printed)
    1: one or more fix-required findings
    2: usage error / file not found

This script is bundled in the qgb skill distribution; the skill agent calls
it before recommending `qgb design-stages adopt`.
"""

from __future__ import annotations

import argparse
import json
import ntpath
import os
import posixpath
import re
import shutil
import sys
from pathlib import Path, PureWindowsPath
from typing import Optional


FAIL_CODE_FIX_REQUIRED = 1
FAIL_USAGE = 2


# Mapping from contract.runtime (declared by the skill) to expected script extensions.
RUNTIME_EXTENSIONS = {
    "powershell-5": [".ps1"],
    "powershell-7": [".ps1"],
    "bash": [".sh", ".bash"],
    "sh": [".sh"],
    "python": [".py"],
    "node": [".js", ".mjs", ".cjs"],
}

# Allowed PowerShell invoker basenames per runtime (case-insensitive on Windows,
# matched as exact basename equality).
POWERSHELL_INVOKER_BASENAMES = {
    "powershell-5": {"powershell", "powershell.exe"},
    "powershell-7": {"pwsh", "pwsh.exe"},
}


# Required PowerShell preamble pattern for stdout encoding initialization (C4).
# [Console]::OutputEncoding = ... UTF8 is the canonical guarantee for what qgb
# reads from PowerShell's own stdout. $OutputEncoding alone is insufficient
# (it only affects child-process pipelines).
PS_REQUIRED_STDOUT_INIT_PATTERN = (
    r"\[Console\]::OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8"
)
PS_RECOMMENDED_STDOUT_INIT_PATTERN = (
    r"\$OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8"
)


def read_text_strict(path: Path) -> str:
    """Read text file with explicit UTF-8 (BOM tolerant)."""
    return path.read_text(encoding="utf-8-sig")


def has_utf8_bom(path: Path) -> bool:
    """Detect UTF-8 BOM at the start of a file (3 bytes: EF BB BF)."""
    with path.open("rb") as fh:
        return fh.read(3) == b"\xef\xbb\xbf"


def is_pure_ascii(text: str) -> bool:
    """Return True iff text is ASCII-only."""
    try:
        text.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def basename_universal(path_str: str) -> str:
    """Extract basename treating both POSIX and Windows path separators.

    On POSIX hosts, os.path.basename("C:\\foo\\bar.exe") returns the whole
    string because backslash isn't a separator. For lint we must handle both
    styles since contracts may be authored for Windows users from any host.
    """
    # Try POSIX first (forward slash), then Windows (backslash).
    # If the string contains backslash, ntpath handles it correctly.
    if "\\" in path_str:
        return ntpath.basename(path_str)
    return posixpath.basename(path_str)


def has_path_separator(path_str: str) -> bool:
    """True iff path_str contains a path separator (POSIX or Windows)."""
    return "/" in path_str or "\\" in path_str


def normalize_path_for_compare(path_str: str, base_dir: Path) -> str:
    """Normalize a path string for full-path comparison.

    Handles both POSIX (forward slash) and Windows (backslash) styles.
    Relative paths are resolved against base_dir. Returns a normalized
    POSIX-style string for case-insensitive comparison on Windows-like
    paths.
    """
    if "\\" in path_str:
        # Windows-style path string.
        win_path = PureWindowsPath(path_str)
        if win_path.is_absolute():
            return str(win_path).replace("\\", "/").lower()
        # Resolve relative to base_dir.
        candidate = (base_dir / Path(path_str.replace("\\", "/"))).resolve()
        return str(candidate).replace("\\", "/").lower()
    # POSIX-style path string.
    posix_path = Path(path_str)
    if posix_path.is_absolute():
        return str(posix_path.resolve()).replace("\\", "/").lower()
    candidate = (base_dir / posix_path).resolve()
    return str(candidate).replace("\\", "/").lower()


def find_runtime_executable(runtime: str) -> Optional[str]:
    """Return resolved path of a runtime executable, or None if not on PATH."""
    candidates = {
        "powershell-5": ["powershell.exe", "powershell"],
        "powershell-7": ["pwsh.exe", "pwsh"],
        "bash": ["bash"],
        "sh": ["sh"],
        "python": ["python", "python3"],
        "node": ["node"],
    }
    for name in candidates.get(runtime, []):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def derive_script_from_command(contract: dict) -> Optional[Path]:
    """Derive script path from contract.command for PowerShell runtimes.

    PowerShell invocation pattern: ["powershell.exe", ..., "-File", "<path>", ...]
    Returns the path argument that follows -File (case-insensitive), or None
    if not derivable.
    """
    command = contract.get("command")
    if not isinstance(command, list):
        return None
    runtime = contract.get("runtime")
    if runtime not in POWERSHELL_INVOKER_BASENAMES:
        return None
    for i, arg in enumerate(command):
        if str(arg).lower() == "-file" and i + 1 < len(command):
            return Path(command[i + 1])
    return None


def resolve_script_path(
    contract: dict,
    script_arg: Optional[Path],
    contract_path: Path,
) -> Optional[Path]:
    """Resolve script path: --script wins; else derive from contract.command.

    Returns a Path (possibly relative to contract_path's parent) if resolvable,
    else None.
    """
    if script_arg is not None:
        return script_arg
    derived = derive_script_from_command(contract)
    if derived is None:
        return None
    if derived.is_absolute():
        return derived
    # Try a few resolution roots: contract file's dir, cwd.
    contract_dir = contract_path.resolve().parent
    for root in (contract_dir, Path.cwd()):
        candidate = (root / derived).resolve()
        if candidate.exists():
            return candidate
    # Return the relative path as-is; subsequent checks will report missing file.
    return derived


def check_extension_runtime_match(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C1: script 拡張子と confirmed runtime の整合.

    script_path 解決失敗時は PowerShell runtime のみ hard finding
    (PowerShell 系は -File <path> で derive 可能なはず)。
    その他 runtime (bash/python/node 等) は script_path optional として扱う
    (これらの runtime は command 構文が多様で、--script 明示が前提)。
    """
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime is None:
        findings.append(
            "C1: contract.runtime is not declared. Add a runtime field "
            "(e.g. 'powershell-5' / 'bash' / 'python' / 'node') to enable "
            "capability-based dispatch (design-stages prompt sec 5.5, "
            "prompts/design-stages.md in split builds)."
        )
        return findings
    if script_path is None:
        # PowerShell 系: derive できないのは contract.command に -File 形式が
        # ないことを示す → C1 hard finding。それ以外は --script optional 扱い。
        if runtime in POWERSHELL_INVOKER_BASENAMES:
            findings.append(
                "C1: PowerShell script path could not be resolved. Provide "
                "--script or ensure contract.command uses an explicit "
                "'-File <script>' form (body.md §6.5 PowerShell 5 rules)."
            )
        # 非 PowerShell runtime は --script 未指定なら extension 検査を skip
        # (silent skip ではなく、advisory として note を出すのが正しいが、
        #  利用者の認知負荷との balance で simple skip を選択)
        return findings
    expected_exts = RUNTIME_EXTENSIONS.get(runtime, [])
    if expected_exts and script_path.suffix.lower() not in expected_exts:
        findings.append(
            f"C1: script extension '{script_path.suffix}' does not match "
            f"runtime '{runtime}' (expected one of {expected_exts}). "
            "Match the script extension to the confirmed runtime or change "
            "contract.runtime (design-stages prompt sec 5.5, "
            "prompts/design-stages.md in split builds)."
        )
    return findings


def check_powershell_bom(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C2: PowerShell 5 + 非 ASCII .ps1 なのに BOM なし."""
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime != "powershell-5":
        return findings
    if script_path is None:
        findings.append(
            "C2: cannot check BOM because script path is unresolved "
            "(PowerShell 5 runtime requires a .ps1 path via --script or "
            "contract.command's -File argument)."
        )
        return findings
    if script_path.suffix.lower() != ".ps1":
        return findings
    if not script_path.exists():
        findings.append(f"C2: PowerShell script not found: {script_path}")
        return findings
    try:
        text = read_text_strict(script_path)
    except UnicodeDecodeError:
        findings.append(
            f"C2: PowerShell script '{script_path}' is not valid UTF-8. "
            "Save with UTF-8 (BOM tolerated) and ensure no legacy cp932 bytes."
        )
        return findings
    if is_pure_ascii(text):
        return findings
    if not has_utf8_bom(script_path):
        findings.append(
            f"C2: PowerShell 5 target script '{script_path}' contains "
            "non-ASCII characters but has no UTF-8 BOM. PowerShell 5 reads "
            "BOM-less .ps1 as system code page (cp932 on Japanese Windows), "
            "causing parse errors. Save with UTF-8 BOM, or rewrite the "
            "script as pure ASCII with Unicode escape ([char]0x<codepoint>). "
            "See body.md §6.5 PowerShell 5 rules."
        )
    return findings


def check_powershell_argv(
    contract: dict,
    script_path: Optional[Path],
    contract_path: Path,
    script_explicitly_provided: bool = False,
) -> list[str]:
    """C3: PowerShell argv が完全明示か.

    Checks:
    - first arg basename matches invoker for runtime (case-insensitive,
      cross-platform path-style aware: handles both 'powershell.exe' and
      'C:\\path\\powershell.exe')
    - required flags present (PS 5 also needs -ExecutionPolicy Bypass)
      with case-insensitive matching to keep parity with PowerShell's own
      option parser; option values like Bypass also case-insensitive.
    - host options (NoLogo / NoProfile / NonInteractive / ExecutionPolicy)
      must appear BEFORE -File; -File is followed by the script and
      script-side arguments.
    - host options have no duplicates (single occurrence of each).
    - -ExecutionPolicy is immediately followed by 'Bypass' (adjacency).
    - -File present exactly once, followed by a script path (not another flag).
    - -File argument resolves to same full path as --script argument when
      either side is absolute; otherwise basename equality.
    """
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime not in POWERSHELL_INVOKER_BASENAMES:
        return findings
    command = contract.get("command")
    if not isinstance(command, list) or not command:
        findings.append(
            "C3: contract.command is not a non-empty list. "
            "For verification_type=command, contract.command must be the "
            "argv as a list (body.md §6.5 step 4)."
        )
        return findings

    # Normalize argv to strings; build a case-insensitive lower form for
    # option matching (PowerShell's parser is case-insensitive on option
    # names and on Bypass). Path arguments retain original casing.
    command_str = [str(arg) for arg in command]
    command_lower = [arg.lower() for arg in command_str]

    # First arg: invoker basename, cross-platform path style aware.
    allowed_invokers = POWERSHELL_INVOKER_BASENAMES[runtime]
    first_basename = basename_universal(command_str[0]).lower()
    if first_basename not in allowed_invokers:
        findings.append(
            f"C3: contract.command[0] basename = '{first_basename}' is not "
            f"a recognized invoker for runtime '{runtime}' (expected one of "
            f"{sorted(allowed_invokers)}). PowerShell runtimes require an "
            "explicit invoker as the first argv element. "
            "See body.md §6.5 PowerShell 5 rules."
        )
        # Continue: remaining checks may still surface issues.

    # Required flags. Each required flag may be satisfied by its canonical
    # name OR any of its documented abbreviations. PowerShell's parser
    # accepts either form. We model this as a list of synonym groups.
    required_flag_synonyms = [
        ("-nologo", "-nol"),
        ("-noprofile", "-nop"),
        ("-noninteractive", "-noni"),
    ]
    if runtime == "powershell-5":
        required_flag_synonyms.extend(
            [
                ("-executionpolicy", "-ex", "-ep"),
                ("bypass",),  # value is case-insensitive; only canonical form valid
            ]
        )
    missing = []
    for group in required_flag_synonyms:
        if not any(synonym in command_lower for synonym in group):
            # Report the canonical (first) name.
            missing.append(group[0])
    if missing:
        findings.append(
            f"C3: PowerShell argv is missing required flags {missing} "
            "(case-insensitive; abbreviations also accepted). These "
            "flags ensure deterministic execution (no profile load, "
            "no interactive prompt, no policy ambiguity). See body.md §6.5."
        )

    # Locate -File (case-insensitive, first occurrence).
    file_idx = -1
    file_count = 0
    for i, lower in enumerate(command_lower):
        if lower == "-file":
            if file_idx < 0:
                file_idx = i
            file_count += 1
    if file_idx < 0:
        findings.append(
            "C3: PowerShell argv is missing '-File <script.ps1>'. "
            ".ps1 must be invoked via -File explicitly (not via positional "
            "argument or shell association). See body.md §6.5."
        )
        return findings
    if file_count > 1:
        findings.append(
            f"C3: '-File' appears {file_count} times in contract.command; "
            "exactly one occurrence is required. PowerShell would use the "
            "first, but the duplicate is misleading. See body.md §6.5."
        )

    # Strict host-option grammar for argv positions BEFORE -File.
    # We enforce an allowlist: any token that starts with '-' and appears
    # before -File must be on the allowed list (full name or accepted
    # abbreviation). This catches two classes of silent failure:
    #   (a) execution-mode options (-Command / -EncodedCommand / variants)
    #       that are mutually exclusive with -File: PowerShell runs the
    #       command body and treats -File + path as string arguments,
    #       never executing the target script (exit 0 + wrong stdout).
    #   (b) unknown / typo'd options before -File that PowerShell either
    #       errors on or silently misinterprets.
    # See:
    #   PS5: https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_powershell_exe
    #   PS7: https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_pwsh
    #
    # Runtime-separated tables. PowerShell's parser is case-insensitive on
    # option names and on values like Bypass; we enumerate documented
    # abbreviations rather than allow arbitrary prefixes (prefix-matching is
    # locale/version-sensitive and invites collisions with future options).
    #
    # NOTE: help-mode options (-Help / -? / /?) are intentionally EXCLUDED
    # from the allowlist: they are mutually exclusive with -File in practice
    # (PowerShell prints help and exits without running the script).
    allowed_host_options_by_runtime = {
        "powershell-5": {
            "-nologo", "-nol",
            "-noprofile", "-nop",
            "-noninteractive", "-noni",
            "-noexit", "-noe",
            "-executionpolicy", "-ex", "-ep",
            "-windowstyle", "-w",
            "-version", "-v",
            "-mta",
            "-sta",
            "-psconsolefile", "-psc",
            "-inputformat", "-inp", "-if",
            "-outputformat", "-out", "-of",
            "-configurationname", "-config",
            "-encodedarguments", "-encodedargs",
        },
        "powershell-7": {
            "-nologo", "-nol",
            "-noprofile", "-nop",
            "-noninteractive", "-noni",
            "-noexit", "-noe",
            "-noprofileloadtime", "-noprofileloadtim",
            "-executionpolicy", "-ex", "-ep",
            "-windowstyle", "-w",
            "-version", "-v",
            "-mta",
            "-sta",
            "-inputformat", "-inp", "-if",
            "-outputformat", "-o", "-of",
            "-interactive", "-i",
            "-login", "-l",
            "-configurationname", "-config",
            "-configurationfile",
            "-custompipename",
            "-settingsfile", "-settings",
            "-sshservermode", "-sshs",
            "-workingdirectory", "-wd", "-wo",
        },
    }
    # Execution-mode options that are mutually exclusive with -File.
    # Detection of these in the pre-File range produces a more specific
    # finding than the generic allowlist failure.
    exec_mode_options_by_runtime = {
        "powershell-5": {
            "-command", "-c",
            "-encodedcommand", "-ec",
            # help-mode also runs to completion without -File:
            "-help", "-?", "/?",
        },
        "powershell-7": {
            "-command", "-c",
            "-encodedcommand", "-e", "-ec",
            "-commandwithargs", "-cwa",
            # help-mode also runs to completion without -File:
            "-help", "-?", "/?",
        },
    }
    allowed_host_options_pre_file = allowed_host_options_by_runtime.get(runtime, set())
    exec_mode_options = exec_mode_options_by_runtime.get(runtime, set())

    # Walk argv positions [1, file_idx) and validate each '-'-prefixed token.
    # We also need to skip option values: -ExecutionPolicy is followed by
    # 'Bypass', -WindowStyle by 'Hidden', etc. To keep this simple and
    # conservative, we treat any non-flag token as a value of the preceding
    # flag; this matches PowerShell's positional-argument convention.
    i = 1
    while i < file_idx:
        token_lower = command_lower[i]
        token_orig = command_str[i]
        if token_lower.startswith("-") or token_lower.startswith("/"):
            if token_lower in exec_mode_options:
                findings.append(
                    f"C3: contract.command contains '{token_orig}' at "
                    f"position {i}, which is a PowerShell execution-mode "
                    "option (-Command / -c / -EncodedCommand / -ec). It is "
                    "mutually exclusive with -File: PowerShell would run "
                    "the command body and treat -File + path as string "
                    "arguments, never executing the target script "
                    "(exit 0 with the wrong stdout). Choose exactly one "
                    "execution mode. For verification_type=command "
                    "contracts that invoke .ps1, use -File only. "
                    "See body.md §6.5."
                )
            elif token_lower not in allowed_host_options_pre_file:
                findings.append(
                    f"C3: contract.command contains '{token_orig}' at "
                    f"position {i} (before -File), which is not a "
                    "recognized PowerShell host option. PowerShell either "
                    "errors on this or silently misinterprets it. "
                    "Allowed host options (and their accepted abbreviations): "
                    f"{sorted(allowed_host_options_pre_file)}. See body.md §6.5."
                )
        i += 1

    # Structure: all host options must appear BEFORE -File. Anything after
    # -File is the script path or script-side arguments, not host options.
    host_option_lowercase = {
        "-nologo",
        "-noprofile",
        "-noninteractive",
        "-executionpolicy",
        "-command",
        "-encodedcommand",
        "-windowstyle",
        "-version",
        "-mta",
        "-sta",
        "-psconsolefile",
        "-inputformat",
        "-outputformat",
    }
    for i in range(file_idx + 2, len(command_lower)):  # skip -File and its path
        if command_lower[i] in host_option_lowercase:
            findings.append(
                f"C3: host option '{command_str[i]}' appears AFTER '-File' "
                "(position " + str(i) + "). Host options must precede -File; "
                "anything after -File is interpreted as script arguments. "
                "See body.md §6.5."
            )

    # Duplicate -ExecutionPolicy check (incl. abbreviations -ex / -ep).
    ep_aliases = {"-executionpolicy", "-ex", "-ep"}
    ep_indices = [
        i for i, lower in enumerate(command_lower) if lower in ep_aliases
    ]
    if len(ep_indices) > 1:
        findings.append(
            f"C3: '-ExecutionPolicy' (or abbreviation -ex / -ep) appears "
            f"{len(ep_indices)} times in contract.command; exactly one "
            "occurrence is required (the duplicate would silently apply a "
            "non-deterministic value). See body.md §6.5."
        )

    # PS 5: -ExecutionPolicy must be IMMEDIATELY followed by Bypass.
    if runtime == "powershell-5" and ep_indices:
        ep_idx = ep_indices[0]
        next_arg = command_lower[ep_idx + 1] if ep_idx + 1 < len(command_lower) else None
        if next_arg != "bypass":
            actual = command_str[ep_idx + 1] if ep_idx + 1 < len(command_str) else None
            ep_form = command_str[ep_idx]
            findings.append(
                f"C3: '{ep_form}' must be immediately followed by "
                f"'Bypass' (case-insensitive), but the next argv element is "
                f"{actual!r}. The current argv would set a different "
                "policy, defeating the deterministic-execution intent. "
                "See body.md §6.5."
            )

    # -File path immediately follows -File.
    if file_idx + 1 >= len(command_str):
        findings.append(
            "C3: '-File' is the last argv element, but a script path is "
            "required immediately after. See body.md §6.5."
        )
        return findings
    file_arg = command_str[file_idx + 1]
    if file_arg.startswith("-"):
        findings.append(
            f"C3: argv item after '-File' is '{file_arg}', which looks "
            "like another flag. Expected a script path. See body.md §6.5."
        )
        return findings

    # If --script was EXPLICITLY provided by the user, compare -File argument
    # to it. When script_path was derived from contract.command's -File
    # value (because --script was omitted), comparing the two is tautological:
    # they came from the same place. Worse, the derived path was resolved
    # against contract_dir or cwd which may differ from the user's actual
    # project layout — comparing it back against the raw -File arg produces
    # spurious mismatches (Codex K=2 r5 fix #1 noted base-dir mismatch).
    #
    # Both -File and --script can be relative paths, but they are interpreted
    # against different base directories at runtime:
    #   -File: relative to the user's project working dir (cwd at `qgb run`)
    #   --script: relative to the lint invocation cwd, or absolute
    # We therefore use a layered comparison:
    #   (a) If either side is absolute, full-path equality after normalization.
    #   (b) Otherwise, basename equality (we cannot disambiguate same-basename
    #       different-dir cases without knowing the user's project layout).
    # Basename equality is intentionally weak; the proposal author is
    # expected to keep -File and --script aligned. Stronger checks belong
    # in 5.b dogfooding (a real `qgb check` against a fixture project).
    if script_path is not None and script_explicitly_provided:
        file_path_obj = Path(file_arg) if "\\" not in file_arg else PureWindowsPath(file_arg)
        either_absolute = (
            file_path_obj.is_absolute() or script_path.is_absolute()
        )
        if either_absolute:
            try:
                contract_dir = contract_path.resolve().parent
                file_norm = normalize_path_for_compare(file_arg, contract_dir)
                script_norm = normalize_path_for_compare(
                    str(script_path), contract_dir
                )
                if file_norm != script_norm:
                    findings.append(
                        f"C3: contract.command -File argument '{file_arg}' "
                        f"does not resolve to the same path as --script "
                        f"'{script_path}' "
                        f"(normalized: {file_norm!r} vs {script_norm!r}). "
                        "The skill must invoke exactly the script under "
                        "review."
                    )
            except (OSError, ValueError) as exc:
                findings.append(
                    f"C3: could not normalize -File path '{file_arg}' or "
                    f"--script '{script_path}' for comparison: {exc}"
                )
        else:
            file_basename = basename_universal(file_arg)
            script_basename = script_path.name
            if file_basename != script_basename:
                findings.append(
                    f"C3: contract.command -File argument basename "
                    f"'{file_basename}' does not match --script basename "
                    f"'{script_basename}'. The skill must invoke exactly "
                    "the script under review (relative paths checked by "
                    "basename only; for stricter check, pass absolute "
                    "paths to both -File and --script)."
                )

    return findings


def check_powershell_stdout_init(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C4: PowerShell .ps1 の冒頭に [Console]::OutputEncoding 初期化必須.

    $OutputEncoding は recommended だが C4 を満たさない (advisory のみ)。
    """
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime not in POWERSHELL_INVOKER_BASENAMES:
        return findings
    if script_path is None:
        findings.append(
            "C4: cannot check [Console]::OutputEncoding init because script "
            "path is unresolved (PowerShell runtime requires a .ps1 path)."
        )
        return findings
    if script_path.suffix.lower() != ".ps1":
        return findings
    if not script_path.exists():
        return findings  # Already reported via C2.
    try:
        text = read_text_strict(script_path)
    except UnicodeDecodeError:
        return findings  # Already reported via C2.

    has_required = re.search(PS_REQUIRED_STDOUT_INIT_PATTERN, text) is not None
    if not has_required:
        findings.append(
            f"C4: PowerShell script '{script_path}' does not set "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8. "
            "This is required; $OutputEncoding alone is insufficient (it "
            "only affects child-process pipelines, not qgb's read of "
            "PowerShell's own stdout). Without [Console]::OutputEncoding, "
            "stdout may use system code page (cp932 on Japanese Windows), "
            "causing qgb's UTF-8 decode to produce U+FFFD characters. "
            "See body.md §6.5 + design-stages prompt sec 5.5 PowerShell "
            "checklist (prompts/design-stages.md in split builds)."
        )
    return findings


def check_runtime_available(contract: dict) -> tuple[list[str], list[str]]:
    """C5: 確定 runtime が PATH に存在するか (advisory only).

    Returns (findings, advisories). findings are fix-required; advisories
    are non-blocking informational notes (the user's host may differ).
    """
    findings: list[str] = []
    advisories: list[str] = []
    runtime = contract.get("runtime")
    if runtime is None:
        return findings, advisories
    resolved = find_runtime_executable(runtime)
    if resolved is None:
        advisories.append(
            f"C5 (advisory): runtime '{runtime}' executable not found on "
            "this host's PATH. This is the skill-agent's local environment; "
            "the target user environment may differ. Verify availability "
            "on the user's host before relying on this contract."
        )
    return findings, advisories


def check_evidence_mojibake(evidence_path: Optional[Path]) -> list[str]:
    """C6: qgb check stage log に U+FFFD が含まれていないか."""
    findings: list[str] = []
    if evidence_path is None:
        return findings
    if not evidence_path.exists():
        findings.append(
            f"C6: evidence/stage log '{evidence_path}' not found. "
            "Run `python -m qgb check` first, then re-run this lint with "
            "--evidence <path-to-stage-log>."
        )
        return findings
    try:
        text = read_text_strict(evidence_path)
    except UnicodeDecodeError:
        findings.append(
            f"C6: evidence log '{evidence_path}' is not valid UTF-8."
        )
        return findings
    replacement_count = text.count("�")
    if replacement_count > 0:
        findings.append(
            f"C6: stage log '{evidence_path}' contains {replacement_count} "
            "U+FFFD (replacement character) occurrence(s). This indicates "
            "command stdout/stderr was not valid UTF-8 (likely cp932 or "
            "another encoding). Fix script's output encoding (e.g. set "
            "[Console]::OutputEncoding = UTF8 for PowerShell, "
            "PYTHONUTF8=1 for Python). See body.md §6.5 κ mojibake sentinel."
        )
    return findings


def check_powershell_output_encoding_advisory(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """Advisory: $OutputEncoding (child process) is recommended for PowerShell.

    This is separate from C4 (which requires [Console]::OutputEncoding).
    Missing $OutputEncoding does NOT fail the lint; it only emits an
    informational note.
    """
    advisories: list[str] = []
    runtime = contract.get("runtime")
    if runtime not in POWERSHELL_INVOKER_BASENAMES:
        return advisories
    if script_path is None or not script_path.exists():
        return advisories
    if script_path.suffix.lower() != ".ps1":
        return advisories
    try:
        text = read_text_strict(script_path)
    except UnicodeDecodeError:
        return advisories
    has_recommended = re.search(PS_RECOMMENDED_STDOUT_INIT_PATTERN, text) is not None
    if not has_recommended:
        advisories.append(
            f"advisory (PowerShell recommended): script '{script_path}' does "
            "not set $OutputEncoding = [System.Text.Encoding]::UTF8. While "
            "not required by C4, it is recommended when the script pipes "
            "output to child processes that expect UTF-8."
        )
    return advisories


def run_checks(
    contract_path: Path,
    script_path_arg: Optional[Path],
    evidence_path: Optional[Path],
) -> int:
    """Run all checks, print findings + advisories, return exit code."""
    script_explicitly_provided = script_path_arg is not None
    try:
        contract = json.loads(read_text_strict(contract_path))
    except FileNotFoundError:
        print(f"ERROR: contract not found: {contract_path}", file=sys.stderr)
        return FAIL_USAGE
    except json.JSONDecodeError as e:
        print(f"ERROR: contract is not valid JSON: {e}", file=sys.stderr)
        return FAIL_USAGE

    if contract.get("verification_type") != "command":
        print(
            "INFO: contract.verification_type is not 'command', skipping "
            "command authoring lint.",
            file=sys.stderr,
        )
        return 0

    # Resolve script path: --script wins; else derive from contract.command.
    script_path = resolve_script_path(contract, script_path_arg, contract_path)

    findings: list[str] = []
    advisories: list[str] = []

    findings.extend(check_extension_runtime_match(contract, script_path))
    findings.extend(check_powershell_bom(contract, script_path))
    findings.extend(
        check_powershell_argv(
            contract,
            script_path,
            contract_path,
            script_explicitly_provided=script_explicitly_provided,
        )
    )
    findings.extend(check_powershell_stdout_init(contract, script_path))
    runtime_findings, runtime_advisories = check_runtime_available(contract)
    findings.extend(runtime_findings)
    advisories.extend(runtime_advisories)
    findings.extend(check_evidence_mojibake(evidence_path))
    advisories.extend(check_powershell_output_encoding_advisory(contract, script_path))

    if advisories:
        print(f"NOTE: {len(advisories)} advisory note(s):", file=sys.stderr)
        for i, note in enumerate(advisories, start=1):
            print(f"  ({i}) {note}", file=sys.stderr)

    if not findings:
        print("OK: all fix-required checks passed.")
        return 0

    print(f"FAIL: {len(findings)} fix-required finding(s):", file=sys.stderr)
    for i, finding in enumerate(findings, start=1):
        print(f"  [{i}] {finding}", file=sys.stderr)
    return FAIL_CODE_FIX_REQUIRED


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "qgb skill lint for verification_type=command contracts. "
            "Checks runtime/script/encoding/argv consistency before adopt."
        )
    )
    parser.add_argument(
        "contract",
        type=Path,
        help="Path to contract.json (the stage contract being authored).",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=None,
        help=(
            "Optional path to the script that contract.command invokes. "
            "If omitted, the script path is derived from contract.command "
            "for PowerShell runtimes ('-File <path>'). Required if "
            "derivation fails (C1/C2/C4 emit a hard finding rather than "
            "skipping silently)."
        ),
    )
    parser.add_argument(
        "--evidence",
        type=Path,
        default=None,
        help=(
            "Optional path to a stage log from `qgb check`. "
            "Required for C6 (U+FFFD mojibake sentinel)."
        ),
    )
    args = parser.parse_args(argv)
    return run_checks(args.contract, args.script, args.evidence)


if __name__ == "__main__":
    sys.exit(main())
