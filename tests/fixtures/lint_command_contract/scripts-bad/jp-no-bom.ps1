# PS5.1 で BOM なし日本語 .ps1 は cp932 として読まれ parse error になる例。
# Write tool は BOM なし UTF-8 で書くため、Write 直後はこの状態。
# 利用者プロジェクトで「日本語コメント / string を入れた .ps1 を保存」した結果として
# 出る典型的な失敗形を再現。
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$message = '日本語メッセージ：fixture 用、BOM なしのため PS5.1 で parse error 想定'
Write-Output $message
Write-Output 'BOM_LESS_RAN_OK'
exit 0
