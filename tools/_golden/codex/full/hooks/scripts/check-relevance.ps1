# qgb skill UserPromptSubmit hook for Codex CLI (Windows native, PowerShell).
#
# Invoked as: powershell -ExecutionPolicy Bypass -NoProfile -File <this script>
# - stdin: Codex CLI UserPromptSubmit JSON envelope
# - stdout (no match): empty, exit 0
# - stdout (match): plain text nudge (Codex injects stdout as additional
#   context for the matched prompt)
#
# Why this script exists at all:
#   Codex CLI's UserPromptSubmit hook does NOT honour the matcher field at the
#   hook config level (the matcher is silently ignored for this event). To get
#   "only nudge when the prompt looks like a qgb request" we must regex the
#   prompt body ourselves inside the hook command. This script does exactly
#   that and nothing else (no filesystem writes, no network, no env mutation).
#
# Conservative pattern: the literal "qgb", REQ-XXX-NNN ids, gate keywords, and
# the JP trigger phrases that show up in the skill's body.md trigger table.
# JP keywords are built from Unicode escapes so this script is pure ASCII and
# round-trips through PowerShell 5 / 7 regardless of the saved file encoding
# (no BOM required). Tighten for noisier projects by editing $Pattern below.

$ErrorActionPreference = 'Stop'

# Force UTF-8 on stdout so the nudge round-trips cleanly through Codex's
# hook reader regardless of the system code page.
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# JP trigger phrases as Unicode-escaped strings (pure ASCII source, identical
# match behaviour vs literal JP). Keep in sync with skills/source/body.md
# trigger table.
#   keigaku-dankai = "Keiyaku Dankai" (contract stage)  U+5951 U+7D04 U+6BB5 U+968E
#   hinshitsu-gate = "Hinshitsu Ge-to" (quality gate)   U+54C1 U+8CEA U+30B2 U+30FC U+30C8
$JpKeiyakuDankai = ([char]0x5951 + [char]0x7d04 + [char]0x6bb5 + [char]0x968e)
$JpHinshitsuGate = ([char]0x54c1 + [char]0x8ceA + [char]0x30b2 + [char]0x30fc + [char]0x30c8)
$Pattern = "qgb|REQ-[A-Z]+-\d+|gate\.json|\bALLOW\b|\bDENY\b|NOT_READY|$JpKeiyakuDankai|$JpHinshitsuGate"

$Nudge = 'qgb skill may be relevant for this prompt. Consider loading the qgb skill (~/.agents/skills/qgb/ or .agents/skills/qgb/) if it is not yet active. The skill validates whether the request actually matches qgb scope before acting.'

# Read all of stdin as a single string. If stdin is empty (dry-run without
# input), silently exit.
$raw = [Console]::In.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) {
    exit 0
}

# Parse the envelope. If it is not valid JSON, do nothing rather than crash --
# the hook must never block prompt submission.
try {
    $obj = $raw | ConvertFrom-Json -ErrorAction Stop
} catch {
    exit 0
}

# The Codex CLI UserPromptSubmit envelope has the user-visible text in
# .prompt (same field name as Claude Code -- they share the Agent Skills
# hook envelope shape). Be defensive: if the field is absent, treat as
# non-match.
$prompt = $obj.prompt
if ([string]::IsNullOrWhiteSpace($prompt)) {
    exit 0
}

if ($prompt -notmatch $Pattern) {
    exit 0
}

# Emit the nudge as plain text. Codex injects stdout as additional context
# for the matched prompt.
[Console]::Out.WriteLine($Nudge)
exit 0
