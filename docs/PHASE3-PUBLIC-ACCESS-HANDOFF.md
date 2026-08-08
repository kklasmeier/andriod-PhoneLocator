# Phase 3 Public Access — Handoff Document

**Project:** Phone Locator (`c:\Projects\andriod-PhoneLocator`)  
**Date:** July 26, 2026  
**Status:** Phase 2 complete; Phase 3 (public HTTPS/API) **blocked** on inbound connectivity  
**Audience:** Next agent continuing Phase 3

---

## Goal

Make the Phone Locator API reachable from the phone **without VPN**, ideally at a public URL so the Android app can upload location when away from home WiFi.

**Target URL (original plan):** `https://kklasmei.mooo.com`  
**Interim test URL attempted:** `http://kklasmei.mooo.com:51823/locator`

---

## What works today

| Component | Status |
|-----------|--------|
| Phase 1 API on piSensors | ✅ Deployed, `127.0.0.1:8003` |
| Phase 2 Android app | ✅ Tracking, sync, reboot survival verified |
| LAN API via nginx | ✅ `http://192.168.1.26:8000/locator/api/v1/health` |
| Direct on Pi | ✅ `http://127.0.0.1:8003/api/v1/health` |
| Phone device_id | `0ab2b40f-c496-49f4-990d-9309573445d4` |
| DDNS | ✅ `kklasmei.mooo.com` → `74.215.40.180` |
| WireGuard inbound (UDP) | ✅ Port 51822 → `192.168.1.100` (piGateway) |

**Phone app default LAN URL:** `http://192.168.1.26:8000/locator`  
**Debug token:** in `android/secrets.properties` (gitignored), synced from piSensors env. User plans to rotate at end of project — do not commit token.

---

## Infrastructure reference

| Host | IP | Role |
|------|-----|------|
| piSensors | 192.168.1.26 | API, DB, nginx :8000 |
| piGateway | 192.168.1.100 | VPN (WireGuard) |
| Public IP | 74.215.40.180 | Home WAN (matches DDNS) |

**nginx on piSensors (port 8000):** `/etc/nginx/sites-available/pivpngateway`  
- `/locator/` → `http://127.0.0.1:8003/`  
- `/gateway/`, cameras, etc. also on 8000

**Important:** Pi port **8080** is a **different app** (Network Activity), NOT Phone Locator.  
Phone Locator is on port **8000** only.

---

## Phase 3 attempts and results

### 1. Let's Encrypt HTTP-01 (port 80)

- **Script:** `server/deploy/install-https-pisensors.sh`
- **Result:** ❌ Timeout — Let's Encrypt cannot reach port 80 from internet
- Router had port triggering initially (wrong); later corrected to port forwarding 80→.26

### 2. Let's Encrypt TLS-ALPN-01 (port 443) via certbot

- **Result:** ❌ Certbot 4.0 does **not** support `tls-alpn-01` with standalone plugin

### 3. acme.sh TLS-ALPN-01 on port 443

- **Result:** ❌ Timeout from Let's Encrypt to `74.215.40.180:443`
- Note: Phone on cellular sometimes showed **connection refused** on HTTPS (port reaches Pi but nothing listening). LE still timed out during challenge.

### 4. DNS-01 via certbot + afraid.org

- **Result:** ❌ afraid.org blocks subdomain names starting with `_` on shared `mooo.com` domains
- Error: *"Creation of records beginning with '_' are presently restricted to the domain owner only"*
- Cannot create `_acme-challenge.kklasmei.mooo.com` TXT record
- **Workaround:** Own domain with full DNS control, or email `dnsadmin@afraid.org`

### 5. Alternate port HTTP (51823 → 8000)

- User wants public access **without VPN**
- Router rule (port **forwarding**, not triggering):

| # | Service | External | Internal | IP |
|---|---------|----------|----------|-----|
| 6 | Web Traffic (Clear 8080) | **51823** | **8000** | 192.168.1.26 |

- **Result:** ❌ Timeout from internet (curl exit 28 from external test)
- **Local test:** `http://192.168.1.26:8000/locator/api/v1/health` → OK
- **Wrong local test:** `http://192.168.1.26:8080/...` → 404 (different nginx site)

---

## Router lessons (critical)

### Port forwarding vs port triggering

| | Port forwarding ✅ | Port triggering ❌ |
|---|-------------------|---------------------|
| Use for | Always-on servers (API, VPN, cameras) | Apps that connect out first, then open return path |
| Phone Locator | **Required** | Will not work |

User initially used **port triggering** — likely contributed to early failures.

### Protocol: TCP vs UDP

| Service | Protocol | Works? |
|---------|----------|--------|
| WireGuard (51822 → .100) | **UDP** | ✅ |
| HTTP/API (51823 → .26:8000) | **TCP** | ❌ (must verify rule is TCP, not UDP) |

WireGuard working does **not** prove TCP forwarding works.

### Internal port mapping

External port does not have to equal internal port:

```text
Internet :51823  →  192.168.1.26:8000   ✅ correct
Internet :51823  →  192.168.1.26:8080   ❌ wrong (Network Activity app)
```

### NAT hairpin

Testing `kklasmei.mooo.com:51823` **from home WiFi** may fail even when cellular works. Always test from **cellular** or external network.

---

## ISP: Altafiber / Fuse.net (Cincinnati)

User ISP: **Fuse.net** (Altafiber / Cincinnati Bell)

From [Altafiber network disclosure (Oct 2024)](https://www.altafiber.com/getmedia/93cf7858-1b11-4c37-bb27-eb6ab82dc158/October-2024-Wireline-Disclosure-101024-altafiber.pdf):

- **Fioptics / ZoomTown (fiber):** Does **not** broadly block inbound TCP. Only blocks ports 23 and 25 (plus outbound SMTP on dynamic IP).
- **Lebanon DOCSIS (cable):** Blocks inbound **TCP 80 and 443** on some residential tiers — should **not** affect port 51823.
- Policy does **not** explain why TCP 51823 times out if router rule is correct TCP.

**Possible causes still open:**

1. Router rule #6 is **UDP** instead of **TCP**
2. **CGNAT** — check router WAN IP vs `74.215.40.180` (if `100.64.x.x`, port forwarding won't work)
3. Router needs reboot after rule changes
4. ISP static IP / business tier needed (call Altafiber)

---

## Files created for Phase 3

| File | Purpose |
|------|---------|
| `server/deploy/install-https-pisensors.sh` | certbot + nginx HTTPS (HTTP-01); has DNS/acme fallback messages |
| `server/deploy/install-https-pisensors-acme.sh` | acme.sh TLS-ALPN (certbot can't do this) |
| `server/deploy/install-https-pisensors-dns.sh` | Manual DNS-01 certbot |
| `server/deploy/nginx-locator-https.conf` | Template nginx site for `kklasmei.mooo.com` |
| `DEPLOY.md` | Phase 3 section with router/DNS steps |
| `scripts/pisensors-query.ps1` | Lookup device_id + print curl commands |
| `android/.../SettingsRepository.kt` | `PRODUCTION_API_URL = https://kklasmei.mooo.com` |

**Git commits (local, may need push):**
- `5237859` — Phase 2 Android MVP
- `6f5102d` / `ebacc7e` — Phase 3 HTTPS deploy scripts

---

## Recommended next steps (priority order)

### A. Confirm router TCP forwarding (quick)

1. Edit router rule #6: **Protocol = TCP**, external 51823 → internal **8000** → 192.168.1.26
2. Check router **WAN IP** = `74.215.40.180` (not `100.64.x.x`)
3. Test from **cellular**: `http://74.215.40.180:51823/locator/api/v1/health`
4. If OK → set phone API URL to `http://kklasmei.mooo.com:51823/locator` (HTTP, unencrypted — interim only)

### B. Cloudflare Tunnel (best if TCP inbound blocked)

- Outbound connection from Pi — no port forwarding needed
- Requires own domain on Cloudflare (not afraid.org `mooo.com` for `_acme-challenge`)
- HTTPS at edge, tunnel to `127.0.0.1:8003`

### C. Own domain + DNS-01 cert + HTTPS on alt port

- Buy domain, point to home IP or Cloudflare
- DNS-01 cert (no port 80 needed for issuance)
- nginx listen on 8443 with cert; forward external 8443 → internal 8443

### D. Call Altafiber

Ask: CGNAT? Static public IP option? Inbound TCP 51823 for self-hosting?

### E. Do NOT pursue (blocked/deferred)

- DNS-01 on `kklasmei.mooo.com` via afraid.org (`_` subdomain restriction)
- certbot `tls-alpn-01` (unsupported in certbot 4.0)
- Standard HTTPS on 443 until inbound TCP confirmed working
- VPN-only solution (user explicitly does not want VPN for this)

---

## Useful commands

**Health check (LAN):**
```bash
curl -s http://127.0.0.1:8000/locator/api/v1/health
curl -s http://192.168.1.26:8000/locator/api/v1/health
```

**Latest location (needs device_id):**
```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  "http://127.0.0.1:8003/api/v1/location/latest?device_id=0ab2b40f-c496-49f4-990d-9309573445d4"
```

**Device IDs from DB:**
```bash
python3 -c "import sqlite3; c=sqlite3.connect('/var/lib/phone-locator/phone-locator.db'); [print(r[0]) for r in c.execute('SELECT DISTINCT device_id FROM location_points')]"
```

**Public test (cellular):**
```text
http://74.215.40.180:51823/locator/api/v1/health
http://kklasmei.mooo.com:51823/locator/api/v1/health
```

**Skip cert, install nginx HTTPS only (after cert obtained):**
```bash
SKIP_CERT_REQUEST=1 CERTBOT_EMAIL=kklasmei@yahoo.com bash server/deploy/install-https-pisensors.sh
```

---

## Future phases already documented in PROJECT.md

| Phase | Name | Notes |
|-------|------|-------|
| 8 | Known Wi-Fi places | Skip GPS when on known SSID (e.g. ZNet) |
| 9 | QR pairing | Scan QR for API URL + token setup |

User preference: **do not rotate API token until project complete.**

---

## User preferences for next agent

- Include **actual token** in test commands when helping user debug (token in piSensors env / `android/secrets.properties`)
- Use `scripts/pisensors-query.ps1` to auto-fill device_id in curls
- Minimize scope; match existing patterns
- User manages git commits unless explicitly asked
