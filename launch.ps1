# launch.ps1 - Automated Cross-Platform Launcher for Windows PowerShell
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ">>> AI Context Dumper Launcher" -ForegroundColor Cyan

# 1. Locate Python Interpreter
$pythonExe = $null

if (Test-Path "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe") {
    $pythonExe = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonExe = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = "python"
}

if (-not $pythonExe) {
    Write-Error "No valid Python installation found. Please ensure Python >= 3.9 is installed."
    exit 1
}

# 2. Setup Virtual Environment
$venvPath = Join-Path $PSScriptRoot ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating project virtual environment in .venv..." -ForegroundColor Yellow
    & $pythonExe -m venv $venvPath
}

# 3. Reconcile Dependencies
Write-Host "Verifying requirements..." -ForegroundColor Yellow
& $venvPython -m pip install --quiet --upgrade pip
& $venvPython -m pip install --quiet -r requirements.txt

# 4. Launch Application
Write-Host "Launching AI Context Dumper..." -ForegroundColor Green
& $venvPython dump.py