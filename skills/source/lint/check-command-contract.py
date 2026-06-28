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

Checks (skills/source/body.md §6.5 + §12.5.5):
    C1  script 拡張子と確定 runtime の整合 (例: PowerShell 5 確定なのに .sh は error)
    C2  PowerShell 5 対象かつ非 ASCII .ps1 なのに BOM がない
    C3  .ps1 を shell=False の argv で直接起動しようとしている
        (= "<script.ps1>" だけを contract.command に書く誤り)
    C4  stdout encoding の初期化が script 内にない (PowerShell .ps1 のみ)
    C5  command が存在しない runtime を指定している (PATH に runtime がない)
    C6  qgb check の log に U+FFFD (replacement character) がある
        (= κ mojibake sentinel、cp932→UTF-8 誤 decode 検出)

Exit codes:
    0: 全 check pass (proposal adopt 可)
    1: 1 件以上の必須 fix (proposal を直してから adopt)
    2: usage error / file not found

This script is bundled in the qgb skill distribution; the skill agent calls
it before recommending `qgb design-stages adopt`.
"""

from __future__ import annotations

import argparse
import json
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


# PowerShell command-line indicator patterns. Used to check (C3) — whether
# the contract.command argv invokes PowerShell explicitly rather than letting
# the OS resolve a .ps1 via shell association.
POWERSHELL_INVOKERS = ("powershell", "powershell.exe", "pwsh", "pwsh.exe")


# Required PowerShell preamble fragments for stdout encoding initialization (C4).
PS_STDOUT_INIT_PATTERNS = [
    r"\[Console\]::OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8",
    r"\$OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8",
]


def read_text_strict(path: Path) -> str:
    """Read text file with explicit UTF-8 (BOM tolerant), error out on decode failure."""
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


def check_extension_runtime_match(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C1: script 拡張子と confirmed runtime の整合."""
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
    if runtime != "powershell-5" or script_path is None:
        return findings
    if script_path.suffix.lower() != ".ps1":
        return findings
    try:
        text = read_text_strict(script_path)
    except FileNotFoundError:
        findings.append(f"C2: PowerShell script not found: {script_path}")
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


def check_powershell_argv(contract: dict) -> list[str]:
    """C3: .ps1 を shell=False の argv で直接起動しようとしている."""
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime not in ("powershell-5", "powershell-7"):
        return findings
    command = contract.get("command")
    if not isinstance(command, list) or not command:
        findings.append(
            "C3: contract.command is not a non-empty list. "
            "For verification_type=command, contract.command must be the "
            "argv as a list (body.md §6.5 step 4)."
        )
        return findings
    first = str(command[0])
    if not any(invoker in first.lower() for invoker in POWERSHELL_INVOKERS):
        findings.append(
            f"C3: contract.command[0] = '{first}' does not look like a "
            "PowerShell invoker. .ps1 cannot be executed directly as the "
            "first argv item; you need: "
            "['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', "
            "'-ExecutionPolicy', 'Bypass', '-File', '<script.ps1>']. "
            "See body.md §6.5 PowerShell 5 rules."
        )
        return findings
    # Verify the PowerShell-recommended args are present.
    required_flags = ["-NoLogo", "-NoProfile", "-NonInteractive"]
    missing = [flag for flag in required_flags if flag not in command]
    if missing:
        findings.append(
            f"C3: PowerShell argv is missing recommended flags {missing}. "
            "These flags ensure deterministic execution (no profile load, "
            "no interactive prompt). See body.md §6.5."
        )
    return findings


def check_powershell_stdout_init(
    contract: dict, script_path: Optional[Path]
) -> list[str]:
    """C4: PowerShell .ps1 の冒頭に [Console]::OutputEncoding 初期化があるか."""
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime not in ("powershell-5", "powershell-7") or script_path is None:
        return findings
    if script_path.suffix.lower() != ".ps1":
        return findings
    try:
        text = read_text_strict(script_path)
    except FileNotFoundError:
        return findings  # already reported in C2
    if not any(re.search(pat, text) for pat in PS_STDOUT_INIT_PATTERNS):
        findings.append(
            f"C4: PowerShell script '{script_path}' does not initialize "
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8 "
            "(or $OutputEncoding equivalent). Without this, stdout may "
            "use system code page (cp932 on Japanese Windows), causing "
            "qgb's UTF-8 decode to produce U+FFFD characters. "
            "See body.md §6.5 + §12.5.5 PowerShell checklist."
        )
    return findings


def check_runtime_available(contract: dict) -> list[str]:
    """C5: 確定 runtime が PATH に存在するか."""
    findings: list[str] = []
    runtime = contract.get("runtime")
    if runtime is None:
        return findings
    resolved = find_runtime_executable(runtime)
    if resolved is None:
        findings.append(
            f"C5: runtime '{runtime}' executable not found on PATH. "
            "Either install the runtime, or change contract.runtime to "
            "one available in the target environment. "
            "(This check runs in the skill's local env; the user environment "
            "may differ — verify with the user.)"
        )
    return findings


def check_evidence_mojibake(evidence_path: Optional[Path]) -> list[str]:
    """C6: qgb check の stage log に U+FFFD が含まれていないか."""
    findings: list[str] = []
    if evidence_path is None:
        return findings
    try:
        text = read_text_strict(evidence_path)
    except FileNotFoundError:
        findings.append(
            f"C6: evidence/stage log '{evidence_path}' not found. "
            "Run `python -m qgb check` first, then re-run this lint with "
            "--evidence <path-to-stage-log>."
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


def run_checks(
    contract_path: Path,
    script_path: Optional[Path],
    evidence_path: Optional[Path],
) -> int:
    """Run all checks, print findings, return exit code."""
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

    findings: list[str] = []
    findings.extend(check_extension_runtime_match(contract, script_path))
    findings.extend(check_powershell_bom(contract, script_path))
    findings.extend(check_powershell_argv(contract))
    findings.extend(check_powershell_stdout_init(contract, script_path))
    findings.extend(check_runtime_available(contract))
    findings.extend(check_evidence_mojibake(evidence_path))

    if not findings:
        print("OK: all checks passed.")
        return 0

    print(f"FAIL: {len(findings)} finding(s):", file=sys.stderr)
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
            "Required for C1/C2/C4 (extension match, BOM check, stdout init)."
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
