# Build script for Fuji HDR Extractor (Windows)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host "Syncing dependencies with uv..."
uv sync --group dev

Write-Host "Building executable..."
uv run pyinstaller --noconfirm "Fuji HDR Extractor.spec"

Write-Host ""
Write-Host "Build complete."
Write-Host "Executable: $ProjectRoot\dist\Fuji HDR Extractor\Fuji HDR Extractor.exe"
Write-Host ""
Write-Host "You can copy the entire 'dist\Fuji HDR Extractor' folder anywhere and run the .exe."
