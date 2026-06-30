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
# Behaviour notes (K=2 r1 fix 反映):
#   - -Script omitted: derive from contract.command for PowerShell runtimes
#     ("-File" -> next arg). If derivation fails for a PowerShell runtime,
#     C1/C2/C4 emit hard findings (not silent skip).
#   - C4 requires [Console]::OutputEncoding (PowerShell self stdout).
#     $OutputEncoding alone is recommended but does NOT satisfy C4.
#   - C5 (runtime PATH) is advisory only (host may differ from user env).
#   - C3 verifies invoker basename exactly, -File presence, and consistency
#     with -Script if provided.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -NoProfile -File check-command-contract.ps1 `
#     -Contract <path> [-Script <path>] [-Evidence <path>]
#
# Exit codes:
#   0: no fix-required findings (advisories may have been printed)
#   1: one or more fix-required findings
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

# Allowed invoker basenames per PowerShell runtime (case-insensitive match).
$PowerShellInvokerBasenames = @{
    'powershell-5' = @('powershell', 'powershell.exe')
    'powershell-7' = @('pwsh', 'pwsh.exe')
}

# PowerShell stdout init regex patterns.
# Required (C4): [Console]::OutputEncoding = ... UTF8
$PsRequiredStdoutPattern = '\[Console\]::OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8'
# Recommended (advisory only): $OutputEncoding = ... UTF8
$PsRecommendedStdoutPattern = '\$OutputEncoding\s*=\s*\[System\.Text\.Encoding\]::UTF8'

# U+FFFD replacement character literal (built from codepoint to keep this
# script pure ASCII and BOM-independent).
$ReplacementChar = [char]0xFFFD

function Read-TextStrict {
    param([string]$Path)
    return [System.IO.File]::ReadAllText($Path, [System.Text.UTF8Encoding]::new($true))
}

function Normalize-PathForCompare {
    param([string]$PathStr, [string]$BaseDir)
    # Cross-style normalization: convert backslashes to forward slashes,
    # resolve relative to BaseDir if not absolute, lowercase for
    # case-insensitive comparison (Windows convention).
    if ([string]::IsNullOrWhiteSpace($PathStr)) { return "" }
    if ([System.IO.Path]::IsPathRooted($PathStr)) {
        return ([System.IO.Path]::GetFullPath($PathStr)).Replace('\', '/').ToLower()
    }
    $combined = Join-Path $BaseDir $PathStr
    return ([System.IO.Path]::GetFullPath($combined)).Replace('\', '/').ToLower()
}

function Test-Utf8Bom {
    param([string]$Path)
    $bytes = [System.IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 3) { return $false }
    return $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
}

function Test-PureAscii {
    param([string]$Text)
    foreach ($ch in $Text.ToCharArray()) {
        if ([int]$ch -gt 127) { return $false }
    }
    return $true
}

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

function Get-ScriptPathFromCommand {
    param($Contract)
    if (-not $Contract.command -or -not ($Contract.command -is [System.Array])) { return $null }
    $runtime = $Contract.runtime
    if (-not $PowerShellInvokerBasenames.ContainsKey($runtime)) { return $null }
    for ($i = 0; $i -lt $Contract.command.Length - 1; $i++) {
        # case-insensitive -File matching to parity with PowerShell parser.
        if (([string]$Contract.command[$i]).ToLower() -eq '-file') {
            return [string]$Contract.command[$i + 1]
        }
    }
    return $null
}

function Resolve-ScriptPath {
    param($Contract, [string]$ScriptArg, [string]$ContractPath)
    if (-not [string]::IsNullOrWhiteSpace($ScriptArg)) {
        return $ScriptArg
    }
    $derived = Get-ScriptPathFromCommand -Contract $Contract
    if (-not $derived) { return $null }
    if ([System.IO.Path]::IsPathRooted($derived)) { return $derived }
    # Try contract dir, then cwd.
    $contractDir = [System.IO.Path]::GetDirectoryName([System.IO.Path]::GetFullPath($ContractPath))
    $tryDirs = @($contractDir, (Get-Location).Path)
    foreach ($dir in $tryDirs) {
        $candidate = Join-Path $dir $derived
        if (Test-Path -LiteralPath $candidate) {
            return [System.IO.Path]::GetFullPath($candidate)
        }
    }
    return $derived
}

function Check-ExtensionRuntimeMatch {
    param($Contract, [string]$ScriptPath)
    $findings = @()
    $runtime = $Contract.runtime
    if (-not $runtime) {
        $findings += "C1: contract.runtime is not declared. Add a runtime field (e.g. 'powershell-5' / 'bash' / 'python' / 'node') to enable capability-based dispatch (body.md sec 12.5.5)."
        return $findings
    }
    if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
        if ($PowerShellInvokerBasenames.ContainsKey($runtime)) {
            $findings += "C1: PowerShell script path could not be resolved. Provide -Script or ensure contract.command uses an explicit '-File <script>' form (body.md sec 6.5 PowerShell 5 rules)."
        }
        return $findings
    }
    $expected = $RuntimeExtensions[$runtime]
    if ($expected -and -not ($expected -contains [System.IO.Path]::GetExtension($ScriptPath).ToLower())) {
        $findings += "C1: script extension '$([System.IO.Path]::GetExtension($ScriptPath))' does not match runtime '$runtime' (expected one of $($expected -join ', ')). Match the script extension to the confirmed runtime or change contract.runtime (body.md sec 12.5.5)."
    }
    return $findings
}

function Check-PowerShellBom {
    param($Contract, [string]$ScriptPath)
    $findings = @()
    if ($Contract.runtime -ne 'powershell-5') { return $findings }
    if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
        $findings += "C2: cannot check BOM because script path is unresolved (PowerShell 5 runtime requires a .ps1 path via -Script or contract.command's -File argument)."
        return $findings
    }
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
    param($Contract, [string]$ScriptPath, [string]$ContractPath, [bool]$ScriptExplicitlyProvided = $false)
    $findings = @()
    $runtime = $Contract.runtime
    if (-not $PowerShellInvokerBasenames.ContainsKey($runtime)) { return $findings }
    $command = $Contract.command
    if (-not ($command -is [System.Array]) -or $command.Count -eq 0) {
        $findings += "C3: contract.command is not a non-empty list. For verification_type=command, contract.command must be the argv as a list (body.md sec 6.5 step 4)."
        return $findings
    }

    # Normalize argv to strings + lower-cased copy for case-insensitive
    # option matching (PowerShell parser is case-insensitive on option
    # names and on Bypass).
    $commandStr = @()
    $commandLower = @()
    foreach ($a in $command) {
        $s = [string]$a
        $commandStr += $s
        $commandLower += $s.ToLower()
    }

    # First arg: invoker basename, case-insensitive.
    $allowedInvokers = $PowerShellInvokerBasenames[$runtime]
    $firstBasename = ([System.IO.Path]::GetFileName($commandStr[0])).ToLower()
    if (-not ($allowedInvokers -contains $firstBasename)) {
        $findings += "C3: contract.command[0] basename = '$firstBasename' is not a recognized invoker for runtime '$runtime' (expected one of $($allowedInvokers -join ', ')). PowerShell runtimes require an explicit invoker as the first argv element. See body.md sec 6.5 PowerShell 5 rules."
    }

    # Required flags. Each may be satisfied by its canonical name OR any
    # documented abbreviation (PowerShell parser accepts either).
    $requiredFlagSynonyms = @(
        @('-nologo', '-nol'),
        @('-noprofile', '-nop'),
        @('-noninteractive', '-noni')
    )
    if ($runtime -eq 'powershell-5') {
        $requiredFlagSynonyms += , @('-executionpolicy', '-ex', '-ep')
        $requiredFlagSynonyms += , @('bypass')
    }
    $missing = @()
    foreach ($group in $requiredFlagSynonyms) {
        $satisfied = $false
        foreach ($synonym in $group) {
            if ($commandLower -contains $synonym) {
                $satisfied = $true
                break
            }
        }
        if (-not $satisfied) {
            $missing += $group[0]
        }
    }
    if ($missing.Count -gt 0) {
        $findings += "C3: PowerShell argv is missing required flags ($($missing -join ', ')) (case-insensitive; abbreviations also accepted). These flags ensure deterministic execution (no profile load, no interactive prompt, no policy ambiguity). See body.md sec 6.5."
    }

    # Locate -File (case-insensitive, first occurrence).
    $fileIdx = -1
    $fileCount = 0
    for ($i = 0; $i -lt $commandLower.Count; $i++) {
        if ($commandLower[$i] -eq '-file') {
            if ($fileIdx -lt 0) { $fileIdx = $i }
            $fileCount++
        }
    }
    if ($fileIdx -lt 0) {
        $findings += "C3: PowerShell argv is missing '-File <script.ps1>'. .ps1 must be invoked via -File explicitly (not via positional argument or shell association). See body.md sec 6.5."
        return $findings
    }
    if ($fileCount -gt 1) {
        $findings += "C3: '-File' appears $fileCount times in contract.command; exactly one occurrence is required. PowerShell would use the first, but the duplicate is misleading. See body.md sec 6.5."
    }

    # Strict host-option grammar for argv positions BEFORE -File.
    # Runtime-separated allowlist of canonical names + accepted abbreviations.
    # Any '-' or '/' prefixed token before -File that is not on the runtime's
    # allowlist is rejected. Execution-mode options (-Command / -EncodedCommand
    # and PS7-only -CommandWithArgs, plus help-mode -?, -Help, /?) are
    # intentionally placed in $execModeOptions: PowerShell would run a body
    # other than the target script and exit 0, masking the failure.
    #
    # See:
    #   PS5: https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_powershell_exe
    #   PS7: https://learn.microsoft.com/powershell/module/microsoft.powershell.core/about/about_pwsh
    $allowedHostOptionsByRuntime = @{
        'powershell-5' = @(
            '-nologo', '-nol',
            '-noprofile', '-nop',
            '-noninteractive', '-noni',
            '-noexit', '-noe',
            '-executionpolicy', '-ex', '-ep',
            '-windowstyle', '-w',
            '-version', '-v',
            '-mta',
            '-sta',
            '-psconsolefile', '-psc',
            '-inputformat', '-inp', '-if',
            '-outputformat', '-out', '-of',
            '-configurationname', '-config',
            '-encodedarguments', '-encodedargs'
        )
        'powershell-7' = @(
            '-nologo', '-nol',
            '-noprofile', '-nop',
            '-noninteractive', '-noni',
            '-noexit', '-noe',
            '-noprofileloadtime', '-noprofileloadtim',
            '-executionpolicy', '-ex', '-ep',
            '-windowstyle', '-w',
            '-version', '-v',
            '-mta',
            '-sta',
            '-inputformat', '-inp', '-if',
            '-outputformat', '-o', '-of',
            '-interactive', '-i',
            '-login', '-l',
            '-configurationname', '-config',
            '-configurationfile',
            '-custompipename',
            '-settingsfile', '-settings',
            '-sshservermode', '-sshs',
            '-workingdirectory', '-wd', '-wo'
        )
    }
    $execModeOptionsByRuntime = @{
        'powershell-5' = @(
            '-command', '-c',
            '-encodedcommand', '-ec',
            '-help', '-?', '/?'
        )
        'powershell-7' = @(
            '-command', '-c',
            '-encodedcommand', '-e', '-ec',
            '-commandwithargs', '-cwa',
            '-help', '-?', '/?'
        )
    }
    $allowedHostOptionsPreFile = $allowedHostOptionsByRuntime[$runtime]
    $execModeOptions = $execModeOptionsByRuntime[$runtime]
    if (-not $allowedHostOptionsPreFile) { $allowedHostOptionsPreFile = @() }
    if (-not $execModeOptions) { $execModeOptions = @() }

    # Walk argv positions [1, fileIdx) and validate each '-' / '/' prefixed token.
    for ($i = 1; $i -lt $fileIdx; $i++) {
        $tokenLower = $commandLower[$i]
        $tokenOrig = $commandStr[$i]
        if ($tokenLower.StartsWith('-') -or $tokenLower.StartsWith('/')) {
            if ($execModeOptions -contains $tokenLower) {
                $findings += "C3: contract.command contains '$tokenOrig' at position $i, which is a PowerShell execution-mode option (-Command / -c / -EncodedCommand / -ec). It is mutually exclusive with -File: PowerShell would run the command body and treat -File + path as string arguments, never executing the target script (exit 0 with the wrong stdout). Choose exactly one execution mode. For verification_type=command contracts that invoke .ps1, use -File only. See body.md sec 6.5."
            } elseif (-not ($allowedHostOptionsPreFile -contains $tokenLower)) {
                $allowedList = ($allowedHostOptionsPreFile | Sort-Object) -join ', '
                $findings += "C3: contract.command contains '$tokenOrig' at position $i (before -File), which is not a recognized PowerShell host option. PowerShell either errors on this or silently misinterprets it. Allowed host options (and their accepted abbreviations): $allowedList. See body.md sec 6.5."
            }
        }
    }

    # Structure: all host options must appear BEFORE -File.
    $hostOptionLower = @(
        '-nologo', '-noprofile', '-noninteractive', '-executionpolicy',
        '-command', '-encodedcommand', '-windowstyle', '-version',
        '-mta', '-sta', '-psconsolefile', '-inputformat', '-outputformat'
    )
    for ($i = $fileIdx + 2; $i -lt $commandLower.Count; $i++) {
        if ($hostOptionLower -contains $commandLower[$i]) {
            $findings += "C3: host option '$($commandStr[$i])' appears AFTER '-File' (position $i). Host options must precede -File; anything after -File is interpreted as script arguments. See body.md sec 6.5."
        }
    }

    # Duplicate -ExecutionPolicy check (incl. abbreviations -ex / -ep).
    $epAliases = @('-executionpolicy', '-ex', '-ep')
    $epIndices = @()
    for ($i = 0; $i -lt $commandLower.Count; $i++) {
        if ($epAliases -contains $commandLower[$i]) { $epIndices += $i }
    }
    if ($epIndices.Count -gt 1) {
        $findings += "C3: '-ExecutionPolicy' (or abbreviation -ex / -ep) appears $($epIndices.Count) times in contract.command; exactly one occurrence is required (the duplicate would silently apply a non-deterministic value). See body.md sec 6.5."
    }

    # PS 5: -ExecutionPolicy must be IMMEDIATELY followed by Bypass.
    if ($runtime -eq 'powershell-5' -and $epIndices.Count -gt 0) {
        $epIdx = $epIndices[0]
        $nextArgLower = if ($epIdx + 1 -lt $commandLower.Count) { $commandLower[$epIdx + 1] } else { $null }
        if ($nextArgLower -ne 'bypass') {
            $actual = if ($epIdx + 1 -lt $commandStr.Count) { $commandStr[$epIdx + 1] } else { $null }
            $epForm = $commandStr[$epIdx]
            $findings += "C3: '$epForm' must be immediately followed by 'Bypass' (case-insensitive), but the next argv element is '$actual'. The current argv would set a different policy, defeating the deterministic-execution intent. See body.md sec 6.5."
        }
    }

    # -File path immediately follows -File.
    if ($fileIdx + 1 -ge $commandStr.Count) {
        $findings += "C3: '-File' is the last argv element, but a script path is required immediately after. See body.md sec 6.5."
        return $findings
    }
    $fileArg = $commandStr[$fileIdx + 1]
    if ($fileArg.StartsWith('-')) {
        $findings += "C3: argv item after '-File' is '$fileArg', which looks like another flag. Expected a script path. See body.md sec 6.5."
        return $findings
    }
    # Compare -File argument with -Script we resolved (full-path normalization,
    # not basename-only). Both POSIX and Windows path styles are handled by
    # .NET's path APIs on the running host (PowerShell sibling runs on Windows
    # native, so we use ntpath-equivalent forward/backslash normalization).
    # -File and -Script can be relative paths but interpreted against
    # different base dirs at runtime (-File: user's project working dir at
    # `qgb run`; -Script: lint invocation cwd, or absolute). Use a layered
    # comparison: full-path equality when either side is absolute, basename
    # equality otherwise. Stronger same-path verification belongs in 5.b
    # dogfooding against a real fixture project.
    #
    # Only compare when -Script was EXPLICITLY provided by the user; when
    # it was derived from -File, the comparison is tautological and the
    # derived value may have been resolved against a base dir different
    # from the user's project layout, producing spurious mismatches
    # (Codex K=2 r6-post real-fixture test caught this).
    if (-not [string]::IsNullOrWhiteSpace($ScriptPath) -and $ScriptExplicitlyProvided) {
        $fileIsAbsolute = [System.IO.Path]::IsPathRooted($fileArg)
        $scriptIsAbsolute = [System.IO.Path]::IsPathRooted($ScriptPath)
        if ($fileIsAbsolute -or $scriptIsAbsolute) {
            $contractDir = (Get-Location).Path
            if (-not [string]::IsNullOrWhiteSpace($ContractPath)) {
                $resolved = [System.IO.Path]::GetFullPath($ContractPath)
                $contractDir = [System.IO.Path]::GetDirectoryName($resolved)
            }
            $fileNorm = Normalize-PathForCompare -PathStr $fileArg -BaseDir $contractDir
            $scriptNorm = Normalize-PathForCompare -PathStr $ScriptPath -BaseDir $contractDir
            if ($fileNorm -ne $scriptNorm) {
                $findings += "C3: contract.command -File argument '$fileArg' does not resolve to the same path as -Script '$ScriptPath' (normalized: '$fileNorm' vs '$scriptNorm'). The skill must invoke exactly the script under review."
            }
        } else {
            $fileBasename = [System.IO.Path]::GetFileName($fileArg)
            $scriptBasename = [System.IO.Path]::GetFileName($ScriptPath)
            if ($fileBasename -ne $scriptBasename) {
                $findings += "C3: contract.command -File argument basename '$fileBasename' does not match -Script basename '$scriptBasename'. The skill must invoke exactly the script under review (relative paths checked by basename only; for stricter check, pass absolute paths to both -File and -Script)."
            }
        }
    }
    return $findings
}

function Check-PowerShellStdoutInit {
    param($Contract, [string]$ScriptPath)
    $findings = @()
    $runtime = $Contract.runtime
    if (-not $PowerShellInvokerBasenames.ContainsKey($runtime)) { return $findings }
    if ([string]::IsNullOrWhiteSpace($ScriptPath)) {
        $findings += "C4: cannot check [Console]::OutputEncoding init because script path is unresolved (PowerShell runtime requires a .ps1 path)."
        return $findings
    }
    if ([System.IO.Path]::GetExtension($ScriptPath).ToLower() -ne '.ps1') { return $findings }
    if (-not (Test-Path -LiteralPath $ScriptPath)) { return $findings }
    $text = Read-TextStrict -Path $ScriptPath
    if (-not ($text -match $PsRequiredStdoutPattern)) {
        $findings += "C4: PowerShell script '$ScriptPath' does not set [Console]::OutputEncoding = [System.Text.Encoding]::UTF8. This is required; `$OutputEncoding alone is insufficient (it only affects child-process pipelines, not qgb's read of PowerShell's own stdout). Without [Console]::OutputEncoding, stdout may use system code page (cp932 on Japanese Windows), causing qgb's UTF-8 decode to produce U+FFFD characters. See body.md sec 6.5 + sec 12.5.5 PowerShell checklist."
    }
    return $findings
}

function Check-RuntimeAvailable {
    param($Contract)
    # Return a hashtable to avoid PowerShell's array-collapse-on-empty
    # behavior (where @(), $advisories in destructuring would collapse the
    # empty array and shift the advisories into the findings slot).
    $result = @{
        Findings = @()
        Advisories = @()
    }
    $runtime = $Contract.runtime
    if (-not $runtime) { return $result }
    $resolved = Find-RuntimeExecutable -Runtime $runtime
    if (-not $resolved) {
        $result.Advisories += "C5 (advisory): runtime '$runtime' executable not found on this host's PATH. This is the skill-agent's local environment; the target user environment may differ. Verify availability on the user's host before relying on this contract."
    }
    return $result
}

function Check-EvidenceMojibake {
    param([string]$EvidencePath)
    $findings = @()
    if ([string]::IsNullOrWhiteSpace($EvidencePath)) { return $findings }
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

function Check-OutputEncodingAdvisory {
    param($Contract, [string]$ScriptPath)
    $advisories = @()
    $runtime = $Contract.runtime
    if (-not $PowerShellInvokerBasenames.ContainsKey($runtime)) { return $advisories }
    if ([string]::IsNullOrWhiteSpace($ScriptPath)) { return $advisories }
    if (-not (Test-Path -LiteralPath $ScriptPath)) { return $advisories }
    if ([System.IO.Path]::GetExtension($ScriptPath).ToLower() -ne '.ps1') { return $advisories }
    $text = Read-TextStrict -Path $ScriptPath
    if (-not ($text -match $PsRecommendedStdoutPattern)) {
        $advisories += "advisory (PowerShell recommended): script '$ScriptPath' does not set `$OutputEncoding = [System.Text.Encoding]::UTF8. While not required by C4, it is recommended when the script pipes output to child processes that expect UTF-8."
    }
    return $advisories
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

$resolvedScript = Resolve-ScriptPath -Contract $contractObj -ScriptArg $Script -ContractPath $Contract
$scriptExplicit = -not [string]::IsNullOrWhiteSpace($Script)

$findings = @()
$advisories = @()

$findings += Check-ExtensionRuntimeMatch -Contract $contractObj -ScriptPath $resolvedScript
$findings += Check-PowerShellBom         -Contract $contractObj -ScriptPath $resolvedScript
$findings += Check-PowerShellArgv        -Contract $contractObj -ScriptPath $resolvedScript -ContractPath $Contract -ScriptExplicitlyProvided $scriptExplicit
$findings += Check-PowerShellStdoutInit  -Contract $contractObj -ScriptPath $resolvedScript
$runtimeResult = Check-RuntimeAvailable -Contract $contractObj
$findings += $runtimeResult.Findings
$advisories += $runtimeResult.Advisories
$findings += Check-EvidenceMojibake      -EvidencePath $Evidence
$advisories += Check-OutputEncodingAdvisory -Contract $contractObj -ScriptPath $resolvedScript

if ($advisories.Count -gt 0) {
    [Console]::Error.WriteLine("NOTE: $($advisories.Count) advisory note(s):")
    for ($i = 0; $i -lt $advisories.Count; $i++) {
        [Console]::Error.WriteLine("  ($($i+1)) $($advisories[$i])")
    }
}

if ($findings.Count -eq 0) {
    Write-Output "OK: all fix-required checks passed."
    exit 0
}

[Console]::Error.WriteLine("FAIL: $($findings.Count) fix-required finding(s):")
for ($i = 0; $i -lt $findings.Count; $i++) {
    [Console]::Error.WriteLine("  [$($i+1)] $($findings[$i])")
}
exit $ExitFix
