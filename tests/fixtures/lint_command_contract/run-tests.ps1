# PS5.1 real-execution fixture runner for skills/source/lint/check-command-contract.
#
# Runs each fixture contract through:
#   1. BOTH lint implementations (Python + PowerShell sibling), asserting
#      each against the shared expectations AND that their exit codes agree
#      (cross-implementation parity).
#   2. The actual PowerShell 5.1 invocation specified by contract.command,
#      observing real stdout and exit code.
# Compares (1) lint judgement and (2) real-execution behaviour against the
# expected outcome encoded in this script. Reports a per-fixture pass/fail
# table and exits 1 if any fixture diverges from expectation.
#
# Run from repo root:
#   powershell -ExecutionPolicy Bypass -NoProfile -File tests/fixtures/lint_command_contract/run-tests.ps1
#
# Pure ASCII source. PS5/7 compatible. UTF-8 stdout.

# NOTE: $ErrorActionPreference must be 'Continue', not 'Stop'.
# PowerShell 5 wraps every stderr line from a native command (python.exe,
# powershell.exe, ...) as an ErrorRecord. With 'Stop', the first stderr
# line aborts the script; with 'Continue', stderr is merged into the
# capture stream as intended.
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Resolve paths relative to this script's location.
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptDir '..\..\..')).Path
$LintScript   = Join-Path $RepoRoot 'skills\source\lint\check-command-contract.py'
$LintScriptPs = Join-Path $RepoRoot 'skills\source\lint\check-command-contract.ps1'
$ContractsDir = Join-Path $ScriptDir 'contracts'

# Expectations table for each fixture.
# Fields:
#   contract           contract.json basename
#   lintExpectedExit   expected lint exit code (0 or 1)
#   lintMustContain    substrings that must appear in lint stderr/stdout
#   lintMustNotContain substrings that must NOT appear
#   realExpectedExit   expected exit code from real PS5.1 run (or $null to skip)
#   realMustContain    substrings that must appear in real-run stdout (or @())
#   realMustNotContain substrings that must NOT appear in real-run stdout
#   notes              human-readable description of the test intent
$Expectations = @(
    @{
        contract           = 'A1-standard-5-options.json'
        lintExpectedExit   = 0
        lintMustContain    = @('OK')
        lintMustNotContain = @('FAIL', 'C3:', 'C2:')
        realExpectedExit   = 0
        realMustContain    = @('OK_GREETER_RAN')
        realMustNotContain = @()
        notes              = 'Standard PS5.1 invocation (5 host options) -- lint OK, real OK'
    },
    @{
        contract           = 'A2-encoded-arguments.json'
        lintExpectedExit   = 0
        lintMustContain    = @('OK')
        lintMustNotContain = @('FAIL', 'C3:', 'not a recognized')
        realExpectedExit   = 0
        realMustContain    = @('OK_GREETER_RAN')
        realMustNotContain = @()
        # Note: original A2 used -EncodedArguments which requires CliXml-encoded
        # base64 (not arbitrary base64). Replaced with -WindowStyle and
        # -InputFormat to exercise other PS5 allowlist entries safely.
        notes              = 'PS5 -WindowStyle Hidden + -InputFormat Text allowlist hits -- lint OK, real OK'
    },
    @{
        contract           = 'A3-abbrev-options.json'
        lintExpectedExit   = 0
        lintMustContain    = @('OK')
        lintMustNotContain = @('FAIL', 'C3:', 'not a recognized')
        realExpectedExit   = 0
        realMustContain    = @('OK_GREETER_RAN')
        realMustNotContain = @()
        notes              = 'Abbreviations -nol/-nop/-noni/-ex -- lint OK, real OK'
    },
    @{
        contract           = 'A4-jp-bom-script.json'
        lintExpectedExit   = 0
        lintMustContain    = @('OK')
        lintMustNotContain = @('FAIL', 'C2:')
        realExpectedExit   = 0
        # Script writes a JP message; the substring we check is the ASCII suffix
        # so encoding round-trip survives whatever console codepage is active.
        realMustContain    = @('fixture')
        realMustNotContain = @('ParserError')
        notes              = 'BOM-equipped JP .ps1 -- lint OK (BOM exempts C2), real OK'
    },
    @{
        contract           = 'B1-c-and-file-conflict.json'
        lintExpectedExit   = 1
        lintMustContain    = @('FAIL', 'C3:', 'mutually exclusive')
        lintMustNotContain = @()
        # Real PS5.1 runs the -c body and ignores -File / its arg as string args:
        realExpectedExit   = 0
        realMustContain    = @('COMMAND_RAN_INSTEAD')
        realMustNotContain = @('OK_GREETER_RAN')
        notes              = '-c + -File silent failure -- lint REJECTS, real exits 0 with wrong stdout'
    },
    @{
        contract           = 'B2-host-option-after-file.json'
        lintExpectedExit   = 1
        lintMustContain    = @('FAIL', 'C3:', 'AFTER')
        lintMustNotContain = @()
        # Real PS5.1: -File runs the script; the trailing tokens become script args.
        # The script does not declare any param() so trailing args are silently dropped.
        # Exit 0 from a successful greeter run is the expected real behaviour.
        realExpectedExit   = 0
        realMustContain    = @('OK_GREETER_RAN')
        realMustNotContain = @()
        notes              = 'Host options AFTER -File -- lint REJECTS, real silently treats them as script args'
    },
    @{
        contract           = 'B3-jp-without-bom-script.json'
        lintExpectedExit   = 1
        lintMustContain    = @('FAIL', 'C2:', 'UTF-8 BOM')
        lintMustNotContain = @()
        # Real PS5.1: parse error on cp932 misinterpretation, non-zero exit.
        # We assert non-zero exit + the script body's own success token
        # 'BOM_LESS_RAN_OK' (a string the script tries to print) must NOT
        # appear, indicating the script never executed past the JP comment.
        realExpectedExit   = -1
        realExpectedExitMeans = 'non-zero (parse error)'
        realMustContain    = @()
        realMustNotContain = @('BOM_LESS_RAN_OK')
        notes              = 'BOM-less JP .ps1 -- lint REJECTS (C2), real parse-error exit non-zero'
    }
)

function Invoke-Lint {
    param([string]$ContractPath, [string]$WorkingDir)
    Push-Location $WorkingDir
    try {
        # Lint uses cwd to resolve relative -File paths in contract.command.
        # We run with cwd = fixture root so the -File path
        # "scripts/ok-greeter.ps1" resolves to the bundled script.
        #
        # Note: write stderr to a temp file rather than merging via 2>&1,
        # because PS5 wraps every native-command stderr line as an
        # ErrorRecord which Out-String renders with an extra "python.exe :"
        # prefix and PowerShell-side stack trace. The temp-file route keeps
        # stderr verbatim.
        $tmpErr = [System.IO.Path]::GetTempFileName()
        try {
            $stdout = & python $LintScript $ContractPath 2>$tmpErr | Out-String
            $stderr = [System.IO.File]::ReadAllText($tmpErr)
            return @{
                ExitCode = $LASTEXITCODE
                Output   = $stdout + $stderr
            }
        } finally {
            Remove-Item -LiteralPath $tmpErr -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Pop-Location
    }
}

function Invoke-LintPs {
    param([string]$ContractPath, [string]$WorkingDir)
    Push-Location $WorkingDir
    try {
        # Run the PowerShell sibling lint with the same temp-file stderr
        # separation pattern used by Invoke-Lint to avoid PS5 ErrorRecord
        # wrapping of native-command stderr lines.
        $tmpErr = [System.IO.Path]::GetTempFileName()
        try {
            $stdout = & powershell.exe -ExecutionPolicy Bypass -NoProfile `
                -File $LintScriptPs -Contract $ContractPath 2>$tmpErr | Out-String
            $stderr = [System.IO.File]::ReadAllText($tmpErr)
            return @{
                ExitCode = $LASTEXITCODE
                Output   = $stdout + $stderr
            }
        } finally {
            Remove-Item -LiteralPath $tmpErr -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Pop-Location
    }
}

function Invoke-RealRun {
    param([string[]]$Command, [string]$WorkingDir)
    Push-Location $WorkingDir
    try {
        # Build splatting args safely: PS5 chokes on $Command[1..-1] when
        # the array has length <= 1. Use an explicit array slice.
        $exe = $Command[0]
        $argList = @()
        if ($Command.Length -gt 1) {
            for ($i = 1; $i -lt $Command.Length; $i++) {
                $argList += $Command[$i]
            }
        }
        # Split stderr to temp file to avoid PS5's ErrorRecord wrapping.
        # We return stdout and stderr separately so the caller can apply
        # different match rules to each (e.g. realMustContain on stdout,
        # error sentinels on stderr). Mixing them caused false positives
        # when error messages echoed script tokens (see B3 sentinel).
        $tmpErr = [System.IO.Path]::GetTempFileName()
        try {
            $stdout = & $exe @argList 2>$tmpErr | Out-String
            $stderr = [System.IO.File]::ReadAllText($tmpErr)
            return @{
                ExitCode = $LASTEXITCODE
                Stdout   = $stdout
                Stderr   = $stderr
                Output   = $stdout  # default match target
            }
        } finally {
            Remove-Item -LiteralPath $tmpErr -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Pop-Location
    }
}

function Test-Contains {
    param([string]$Output, [string[]]$Required, [string[]]$Forbidden)
    $missing = @()
    foreach ($req in $Required) {
        if ($Output -notmatch [regex]::Escape($req)) {
            $missing += $req
        }
    }
    $unwanted = @()
    foreach ($forb in $Forbidden) {
        if ($Output -match [regex]::Escape($forb)) {
            $unwanted += $forb
        }
    }
    return @{
        Missing  = $missing
        Unwanted = $unwanted
    }
}

# --- main ---

Write-Output ('=' * 80)
Write-Output "PS5.1 lint+real-execution fixture runner"
Write-Output "Lint (py): $LintScript"
Write-Output "Lint (ps): $LintScriptPs"
Write-Output "Contracts: $ContractsDir"
Write-Output ('=' * 80)

$results = @()

foreach ($exp in $Expectations) {
    $contractPath = Join-Path $ContractsDir $exp.contract
    $name = $exp.contract

    Write-Output ''
    Write-Output "[$name] $($exp.notes)"

    # 1a) Lint -- Python implementation (run with cwd = fixture root so
    #     contract.command's relative -File path resolves to the bundled script)
    $lint = Invoke-Lint -ContractPath $contractPath -WorkingDir $ScriptDir
    $lintExitOk = ($lint.ExitCode -eq $exp.lintExpectedExit)
    $lintCheck = Test-Contains -Output $lint.Output -Required $exp.lintMustContain -Forbidden $exp.lintMustNotContain
    $lintPass = $lintExitOk -and ($lintCheck.Missing.Count -eq 0) -and ($lintCheck.Unwanted.Count -eq 0)
    $lintStatus = if ($lintPass) { 'PASS' } else { 'FAIL' }
    Write-Output "  lint-py: exit=$($lint.ExitCode) expected=$($exp.lintExpectedExit)  $lintStatus"
    if (-not $lintPass) {
        if (-not $lintExitOk) { Write-Output "    exit mismatch" }
        if ($lintCheck.Missing.Count -gt 0)  { Write-Output "    missing: $($lintCheck.Missing -join ', ')" }
        if ($lintCheck.Unwanted.Count -gt 0) { Write-Output "    unwanted: $($lintCheck.Unwanted -join ', ')" }
    }

    # 1b) Lint -- PowerShell implementation (same cwd convention as 1a)
    $lintPs = Invoke-LintPs -ContractPath $contractPath -WorkingDir $ScriptDir
    $lintPsExitOk = ($lintPs.ExitCode -eq $exp.lintExpectedExit)
    $lintPsCheck = Test-Contains -Output $lintPs.Output -Required $exp.lintMustContain -Forbidden $exp.lintMustNotContain
    $lintPsPass = $lintPsExitOk -and ($lintPsCheck.Missing.Count -eq 0) -and ($lintPsCheck.Unwanted.Count -eq 0)
    $lintPsStatus = if ($lintPsPass) { 'PASS' } else { 'FAIL' }
    Write-Output "  lint-ps: exit=$($lintPs.ExitCode) expected=$($exp.lintExpectedExit)  $lintPsStatus"
    if (-not $lintPsPass) {
        if (-not $lintPsExitOk) { Write-Output "    exit mismatch" }
        if ($lintPsCheck.Missing.Count -gt 0)  { Write-Output "    missing: $($lintPsCheck.Missing -join ', ')" }
        if ($lintPsCheck.Unwanted.Count -gt 0) { Write-Output "    unwanted: $($lintPsCheck.Unwanted -join ', ')" }
        $psHead = ($lintPs.Output -split "`n" | Select-Object -First 5) -join "`n      "
        Write-Output "    lint-ps output (first 5 lines):"
        Write-Output "      $psHead"
    }

    # Cross-implementation assertion: Python and PowerShell exit codes must agree.
    $parityPass = $true
    if ($lint.ExitCode -ne $lintPs.ExitCode) {
        $parityPass = $false
        Write-Output "  PARITY FAIL: py exit=$($lint.ExitCode) != ps exit=$($lintPs.ExitCode)"
    }

    # 2) Real PS5.1 run (only if realExpectedExit is set)
    $realStatus = 'SKIP'
    $realPass = $true
    if ($null -ne $exp.realExpectedExit) {
        # Always read command from contract.json (single source of truth).
        $contractObj = Get-Content $contractPath -Raw | ConvertFrom-Json
        $real = Invoke-RealRun -Command $contractObj.command -WorkingDir $ScriptDir
        # exit check
        if ($exp.realExpectedExit -eq -1) {
            $realExitOk = ($real.ExitCode -ne 0)
        } else {
            $realExitOk = ($real.ExitCode -eq $exp.realExpectedExit)
        }
        $realCheck = Test-Contains -Output $real.Output -Required $exp.realMustContain -Forbidden $exp.realMustNotContain
        $realPass = $realExitOk -and ($realCheck.Missing.Count -eq 0) -and ($realCheck.Unwanted.Count -eq 0)
        $realStatus = if ($realPass) { 'PASS' } else { 'FAIL' }
        $expDisp = if ($exp.realExpectedExitMeans) { $exp.realExpectedExitMeans } else { $exp.realExpectedExit }
        Write-Output "  real:  exit=$($real.ExitCode) expected=$expDisp  $realStatus"
        if (-not $realPass) {
            if (-not $realExitOk) { Write-Output "    exit mismatch" }
            if ($realCheck.Missing.Count -gt 0)  { Write-Output "    missing: $($realCheck.Missing -join ', ')" }
            if ($realCheck.Unwanted.Count -gt 0) { Write-Output "    unwanted: $($realCheck.Unwanted -join ', ')" }
            $head = ($real.Output -split "`n" | Select-Object -First 5) -join "`n      "
            Write-Output "    real stdout (first 5 lines):"
            Write-Output "      $head"
        }
    }

    $results += @{
        Name       = $name
        LintPass   = $lintPass
        LintPsPass = $lintPsPass -and $parityPass
        RealPass   = $realPass
        LintStatus   = $lintStatus
        LintPsStatus = if ($lintPsPass -and $parityPass) { 'PASS' } else { 'FAIL' }
        RealStatus   = $realStatus
    }
}

# Summary
Write-Output ''
Write-Output ('=' * 80)
Write-Output 'Summary'
Write-Output ('=' * 80)
$totalPass = 0
$totalFail = 0
foreach ($r in $results) {
    $line = "  {0,-40}  lint-py={1,-4}  lint-ps={2,-4}  real={3,-4}" -f $r.Name, $r.LintStatus, $r.LintPsStatus, $r.RealStatus
    Write-Output $line
    if ($r.LintPass -and $r.LintPsPass -and $r.RealPass) { $totalPass++ } else { $totalFail++ }
}
Write-Output ''
$totalJudgments = $results.Count * 3
Write-Output "Total fixtures: $($results.Count) passed / $totalFail failed (of $($results.Count) fixtures)"
Write-Output "Total judgments: lint-py + lint-ps + real = $totalJudgments expected, all PASS"

if ($totalFail -gt 0) {
    exit 1
}
exit 0
