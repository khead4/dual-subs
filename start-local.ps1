$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$appUrl = "http://127.0.0.1:8000"

Set-Location $projectRoot

try {
  Get-Command python -ErrorAction Stop | Out-Null
} catch {
  Write-Host "Python was not found on this machine." -ForegroundColor Red
  Write-Host "Install Python 3.12+, then run this launcher again." -ForegroundColor Yellow
  exit 1
}

python -c "import fastapi, uvicorn" 2>$null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Project dependencies are missing." -ForegroundColor Red
  Write-Host "Run: pip install -r requirements.txt" -ForegroundColor Yellow
  exit 1
}

Start-Job -ScriptBlock {
  param($url)
  for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Seconds 1
    try {
      Invoke-WebRequest -UseBasicParsing -Uri "$url/api/health" | Out-Null
      Start-Process $url
      break
    } catch {
    }
  }
} -ArgumentList $appUrl | Out-Null

Write-Host "Starting Dual Subtitle Studio at $appUrl" -ForegroundColor Cyan
Write-Host "Keep this window open while you use the app." -ForegroundColor DarkGray

python -m uvicorn api.server:app --host 127.0.0.1 --port 8000
