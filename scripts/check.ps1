$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
Set-Location -LiteralPath $repo
function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command failed with exit code $LASTEXITCODE" }
}
Invoke-Checked '.\.venv\Scripts\ruff.exe' @('check', 'backend', 'scripts')
Invoke-Checked '.\.venv\Scripts\ruff.exe' @('format', '--check', 'backend', 'scripts')
Invoke-Checked '.\.venv\Scripts\mypy.exe' @('--config-file', 'backend/pyproject.toml', 'backend/src/fileora')
Invoke-Checked '.\.venv\Scripts\pytest.exe' @('backend/tests', '-q')
Push-Location -LiteralPath 'frontend'
try {
    Invoke-Checked 'npx.cmd' @('prettier', '--check', 'src', 'e2e', '*.ts', '*.json', 'index.html')
    Invoke-Checked 'npm.cmd' @('run', 'test')
    Invoke-Checked 'npm.cmd' @('run', 'build')
} finally { Pop-Location }
