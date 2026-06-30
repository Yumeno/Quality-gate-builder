# BOM 付き UTF-8 で保存した PS5.1 向け .ps1 (fixture 用)。
# 日本語 string を含むが BOM があるため PS5.1 でも正常 parse される。
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$message = '日本語メッセージ:fixture 用、BOM 付きのため正常実行'
Write-Output $message
exit 0