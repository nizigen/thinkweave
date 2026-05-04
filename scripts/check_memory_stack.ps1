param()

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

$required = @("postgres", "redis", "neo4j", "qdrant", "falkordb")
$statusOutput = docker compose ps --format json | ConvertFrom-Json

foreach ($name in $required) {
    $service = $statusOutput | Where-Object { $_.Service -eq $name }
    if (-not $service) {
        throw "Missing service in docker compose ps output: $name"
    }
    if ($service.State -notin @("running", "healthy")) {
        throw "Service $name is not ready. Current state: $($service.State)"
    }
}

Write-Host "Memory stack services are present and running."
