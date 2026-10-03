param([switch]$Media, [switch]$NoMedia, [switch]$Watch, [ValidateSet('cpu','auto','cuda')][string]$Device = 'cpu', [int]$Port = 8765,
      [ValidateRange(0,45)][double]$PptOcrSeconds = 20, [ValidateRange(0,1000)][int]$PptOcrMaxImages = 48)
$ErrorActionPreference = 'Stop'
if ($Media -and $NoMedia) { throw 'Choose either -Media or -NoMedia.' }
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
$cli = Join-Path $repo '.venv\Scripts\fileora.exe'
if (-not (Test-Path -LiteralPath $cli)) { throw 'Run scripts/setup.ps1 first.' }
. (Join-Path $PSScriptRoot 'runtime.ps1')
Assert-FileoraStopped -Repo $repo
$arguments = @('--data-dir', '.fileora', '--device', $Device, '--ocr', '--vision')
$arguments += @('--ppt-ocr-seconds', $PptOcrSeconds.ToString([System.Globalization.CultureInfo]::InvariantCulture), '--ppt-ocr-max-images', $PptOcrMaxImages)
if ($Media) { $arguments += '--media' }
if ($NoMedia) { $arguments += '--no-media' }
$arguments += @('serve', '--port', $Port)
if ($Watch) { $arguments += '--watch' }
Write-Host "Fileora: http://127.0.0.1:$Port (Ctrl+C to stop)"
& $cli @arguments
exit $LASTEXITCODE
