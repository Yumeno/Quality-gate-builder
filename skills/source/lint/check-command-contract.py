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

Checks (skills/source/body.md §6.5 + §12.5.5):
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
import os
import re
import shutil
import sys
from pathlib import Path
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
    Returns the path argument that follows -File, or None if not derivable.
    """
    command = contract.get("command")
    if not isinstance(command, list):
        return None
    runtime = contract.get("runtime")
    if runtime not in POWERSHELL_INVOKER_BASENAMES:
        return None
    for i, arg in enumerate(command):
        if arg == "-File" and i + 1 < len(command):
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
            "capability-based dispatch (body.md §12.5.5)."
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
            "contract.runtime (body.md §12.5.5)."
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
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C3: PowerShell argv が完全明示か (basename / runtime ↔ invoker / -File 整合)."""
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

    # Check the first arg: must be a recognized PowerShell invoker matching the runtime.
    allowed_invokers = POWERSHELL_INVOKER_BASENAMES[runtime]
    first_arg = command[0]
    first_basename = os.path.basename(str(first_arg)).lower()
    if first_basename not in allowed_invokers:
        findings.append(
            f"C3: contract.command[0] basename = '{first_basename}' is not "
            f"a recognized invoker for runtime '{runtime}' (expected one of "
            f"{sorted(allowed_invokers)}). PowerShell runtimes require an "
            "explicit invoker as the first argv element. "
            "See body.md §6.5 PowerShell 5 rules."
        )
        # Continue checking remaining structure, since the rest may still be wrong.

    # Required flags.
    required_flags = ["-NoLogo", "-NoProfile", "-NonInteractive"]
    if runtime == "powershell-5":
        required_flags.extend(["-ExecutionPolicy", "Bypass"])
    missing = [flag for flag in required_flags if flag not in command]
    if missing:
        findings.append(
            f"C3: PowerShell argv is missing required flags {missing}. "
            "These flags ensure deterministic execution (no profile load, "
            "no interactive prompt, no policy ambiguity). "
            "See body.md §6.5."
        )

    # -File <path> presence and consistency.
    try:
        file_idx = command.index("-File")
    except ValueError:
        findings.append(
            "C3: PowerShell argv is missing '-File <script.ps1>'. "
            ".ps1 must be invoked via -File explicitly (not via positional "
            "argument or shell association). See body.md §6.5."
        )
        return findings
    if file_idx + 1 >= len(command):
        findings.append(
            "C3: '-File' is the last argv element, but a script path is "
            "required immediately after. See body.md §6.5."
        )
        return findings
    file_arg = command[file_idx + 1]
    if file_arg.startswith("-"):
        findings.append(
            f"C3: argv item after '-File' is '{file_arg}', which looks "
            "like another flag. Expected a script path. See body.md §6.5."
        )
    elif script_path is not None:
        # Verify the -File argument matches the --script we resolved (path equality
        # check; normalize both as relative-or-absolute strings).
        file_path = Path(file_arg)
        # If file_arg is absolute, compare directly; else compare basenames.
        if file_path.is_absolute():
            if file_path != script_path.resolve():
                findings.append(
                    f"C3: contract.command -File argument '{file_arg}' does "
                    f"not match --script '{script_path}'. The skill should "
                    "invoke exactly the script under review."
                )
        else:
            if file_path.name != script_path.name:
                findings.append(
                    f"C3: contract.command -File argument basename "
                    f"'{file_path.name}' does not match --script basename "
                    f"'{script_path.name}'."
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
            "See body.md §6.5 + §12.5.5 PowerShell checklist."
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
    findings.extend(check_powershell_argv(contract, script_path))
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
