$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

python -m PyInstaller --clean --noconfirm installer\focuspilot.spec

$compiler = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($null -ne $compiler) {
    & $compiler.Source installer\focuspilot.iss
} else {
    Write-Output "Windows app bundle created in dist\FocusPilot."
    Write-Output "Install Inno Setup to create dist\installer\FocusPilot-Setup.exe."
}
