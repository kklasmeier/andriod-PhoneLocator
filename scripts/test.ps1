# Run all Phone Locator tests (local — no GitHub CI).
#
# Usage:
#   .\scripts\test.ps1                 # server unit tests
#   .\scripts\test.ps1 -Integration    # + live API on piSensors (needs token)
#   .\scripts\test.ps1 -Android        # + Android unit tests (when android/ exists)
#
# Integration env vars (or pass -Integration to prompt-free run if already set):
#   $env:PHONE_LOCATOR_TEST_URL = "http://192.168.1.26:8000/locator"
#   $env:PHONE_LOCATOR_API_TOKEN = "<token>"

param(
    [switch]$Integration,
    [switch]$Android
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ServerDir = Join-Path $RepoRoot "server"
$VenvPython = Join-Path $ServerDir "venv\Scripts\python.exe"
$VenvPip = Join-Path $ServerDir "venv\Scripts\pip.exe"

Write-Host "==> Phone Locator tests" -ForegroundColor Cyan

if (-not (Test-Path $VenvPython)) {
    Write-Host "==> Creating server venv"
    python -m venv (Join-Path $ServerDir "venv")
}

Write-Host "==> Installing server dependencies"
& $VenvPip install -q -U pip
& $VenvPip install -q -r (Join-Path $ServerDir "requirements-dev.txt")

Write-Host "==> Server unit tests"
Push-Location $ServerDir
& $VenvPython -m unittest discover -s tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }

if ($Integration) {
    if (-not $env:PHONE_LOCATOR_TEST_URL) {
        $env:PHONE_LOCATOR_TEST_URL = "http://192.168.1.26:8000/locator"
    }
    if (-not $env:PHONE_LOCATOR_API_TOKEN) {
        Write-Host "ERROR: Set PHONE_LOCATOR_API_TOKEN for integration tests" -ForegroundColor Red
        Write-Host '  PowerShell:  $env:PHONE_LOCATOR_API_TOKEN = "<token from piSensors>"'
        Write-Host "  cmd.exe:     set PHONE_LOCATOR_API_TOKEN=<token>"
        Pop-Location
        exit 1
    }
    Write-Host "==> Integration tests against $($env:PHONE_LOCATOR_TEST_URL)"
    & $VenvPython -m unittest tests.test_integration -v
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
}

Pop-Location

$AndroidDir = Join-Path $RepoRoot "android"
if ($Android) {
    if (-not (Test-Path (Join-Path $AndroidDir "gradlew.bat"))) {
        Write-Host "ERROR: android/ not scaffolded yet" -ForegroundColor Red
        exit 1
    }
    Write-Host "==> Android unit tests"
    Push-Location $AndroidDir
    .\gradlew.bat test
    if ($LASTEXITCODE -ne 0) { Pop-Location; exit $LASTEXITCODE }
    Pop-Location
}

Write-Host "==> All requested tests passed" -ForegroundColor Green
