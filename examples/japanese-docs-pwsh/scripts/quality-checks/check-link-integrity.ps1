# check-link-integrity.ps1
#
# qgb skill example: japanese-docs-pwsh, stage S1 (link integrity).
# Phase 5 Step 5.a-2-4. Windows native PowerShell 5/7 compatible.
# Pure ASCII source (no BOM required) per body.md sec 6.5 PowerShell 5 rules.
# JP labels are constructed from Unicode escapes ([char]0x...) at runtime.
#
# Checks internal Markdown links in docs/ root:
#   - [text](./path.md) format relative links resolve to existing files
#   - [text](#anchor) inline anchor links resolve to a heading in same file
#
# Exit codes:
#   0: all links valid
#   1: one or more broken links
#
# Required env: PowerShell 5+, executed from project root (cwd = repo root).

param(
    [Parameter(Mandatory=$false)]
    [string]$DocsRoot = "docs"
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# Labels (English to keep script ASCII-safe; user-facing JP messaging is left
# to the skill or the user prompt that calls qgb).
$LabelBrokenLinks = "broken internal link(s) detected"
$LabelAllOK = "all internal links resolve"

if (-not (Test-Path -LiteralPath $DocsRoot -PathType Container)) {
    [Console]::Error.WriteLine("ERROR: docs root not found: $DocsRoot")
    exit 1
}

$broken = @()
$mdFiles = Get-ChildItem -LiteralPath $DocsRoot -Recurse -Filter '*.md' -File

foreach ($file in $mdFiles) {
    $content = [System.IO.File]::ReadAllText($file.FullName, [System.Text.UTF8Encoding]::new($false))

    # Extract [text](path) patterns, filter to internal (no scheme).
    $linkRegex = [regex]'\[([^\]]+)\]\(([^)]+)\)'
    $matches = $linkRegex.Matches($content)

    foreach ($m in $matches) {
        $linkTarget = $m.Groups[2].Value.Trim()

        # Skip external schemes (http / https / mailto / etc).
        if ($linkTarget -match '^[a-zA-Z][a-zA-Z0-9+.-]*:') { continue }

        # Skip empty / hash-only (will be checked separately as anchor).
        if ([string]::IsNullOrWhiteSpace($linkTarget)) { continue }

        # Split path and anchor.
        $pathPart = $linkTarget
        $anchorPart = ""
        if ($linkTarget.Contains('#')) {
            $hashIdx = $linkTarget.IndexOf('#')
            $pathPart = $linkTarget.Substring(0, $hashIdx)
            $anchorPart = $linkTarget.Substring($hashIdx + 1)
        }

        # Resolve path: relative to the file's directory.
        if ([string]::IsNullOrWhiteSpace($pathPart)) {
            # Inline anchor (#xxx), points to same file.
            $targetFile = $file.FullName
        } else {
            $targetFile = Join-Path $file.Directory.FullName $pathPart
            $targetFile = [System.IO.Path]::GetFullPath($targetFile)
            if (-not (Test-Path -LiteralPath $targetFile -PathType Leaf)) {
                $broken += "$($file.FullName): '$linkTarget' -> file not found"
                continue
            }
        }

        # If anchor present, check that target file has a heading matching it.
        if ($anchorPart) {
            $targetContent = [System.IO.File]::ReadAllText($targetFile, [System.Text.UTF8Encoding]::new($false))
            $headingPattern = '(?m)^#+\s+(.+?)\s*$'
            $headingMatches = [regex]::Matches($targetContent, $headingPattern)
            $found = $false
            foreach ($hm in $headingMatches) {
                $heading = $hm.Groups[1].Value
                # GitHub-style anchor: lowercase, spaces -> hyphens, strip punctuation.
                $slug = ($heading.ToLowerInvariant() -replace '\s+', '-' -replace '[^\w\-]', '')
                if ($slug -eq $anchorPart.ToLowerInvariant()) {
                    $found = $true
                    break
                }
            }
            if (-not $found) {
                $broken += "$($file.FullName): '$linkTarget' -> anchor '$anchorPart' not found in $targetFile"
            }
        }
    }
}

if ($broken.Count -gt 0) {
    [Console]::Error.WriteLine("$LabelBrokenLinks ($($broken.Count)):")
    foreach ($b in $broken) {
        [Console]::Error.WriteLine("  - $b")
    }
    exit 1
}

Write-Output $LabelAllOK
exit 0
