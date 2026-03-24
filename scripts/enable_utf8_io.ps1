# Enforce UTF-8 text IO behavior for this PowerShell session.
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/enable_utf8_io.ps1

$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$OutputEncoding = $utf8NoBom

$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Add-Content:Encoding'] = 'utf8'
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Get-Content:Encoding'] = 'utf8'

Write-Output 'UTF8 IO guard enabled for current PowerShell session.'
