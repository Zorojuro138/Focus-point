# Starts FocusPilot from source using this folder's virtual environment.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Output "No .venv found. Run these once:"
    Write-Output "  py -m venv .venv"
    Write-Output "  .\.venv\Scripts\python.exe -m pip install -e `".[dev]`""
    exit 1
}
& $python -m focuspilot
