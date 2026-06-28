# qgb skill lint: check verification_type=command contract authoring.
#
# Phase 5 Step 5.a-2-4 で実装。verification_type=command の contract.json と
# それが起動する script を skill 内部で検査する Windows native PowerShell
# implementation. qgb 本体には変更を加えない (philosophy P9 + framework-shape
# §5 「対象判定を qgb 本体へ戻さない」境界遵守)。
#
# PowerShell 5/7 両対応、pure ASCII + Unicode escape で書かれているため
# BOM 不要 (JP keyword は [char]0x<codepoint> で構築)。
# Python sibling: check-command-contract.py (cross-platform)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -NoProfile -File check-command-contract.ps1 `
#     -Contract <path> [-Script <path>] [-Evidence <path>]
#
# Checks (skills/source/body.md §6.5 + §12.5.5):
#   C1  script extension matches confirmed runtime
#   C2  PowerShell 5 target + non-ASCII .ps1 but no UTF-8 BOM
#   C3  contract.command is not properly an argv list with a PowerShell invoker
#   C4  PowerShell script lacks [Console]::OutputEncoding init
#   C5  runtime executable not on PATH
#   C6  stage log contains U+FFFD (mojibake sentinel)
#
# Exit codes:
#   0: all checks passed
#   1: one or more findings (fix before adopt)
#   2: usage error / file not found

param(
    [Parameter(Mandatory=$true)]
    [string]$Contract,
    [string]$Script = "",
    [string]$Evidence = ""
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ExitFix = 1
$ExitUsage = 2

# Runtime to expected script extensions.
$RuntimeExtensions = @{
    'powershell-5' = @('.ps1')
    'powershell-7' = @('.ps1')
    'bash'         = @('.sh', '.bash')
    'sh'           = @('.sh')
    'python'       = @('.py')
    'node'         = @('.js', '.mjs', '.cjs')
}

# PowerShell invokers for C3.
$PowerShellInvokers = @('powershell', 'powershell.exe', 'pwsh', 'pwsh.exe')

# PowerShell stdout encoding init regex patterns for C4.
$PsStdoutInitPatterns = @(
    '\[Console\]::OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8',
    '\$OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8'
)

# U+FFFD replacement character literal (built from codepoint to keep this
# script pure ASCII and BOM-independent).
$ReplacementChar = [char]0xFFFD

# Read text strictly, BOM tolerant.
function Read-TextStrict {
    param([string]$Path)
    return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($true))
}

# Detect UTF-8 BOM (first 3 bytes = EF BB BF).
function Test-Utf8Bom {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 3) { return $false }
    return $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
}

# True iff string is ASCII-only.
function Test-PureAscii {
    param([string]$Text)
    foreach ($ch in $Text.ToCharArray()) {
        if ([int]$ch -gt 127) { return $false }
    }
    return $true
}

# Find runtime executable on PATH.
function Find-RuntimeExecutable {
    param([string]$Runtime)
    $candidates = @{
        'powershell-5' = @('powershell.exe', 'powershell')
        'powershell-7' = @('pwsh.exe', 'pwsh')
        'bash'         = @('bash')
        'sh'           = @('sh')
        'python'       = @('python', 'python3')
        'node'         = @('node')
    }
    foreach ($name in $candidates[$Runtime]) {
        $cmd = Get-Command -Name $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Check-ExtensionRuntimeMatch {
    param($Contract, $ScriptPath)
    $findings = @()
    $runtime = $Contract.runtime
    if (-not $runtime) {
        $findings += "C1: contract.runtime is not declared. Add a runtime field (e.g. 'powershell-5' / 'bash' / 'python' / 'node') to enable capability-based dispatch (body.md sec 12.5.5)."
        return $findings
    }
    if (-not $ScriptPath) { return $findings }
    $expected = $RuntimeExtensions[$runtime]
    if ($expected -and -not ($expected -contains [System.IO.Path]::GetExtension($ScriptPath).ToLower())) {
        $findings += "C1: script extension '$([System.IO.Path]::GetExtension($ScriptPath))' does not match runtime '$runtime' (expected one of $($expected -join ', ')). Match the script extension to the confirmed runtime or change contract.runtime (body.md sec 12.5.5)."
    }
    return $findings
}

function Check-PowerShellBom {
    param($Contract, $ScriptPath)
    $findings = @()
    if ($Contract.runtime -ne 'powershell-5' -or -not $ScriptPath) { return $findings }
    if ([System.IO.Path]::GetExtension($ScriptPath).ToLower() -ne '.ps1') { return $findings }
    if (-not (Test-Path -LiteralPath $ScriptPath)) {
        $findings += "C2: PowerShell script not found: $ScriptPath"
        return $findings
    }
    $text = Read-TextStrict -Path $ScriptPath
    if (Test-PureAscii -Text $text) { return $findings }
    if (-not (Test-Utf8Bom -Path $ScriptPath)) {
        $findings += "C2: PowerShell 5 target script '$ScriptPath' contains non-ASCII characters but has no UTF-8 BOM. PowerShell 5 reads BOM-less .ps1 as system code page (cp932 on Japanese Windows), causing parse errors. Save with UTF-8 BOM, or rewrite the script as pure ASCII with Unicode escape ([char]0x<codepoint>). See body.md sec 6.5 PowerShell 5 rules."
    }
    return $findings
}

function Check-PowerShellArgv {
    param($Contract)
    $findings = @()
    $runtime = $Contract.runtime
    if ($runtime -ne 'powershell-5' -and $runtime -ne 'powershell-7') { return $findings }
    $command = $Contract.command
    if (-not ($command -is [System.Array]) -or $command.Count -eq 0) {
        $findings += "C3: contract.command is not a non-empty list. For verification_type=command, contract.command must be the argv as a list (body.md sec 6.5 step 4)."
        return $findings
    }
    $first = [string]$command[0]
    $matched = $false
    foreach ($invoker in $PowerShellInvokers) {
        if ($first.ToLower().Contains($invoker)) { $matched = $true; break }
    }
    if (-not $matched) {
        $findings += "C3: contract.command[0] = '$first' does not look like a PowerShell invoker. .ps1 cannot be executed directly as the first argv item; you need: ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', '<script.ps1>']. See body.md sec 6.5 PowerShell 5 rules."
        return $findings
    }
    $required = @('-NoLogo', '-NoProfile', '-NonInteractive')
    $missing = $required | Where-Object { $command -notcontains $_ }
    if ($missing.Count -gt 0) {
        $findings += "C3: PowerShell argv is missing recommended flags ($($missing -join ', ')). These flags ensure deterministic execution (no profile load, no interactive prompt). See body.md sec 6.5."
    }
    return $findings
}

function Check-PowerShellStdoutInit {
    param($Contract, $ScriptPath)
    $findings = @()
    $runtime = $Contract.runtime
    if (($runtime -ne 'powershell-5' -and $runtime -ne 'powershell-7') -or -not $ScriptPath) {
        return $findings
    }
    if ([System.IO.Path]::GetExtension($ScriptPath).ToLower() -ne '.ps1') { return $findings }
    if (-not (Test-Path -LiteralPath $ScriptPath)) { return $findings }
    $text = Read-TextStrict -Path $ScriptPath
    $matched = $false
    foreach ($pat in $PsStdoutInitPatterns) {
        if ($text -match $pat) { $matched = $true; break }
    }
    if (-not $matched) {
        $findings += "C4: PowerShell script '$ScriptPath' does not initialize [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 (or `$OutputEncoding equivalent). Without this, stdout may use system code page (cp932 on Japanese Windows), causing qgb's UTF-8 decode to produce U+FFFD characters. See body.md sec 6.5 + sec 12.5.5 PowerShell checklist."
    }
    return $findings
}

function Check-RuntimeAvailable {
    param($Contract)
    $findings = @()
    $runtime = $Contract.runtime
    if (-not $runtime) { return $findings }
    $resolved = Find-RuntimeExecutable -Runtime $runtime
    if (-not $resolved) {
        $findings += "C5: runtime '$runtime' executable not found on PATH. Either install the runtime, or change contract.runtime to one available in the target environment. (This check runs in the skill's local env; the user environment may differ -- verify with the user.)"
    }
    return $findings
}

function Check-EvidenceMojibake {
    param([string]$EvidencePath)
    $findings = @()
    if (-not $EvidencePath) { return $findings }
    if (-not (Test-Path -LiteralPath $EvidencePath)) {
        $findings += "C6: evidence/stage log '$EvidencePath' not found. Run ``python -m qgb check`` first, then re-run this lint with -Evidence <path-to-stage-log>."
        return $findings
    }
    $text = Read-TextStrict -Path $EvidencePath
    $count = ($text.ToCharArray() | Where-Object { $_ -eq $ReplacementChar }).Count
    if ($count -gt 0) {
        $findings += "C6: stage log '$EvidencePath' contains $count U+FFFD (replacement character) occurrence(s). This indicates command stdout/stderr was not valid UTF-8 (likely cp932 or another encoding). Fix script's output encoding (e.g. set [Console]::OutputEncoding = UTF8 for PowerShell, PYTHONUTF8=1 for Python). See body.md sec 6.5 kappa mojibake sentinel."
    }
    return $findings
}

# --- main ---

if (-not (Test-Path -LiteralPath $Contract)) {
    [Console]::Error.WriteLine("ERROR: contract not found: $Contract")
    exit $ExitUsage
}

try {
    $contractText = Read-TextStrict -Path $Contract
    $contractObj = $contractText | ConvertFrom-Json -ErrorAction Stop
} catch {
    [Console]::Error.WriteLine("ERROR: contract is not valid JSON: $_")
    exit $ExitUsage
}

if ($contractObj.verification_type -ne 'command') {
    [Console]::Error.WriteLine("INFO: contract.verification_type is not 'command', skipping command authoring lint.")
    exit 0
}

$allFindings = @()
$allFindings += Check-ExtensionRuntimeMatch -Contract $contractObj -ScriptPath $Script
$allFindings += Check-PowerShellBom         -Contract $contractObj -ScriptPath $Script
$allFindings += Check-PowerShellArgv        -Contract $contractObj
$allFindings += Check-PowerShellStdoutInit  -Contract $contractObj -ScriptPath $Script
$allFindings += Check-RuntimeAvailable      -Contract $contractObj
$allFindings += Check-EvidenceMojibake      -EvidencePath $Evidence

if ($allFindings.Count -eq 0) {
    Write-Output "OK: all checks passed."
    exit 0
}

[Console]::Error.WriteLine("FAIL: $($allFindings.Count) finding(s):")
for ($i = 0; $i -lt $allFindings.Count; $i++) {
    [Console]::Error.WriteLine("  [$($i+1)] $($allFindings[$i])")
}
exit $ExitFix
