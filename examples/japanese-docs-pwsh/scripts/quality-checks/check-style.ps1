# check-style.ps1
#
# qgb skill example: japanese-docs-pwsh, stage S3 (style check).
# Phase 5 Step 5.a-2-4. Windows native PowerShell 5/7 compatible.
# Pure ASCII source (no BOM required) per body.md sec 6.5 PowerShell 5 rules.
#
# Checks the heading hierarchy rules for each Markdown file under docs/:
#   - exactly one H1 (# ) per file
#   - heading levels do not skip (e.g. H1 followed directly by H3 fails)
#
# Exit codes:
#   0: no style violations
#   1: one or more style violations

param(
    [Parameter(Mandatory=$false)]
    [string]$DocsRoot = "docs"
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

if (-not (Test-Path -LiteralPath $DocsRoot -PathType Container)) {
    [Console]::Error.WriteLine("ERROR: docs root not found: $DocsRoot")
    exit 1
}

$violations = @()
$mdFiles = Get-ChildItem -LiteralPath $DocsRoot -Recurse -Filter '*.md' -File

foreach ($file in $mdFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.UTF8Encoding]::new($false))
    $lines = $content -split "`n"

    $h1Count = 0
    $previousLevel = 0
    $lineNo = 0

    foreach ($line in $lines) {
        $lineNo++
        if ($line -match '^(#+)\s+(.+?)\s*$') {
            $level = $matches[1].Length
            $headingText = $matches[2]

            if ($level -eq 1) {
                $h1Count++
            }

            # Check skip: previous level + 1 should equal current level if going deeper.
            if ($previousLevel -gt 0 -and $level -gt $previousLevel + 1) {
                $violations += "$($file.FullName):${lineNo}: heading level skipped (H$previousLevel -> H$level): '$headingText'"
            }
            $previousLevel = $level
        }
    }

    if ($h1Count -eq 0) {
        $violations += "$($file.FullName): no H1 (#) heading found"
    } elseif ($h1Count -gt 1) {
        $violations += "$($file.FullName): multiple H1 (#) headings found ($h1Count); only one is allowed per file"
    }
}

if ($violations.Count -gt 0) {
    [Console]::Error.WriteLine("style violation(s) detected ($($violations.Count)):")
    foreach ($v in $violations) {
        [Console]::Error.WriteLine("  - $v")
    }
    exit 1
}

Write-Output "no style violations"
exit 0
