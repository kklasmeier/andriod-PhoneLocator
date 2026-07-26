# Deploying Phone Locator API

API runs on **piSensors** (`192.168.1.26`) at `127.0.0.1:8003`, proxied by nginx at `/locator/`.

| URL | Purpose |
|-----|---------|
| `http://192.168.1.26:8000/locator/api/v1/health` | Health (via nginx) |
| `http://192.168.1.26:8000/locator/api/v1/location/...` | API (via nginx) |
| `http://127.0.0.1:8003/api/v1/...` | Direct on Pi (debug) |

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

From the repo root:

```cmd
test.bat
```

```cmd
test.bat integration
```

Set your token first (see **API token** below):

```cmd
set PHONE_LOCATOR_API_TOKEN=your-token-here
test.bat integration
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
test.bat integration
```

Or in PowerShell:

```powershell
$env:PHONE_LOCATOR_API_TOKEN = "paste-token-here"
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -Integration
```

You only need the token for **integration** tests (live API on piSensors). **Unit tests do not need a token.**

### Linux / piSensors

```bash
./scripts/test.sh
export PHONE_LOCATOR_API_TOKEN=<token>
./scripts/test.sh --integration
```

| Suite | Command | Needs token? |
|-------|---------|--------------|
| Server unit | `test.bat` | No |
| Integration | `test.bat integration` | Yes (from Pi) |
| Android unit | `test.bat android` | No (Phase 2+) |

GitHub Actions can be added later when the project is mature enough.
