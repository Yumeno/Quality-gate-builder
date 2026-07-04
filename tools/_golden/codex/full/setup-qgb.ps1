# GENERATED FILE - DO NOT EDIT.
# This is a generated artifact. Edit skills/source/body.md instead.
# converter_version: 0.1.0
# build_input_digest: a9597890ff883282
param(
    [string]$FromPath = ""
)

$ErrorActionPreference = 'Stop'

# setup-qgb.ps1 -- qgb installer (venv-default).
#
# Trust boundary note: the default install path below runs
# 'pip install git+https://...@<tag>', which is clone-equivalent
# trust (arbitrary code from the repo at that tag runs during
# 'pip install').  --require-hashes is not available for VCS
# installs (NF-011); this script does not attempt to simulate it.
# Use -FromPath for an offline / local-clone install instead.

function Write-Step($msg) {
    Write-Host "[setup-qgb] $msg"
}

# Step 1: locate a Python 3 interpreter.
Write-Step "Step 1: locating Python..."
$pythonCmd = $null
try {
    & py -3 --version | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $pythonCmd = "py -3"
    }
} catch {
    $pythonCmd = $null
}
if (-not $pythonCmd) {
    try {
        & python --version | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $pythonCmd = "python"
        }
    } catch {
        $pythonCmd = $null
    }
}
if (-not $pythonCmd) {
    Write-Host "[setup-qgb] ERROR: no working Python 3 interpreter found (tried 'py -3' and 'python')."
    Write-Host "[setup-qgb] Install Python 3 and re-run this script."
    exit 1
}
Write-Step "Using interpreter: $pythonCmd"

# Step 2: create .venv if absent; leave an existing .venv untouched.
Write-Step "Step 2: checking .venv..."
if (Test-Path ".venv") {
    Write-Step ".venv already exists -- leaving it untouched."
} else {
    Write-Step "Creating .venv..."
    if ($pythonCmd -eq "py -3") {
        & py -3 -m venv .venv
    } else {
        & python -m venv .venv
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[setup-qgb] ERROR: 'python -m venv .venv' failed (exit $LASTEXITCODE)."
        exit 1
    }
}
$venvPython = ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[setup-qgb] ERROR: expected venv interpreter not found: $venvPython"
    exit 1
}

# Step 3: install qgb into .venv.
if ($FromPath -ne "") {
    Write-Step "Step 3: installing qgb from local path (editable): $FromPath"
    & $venvPython -m pip install -e $FromPath
} else {
    Write-Step "Step 3: installing qgb from git+https://github.com/Yumeno/Quality-gate-builder.git (tag skill-v0.1.2)..."
    & $venvPython -m pip install "git+https://github.com/Yumeno/Quality-gate-builder.git@skill-v0.1.2"
}
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup-qgb] ERROR: pip install failed (exit $LASTEXITCODE)."
    exit 1
}

# Step 4: verify.
Write-Step "Step 4: verifying installation..."
& $venvPython -m qgb --version
if ($LASTEXITCODE -ne 0) {
    Write-Host "[setup-qgb] ERROR: '$venvPython -m qgb --version' failed (exit $LASTEXITCODE)."
    Write-Host "[setup-qgb] qgb was not installed correctly. See the error above."
    exit 1
}

# Step 5: next steps.
Write-Host ""
Write-Host "[setup-qgb] qgb installed successfully into .venv."
Write-Host "[setup-qgb] To activate this venv in your shell:"
Write-Host "[setup-qgb]     .venv\Scripts\Activate.ps1"
Write-Host "[setup-qgb] Agent sessions do NOT auto-activate a venv: invoke qgb explicitly instead:"
Write-Host "[setup-qgb]     .venv\Scripts\python.exe -m qgb <command>"

