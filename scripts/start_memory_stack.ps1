param(
    [switch]$Detach = $true
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$args = @("compose", "up")
if ($Detach) {
    $args += "-d"
}
$args += @("postgres", "redis", "neo4j", "qdrant")

Write-Host "Starting memory stack: $($args -join ' ')"
docker @args
