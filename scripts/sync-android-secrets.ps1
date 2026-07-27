# Write android/secrets.properties from env or argument (gitignored — not committed).
#
# Usage:
#   $env:PHONE_LOCATOR_API_TOKEN = "<token from piSensors>"
#   .\scripts\sync-android-secrets.ps1
#
#   .\scripts\sync-android-secrets.ps1 -Token "<token>"
#   .\scripts\sync-android-secrets.ps1 -FromPiSensors

param(
    [string]$Token = $env:PHONE_LOCATOR_API_TOKEN,
    [string]$ApiUrl = $env:PHONE_LOCATOR_API_URL,
    [switch]$FromPiSensors
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$outFile = Join-Path $repoRoot "android\secrets.properties"

if ($FromPiSensors) {
    $line = ssh piSensors "grep PHONE_LOCATOR_API_TOKEN /etc/phone-locator/phone-locator.env"
    if ($line -match '^PHONE_LOCATOR_API_TOKEN=(.+)$') {
        $Token = $Matches[1].Trim()
    } else {
        Write-Error "Could not read token from piSensors"
        exit 1
    }
}

if (-not $Token) {
    Write-Host "ERROR: No token. Set PHONE_LOCATOR_API_TOKEN, pass -Token, or use -FromPiSensors" -ForegroundColor Red
    Write-Host '  ssh piSensors "grep PHONE_LOCATOR_API_TOKEN /etc/phone-locator/phone-locator.env"'
    exit 1
}

if (-not $ApiUrl) {
    $ApiUrl = "http://192.168.1.26:8000/locator"
}

@"
PHONE_LOCATOR_API_URL=$ApiUrl
PHONE_LOCATOR_API_TOKEN=$Token
"@ | Set-Content -Path $outFile -Encoding utf8

Write-Host "Wrote $outFile"
Write-Host "Rebuild debug APK:  cd android; .\gradlew.bat assembleDebug"
