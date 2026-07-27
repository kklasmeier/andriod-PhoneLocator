# Query piSensors for device IDs and print ready-to-run curl commands.
# Usage (from repo root):
#   .\scripts\pisensors-query.ps1
#   .\scripts\pisensors-query.ps1 -Latest

param(
    [switch]$Latest
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path $PSScriptRoot -Parent
$token = $env:PHONE_LOCATOR_API_TOKEN

if (-not $token) {
    $secretsFile = Join-Path $repoRoot "android\secrets.properties"
    if (Test-Path $secretsFile) {
        Get-Content $secretsFile | ForEach-Object {
            if ($_ -match '^PHONE_LOCATOR_API_TOKEN=(.+)$') {
                $token = $Matches[1].Trim()
            }
        }
    }
}

if (-not $token) {
  $token = (& ssh piSensors "grep PHONE_LOCATOR_API_TOKEN /etc/phone-locator/phone-locator.env" 2>$null) -replace '^PHONE_LOCATOR_API_TOKEN=', ''
}

$py = @'
import sqlite3
c = sqlite3.connect("/var/lib/phone-locator/phone-locator.db")
rows = list(c.execute(
    "SELECT device_id, MAX(received_at) AS last_seen FROM location_points "
    "GROUP BY device_id ORDER BY last_seen DESC"
))
for device_id, last_seen in rows:
    print(f"{device_id}\t{last_seen}")
'@

Write-Host "Device IDs on piSensors (newest first):" -ForegroundColor Cyan
$rows = $py | ssh piSensors python3
if (-not $rows) {
    Write-Host "No points in database yet."
    exit 0
}

$deviceIds = @()
foreach ($line in $rows) {
    if ($line -match '^(.+?)\t(.+)$') {
        $deviceIds += $Matches[1]
        Write-Host ("  {0}  (last: {1})" -f $Matches[1], $Matches[2])
    }
}

$phoneId = $deviceIds | Where-Object {
    $_ -notin @('test-phone', 'integration-test-device')
} | Select-Object -First 1

if (-not $phoneId) {
    $phoneId = $deviceIds[0]
}

Write-Host ""
Write-Host "Likely phone device_id: $phoneId" -ForegroundColor Green
Write-Host ""
Write-Host "Copy-paste on piSensors:" -ForegroundColor Cyan

$auth = "Authorization: Bearer $token"
Write-Host ""
Write-Host "curl -s -H `"$auth`" `"http://127.0.0.1:8003/api/v1/location/latest?device_id=$phoneId`""
Write-Host ""
Write-Host "curl -s -H `"$auth`" `"http://127.0.0.1:8000/locator/api/v1/location/latest?device_id=$phoneId`""

if ($Latest) {
    Write-Host ""
    Write-Host "Latest point:" -ForegroundColor Cyan
    ssh piSensors "curl -s -H 'Authorization: Bearer $token' 'http://127.0.0.1:8003/api/v1/location/latest?device_id=$phoneId'"
    Write-Host ""
}
