# Minimal greeting script for lint_command_contract fixtures.
# Pure ASCII. PS5/7 compatible. Exit 0 on success.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output 'OK_GREETER_RAN'
exit 0
