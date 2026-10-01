param([switch]$Demo, [switch]$Media, [switch]$NoModels)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
. (Join-Path $PSScriptRoot 'runtime.ps1')
Assert-FileoraStopped -Repo $repo

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    Invoke-Checked 'python' @('-m', 'venv', '.venv')
}
$python = Join-Path $repo '.venv\Scripts\python.exe'
$cli = Join-Path $repo '.venv\Scripts\fileora.exe'
$uv = Join-Path $repo '.venv\Scripts\uv.exe'
New-Item -ItemType Directory -Force -Path '.fileora' | Out-Null
$env:UV_CACHE_DIR = Join-Path $repo '.fileora\uv-cache'
$env:PIP_CACHE_DIR = Join-Path $repo '.fileora\pip-cache'
$env:VIRTUAL_ENV = Join-Path $repo '.venv'
$env:HF_HOME = Join-Path $repo '.fileora\hub-cache'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:SCARF_ANALYTICS = 'false'
if (-not (Test-Path -LiteralPath $uv)) {
    Invoke-Checked $python @('-m', 'pip', 'install', 'uv>=0.11,<1')
}
$sync = @('sync', '--project', 'backend', '--active', '--locked', '--inexact', '--extra', 'dev', '--extra', 'ml', '--extra', 'code', '--extra', 'ocr')
if ($Media) { $sync += @('--extra', 'media') }
# --inexact retains the bootstrap uv executable; project packages use uv.lock.
Invoke-Checked $uv $sync
$npmCache = Join-Path $repo '.fileora\npm-cache'
Push-Location -LiteralPath 'frontend'
try {
    Invoke-Checked 'npm.cmd' @('ci', '--cache', $npmCache)
    Invoke-Checked 'npm.cmd' @('run', 'build')
} finally { Pop-Location }
Push-Location -LiteralPath 'scripts\ocr'
try { Invoke-Checked 'npm.cmd' @('ci', '--cache', $npmCache) } finally { Pop-Location }
if ($Media) {
    Push-Location -LiteralPath 'scripts\speech'
    try { Invoke-Checked 'npm.cmd' @('ci', '--cache', $npmCache) } finally { Pop-Location }
}
if (-not $NoModels) {
    Invoke-Checked $cli @('--data-dir', '.fileora', 'models', 'download', 'sentence-transformers/all-MiniLM-L6-v2', '--revision', '1110a243fdf4706b3f48f1d95db1a4f5529b4d41')
    Invoke-Checked $cli @('--data-dir', '.fileora', 'models', 'download', 'openai/clip-vit-base-patch32', '--revision', '3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268')
    if ($Media) {
        Invoke-Checked $cli @('--data-dir', '.fileora', 'models', 'download', 'Systran/faster-whisper-base.en', '--revision', '3d3d5dee26484f91867d81cb899cfcf72b96be6c')
    }
}
if ($Demo) {
    Invoke-Checked $python @('scripts/create_demo.py')
    Invoke-Checked $cli @('--data-dir', '.fileora', 'roots', 'add', (Join-Path $repo 'evaluation\corpus'))
    $index = @('--data-dir', '.fileora', '--device', 'cpu', '--ocr', '--vision')
    if ($Media) {
        Invoke-Checked $python @('scripts/create_media_demo.py')
        Invoke-Checked $cli @('--data-dir', '.fileora', 'roots', 'add', (Join-Path $repo 'evaluation\media_corpus'))
        $index += '--media'
    }
    Invoke-Checked $cli ($index + 'index')
}
Write-Host 'Fileora is ready. Run scripts/start.ps1 to open your local workspace.'
