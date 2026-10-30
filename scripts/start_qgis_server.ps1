$ErrorActionPreference = "Stop"

Set-Location (Resolve-Path "$PSScriptRoot\..")
docker compose -f docker-compose.qgis.yml up -d --build

Write-Host "QGIS Server is expected at: http://127.0.0.1:8090/qgis-server/" -ForegroundColor Green
Write-Host "FastAPI status endpoint: http://127.0.0.1:8010/api/qgis/status" -ForegroundColor Green
