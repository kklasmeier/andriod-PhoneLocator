# Android app — Phone Locator

Kotlin / Jetpack Compose app that collects location in a foreground service and uploads to the piSensors API.

## Build (Windows)

Requires Android SDK (Android Studio) and `ANDROID_HOME` or `local.properties` with `sdk.dir`.

### Debug API token (local only — not committed)

For testing, the debug APK can pre-fill the API URL and token from `android/secrets.properties` (gitignored):

```powershell
# One-time: pull token from piSensors into secrets.properties
.\scripts\sync-android-secrets.ps1 -FromPiSensors

# Or copy android/secrets.properties.example → secrets.properties and paste token
```

Then build:

```powershell
cd android
.\gradlew.bat assembleDebug
```

Release builds never embed a token.

APK: `android\app\build\outputs\apk\debug\app-debug.apk`

## First run

1. Install APK on phone (USB debugging or sideload).
2. Open app → complete setup:
   - **API URL:** `http://192.168.1.26:8000/locator` (home WiFi) — pre-filled in debug builds
   - **API token:** pre-filled in debug builds if `secrets.properties` exists; otherwise from piSensors env
   - **Device ID:** auto-generated
3. Grant location (including **Allow all the time**) and notifications.
4. Disable battery optimization when prompted (recommended).

## Tests

```powershell
cd android
.\gradlew.bat test
```

```cmd
.\test.bat android
```

## Phase 4 dashboard (Status + Log tabs)

- **Status:** colored health indicator, last sent/reading, queue, 24h upload success %, service uptime
- **Alerts:** only when uploads back up for **4+ hours** (e.g. VPN off) — not on routine successful sends
- **Problem banners** when upload backlog detected (not permissions/battery on every screen load)
- **Log:** last 50 upload/service events with refresh and clear
- **Settings:** permission summary, battery optimization shortcut, queue size, clear log

## Remote access (WireGuard VPN)

Public HTTPS through the Nighthawk router is **deferred**. For uploads away from home WiFi, connect the phone to **home WireGuard** first, then use the same API URL:

```text
http://192.168.1.26:8000/locator
```

WireGuard inbound: UDP **51822** → piGateway (`192.168.1.100`). Once the VPN tunnel is up, the phone can reach piSensors on the LAN.

**Verify on phone (VPN connected):** open `http://192.168.1.26:8000/locator/api/v1/health` — should show `{"status":"ok"}`.

## LAN note

On home WiFi (no VPN), the same URL works. No separate public API URL is required for this implementation.
