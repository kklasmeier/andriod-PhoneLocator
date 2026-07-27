# Deploying Phone Locator API

API runs on **piSensors** (`192.168.1.26`) at `127.0.0.1:8003`, proxied by nginx at `/locator/`.

| URL | Purpose |
|-----|---------|
| `http://192.168.1.26:8000/locator/api/v1/health` | Health (via nginx) |
| `http://192.168.1.26:8000/locator/api/v1/location/...` | API (via nginx) |
| `http://127.0.0.1:8003/api/v1/...` | Direct on Pi (debug) |
| `https://kklasmei.mooo.com/api/v1/...` | Public HTTPS (Phase 3 — phone) |

---

## Phase 3 — HTTPS (public API)

### 1. Router (manual)

Forward these ports to **piSensors** (`192.168.1.26`):

| External | Internal | Purpose |
|----------|----------|---------|
| TCP **443** | 443 | HTTPS API + web |
| TCP **80** | 80 | Let's Encrypt renewal (may already be forwarded) |

Confirm DDNS: `kklasmei.mooo.com` → your current public IP.

### 2. Install certificate on piSensors

```bash
ssh piSensors
cd ~/andriod-PhoneLocator
git pull
CERTBOT_EMAIL=you@example.com bash server/deploy/install-https-pisensors.sh
```

### 3. Verify

On piSensors:

```bash
curl -s https://kklasmei.mooo.com/api/v1/health
```

Off home WiFi (cellular), same URL should work.

### 4. Update phone app

**Settings → API URL:** `https://kklasmei.mooo.com`  
(Token unchanged.) Tap **Test connection**, then **Sync now**.

LAN URL (`http://192.168.1.26:8000/locator`) still works at home; HTTPS works everywhere.

---

## First-time install (piSensors)

```bash
ssh piSensors
cd ~/andriod-PhoneLocator
git pull
bash server/deploy/install-pisensors.sh
```

Save the generated **API token** printed on first install (also in `/etc/phone-locator/phone-locator.env`).

---

## Day-to-day deploy

```bash
ssh piSensors
cd ~/andriod-PhoneLocator
git pull
./deploy.sh
```

---

## Local development (Windows / PC)

```powershell
cd c:\Projects\andriod-PhoneLocator\server
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# Edit .env — set PHONE_LOCATOR_API_TOKEN
uvicorn app.main:app --host 127.0.0.1 --port 8003 --reload
```

Test:

```powershell
curl http://127.0.0.1:8003/api/v1/health
```

---

## API quick test

```bash
TOKEN="your-token-here"

# Health (no auth)
curl -s http://192.168.1.26:8000/locator/api/v1/health

# Upload batch
curl -s -X POST http://192.168.1.26:8000/locator/api/v1/location/batch \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "test-phone",
    "points": [{
      "client_point_id": "test-001",
      "latitude": 42.123456,
      "longitude": -83.123456,
      "accuracy_m": 10.0,
      "recorded_at": "2026-07-26T22:00:00Z"
    }]
  }'

# Latest
curl -s "http://192.168.1.26:8000/locator/api/v1/location/latest?device_id=test-phone" \
  -H "Authorization: Bearer $TOKEN"
```

---

## Files on piSensors

| Path | Purpose |
|------|---------|
| `/opt/phone-locator/` | App + venv |
| `/var/lib/phone-locator/phone-locator.db` | SQLite database |
| `/etc/phone-locator/phone-locator.env` | Config + API token |
| `/etc/systemd/system/phone-locator.service` | systemd unit |

---

## nginx

`install-pisensors.sh` adds `/locator/` to `/etc/nginx/sites-available/pivpngateway` if not already present. Manual snippet: `server/deploy/nginx-locator.snippet`.

---

## Tests (local — no GitHub CI)

### Windows (easiest — no execution-policy change)

From the repo root in **PowerShell** (note the `.\` prefix):

```powershell
.\test.bat
```

Integration tests (live piSensors API):

```powershell
$env:PHONE_LOCATOR_API_TOKEN = "fab06e8c4d29dc31afaaa8e8785ebd4fbc70af8c14f01d5d06189d7d4f29bcba"
$env:PHONE_LOCATOR_TEST_URL = "http://192.168.1.26:8000/locator"
.\test.bat integration
```

After Phase 3 HTTPS:

```powershell
$env:PHONE_LOCATOR_TEST_URL = "https://kklasmei.mooo.com"
.\test.bat integration
```

In **cmd.exe** (not PowerShell), environment variables use `set`:

```cmd
set PHONE_LOCATOR_API_TOKEN=paste-token-here
.\test.bat integration
```

### PowerShell (if scripts are allowed)

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Integration
```

### API token (you do not create this on Windows)

The token was **generated automatically** when you ran `install-pisensors.sh` on piSensors.

**Retrieve it on the Pi:**

```bash
ssh piSensors
sudo grep PHONE_LOCATOR_API_TOKEN /etc/phone-locator/phone-locator.env
```

Copy the value after `=` (the long hex string). Use it on your PC:

```cmd
set PHONE_LOCATOR_API_TOKEN=paste-token-here
.\test.bat integration
```

Or in PowerShell:

```powershell
$env:PHONE_LOCATOR_API_TOKEN = "paste-token-here"
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Integration
```

You only need the token for **integration** tests (live API on piSensors). **Unit tests do not need a token.**

### Android debug APK (pre-fill token on setup)

On your PC (writes gitignored `android/secrets.properties`):

```powershell
.\scripts\sync-android-secrets.ps1 -FromPiSensors
cd android
.\gradlew.bat assembleDebug
adb install -r app\build\outputs\apk\debug\app-debug.apk
```

Debug builds pre-fill API URL and token on the setup screen. **Phase 9** will add QR scan pairing instead.

### Linux / piSensors

```bash
./scripts/test.sh
export PHONE_LOCATOR_API_TOKEN=<token>
./scripts/test.sh --integration
```

| Suite | Command | Needs token? |
|-------|---------|--------------|
| Server unit | `.\test.bat` | No |
| Integration | `.\test.bat integration` | Yes (from Pi) |
| Android unit | `.\test.bat android` | No (Phase 2+) |

GitHub Actions can be added later when the project is mature enough.
