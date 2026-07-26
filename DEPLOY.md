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

Run from the repo root on your PC:

```powershell
# Server unit tests only (fast, no network)
.\scripts\test.ps1
```

```powershell
# + live smoke test against piSensors
$env:PHONE_LOCATOR_API_TOKEN = "<token>"
.\scripts\test.ps1 -Integration
```

On Linux / piSensors (unit tests only):

```bash
./scripts/test.sh
./scripts/test.sh --integration   # needs PHONE_LOCATOR_API_TOKEN
```

| Suite | Command | Needs |
|-------|---------|-------|
| Server unit | `.\scripts\test.ps1` | Python on PC |
| Integration | `.\scripts\test.ps1 -Integration` | PC + LAN access to piSensors + token |
| Android unit | `.\scripts\test.ps1 -Android` | Phase 2+; Android SDK on PC |

GitHub Actions can be added later when the project is mature enough.
