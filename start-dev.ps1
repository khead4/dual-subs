$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot

Write-Host "Starting Dual Subtitle Studio in developer reload mode at http://127.0.0.1:8000" -ForegroundColor Cyan
Write-Host "Use start-local.bat for stable long video renders." -ForegroundColor DarkGray

python -m uvicorn api.server:app --host 127.0.0.1 --port 8000 --reload
