$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\..")
docker compose -f docker-compose.qgis.yml down

Write-Host "QGIS Server containers stopped." -ForegroundColor Green
