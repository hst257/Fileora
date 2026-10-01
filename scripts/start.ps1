param([switch]$Media, [switch]$Watch, [ValidateSet('cpu','auto','cuda')][string]$Device = 'cpu', [int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
$cli = Join-Path $repo '.venv\Scripts\fileora.exe'
if (-not (Test-Path -LiteralPath $cli)) { throw 'Run scripts/setup.ps1 first.' }
. (Join-Path $PSScriptRoot 'runtime.ps1')
Assert-FileoraStopped -Repo $repo
$arguments = @('--data-dir', '.fileora', '--device', $Device, '--ocr', '--vision')
if ($Media) { $arguments += '--media' }
$arguments += @('serve', '--port', $Port)
if ($Watch) { $arguments += '--watch' }
Write-Host "Fileora: http://127.0.0.1:$Port (Ctrl+C to stop)"
& $cli @arguments
exit $LASTEXITCODE
