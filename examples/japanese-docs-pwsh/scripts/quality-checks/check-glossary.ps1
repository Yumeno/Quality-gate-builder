# check-glossary.ps1
#
# qgb skill example: japanese-docs-pwsh, stage S2 (glossary check).
# Phase 5 Step 5.a-2-4. Windows native PowerShell 5/7 compatible.
# Pure ASCII source (no BOM required) per body.md sec 6.5 PowerShell 5 rules.
#
# Checks: Markdown files under docs/ do not contain any deprecated terms
# declared in glossary.json. The glossary itself is UTF-8 (BOM tolerant)
# and may contain JP terms; this script reads them as data, not as code.
#
# glossary.json format:
#   {
#     "deprecated": [
#       {"term": "<deprecated>", "use_instead": "<preferred>", "reason": "..."}
#     ]
#   }
#
# Exit codes:
#   0: no deprecated terms found
#   1: one or more deprecated terms found in docs/
#   2: glossary.json not found or invalid

param(
    [Parameter(Mandatory=$false)]
    [string]$DocsRoot = "docs",
    [Parameter(Mandatory=$false)]
    [string]$GlossaryFile = "docs/glossary.json"
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path -LiteralPath $DocsRoot -PathType Container)) {
    [Console]::Error.WriteLine("ERROR: docs root not found: $DocsRoot")
    exit 2
}
if (-not (Test-Path -LiteralPath $GlossaryFile -PathType Leaf)) {
    [Console]::Error.WriteLine("ERROR: glossary file not found: $GlossaryFile")
    exit 2
}

try {
    $glossaryText = [System.IO.File]::ReadAllText($GlossaryFile, [System.Text.UTF8Encoding]::new($true))
    $glossary = $glossaryText | ConvertFrom-Json -ErrorAction Stop
} catch {
    [Console]::Error.WriteLine("ERROR: glossary is not valid JSON: $_")
    exit 2
}

if (-not $glossary.deprecated) {
    Write-Output "no deprecated terms declared; nothing to check"
    exit 0
}

$violations = @()
$mdFiles = Get-ChildItem -LiteralPath $DocsRoot -Recurse -Filter '*.md' -File

foreach ($file in $mdFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.UTF8Encoding]::new($false))

    foreach ($entry in $glossary.deprecated) {
        $term = $entry.term
        if (-not $term) { continue }
        if ($content.Contains($term)) {
            $useInstead = $entry.use_instead
            $reason = $entry.reason
            $violations += "$($file.FullName): contains deprecated term '$term' (use instead: '$useInstead'; reason: $reason)"
        }
    }
}

if ($violations.Count -gt 0) {
    [Console]::Error.WriteLine("deprecated term(s) detected ($($violations.Count)):")
    foreach ($v in $violations) {
        [Console]::Error.WriteLine("  - $v")
    }
    exit 1
}

Write-Output "no deprecated terms found"
exit 0
