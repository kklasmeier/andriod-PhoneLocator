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

## LAN note

Use the **LAN URL** until Phase 3 (HTTPS + public domain). Phone must be on home WiFi to reach `192.168.1.26`.
