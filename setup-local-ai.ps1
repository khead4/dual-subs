$ErrorActionPreference = "Stop"

Set-Location $PSScriptRoot

$profile = if ($env:DUAL_SUBTITLE_LOCAL_PROFILE) { $env:DUAL_SUBTITLE_LOCAL_PROFILE } else { "all" }
$whisperModel = if ($env:LOCAL_WHISPER_MODEL) { $env:LOCAL_WHISPER_MODEL } else { "small" }
$localAiRoot = Join-Path $PSScriptRoot ".local-ai"

$env:XDG_DATA_HOME = Join-Path $localAiRoot "share"
$env:XDG_CONFIG_HOME = Join-Path $localAiRoot "config"
$env:XDG_CACHE_HOME = Join-Path $localAiRoot "cache"
$env:STANZA_RESOURCES_DIR = Join-Path $localAiRoot "stanza_resources"
$env:HF_HOME = Join-Path $localAiRoot "huggingface"

Write-Host "Installing the offline subtitle dependencies..."
python -m pip install -r requirements.txt -r requirements-local.txt

Write-Host "Downloading the offline transcription and translation models..."
python scripts\setup_local_models.py --profile $profile --whisper-model $whisperModel

Write-Host ""
Write-Host "Local subtitle setup is complete."
Write-Host "Restart start-local.bat, then open http://127.0.0.1:8000"
