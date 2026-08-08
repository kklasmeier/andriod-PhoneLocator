# Phase 3 — Public Access Handoff

**Project:** Phone Locator (`c:\Projects\andriod-PhoneLocator`)  
**Last updated:** August 7, 2026  
**Status:** **Deferred** — remote access uses **WireGuard VPN only** for this implementation.

### Decision (Aug 7, 2026)

Public HTTPS / Nighthawk TCP port forwarding was not reliable enough to ship. **VPN-only** is the chosen approach:

- Phone connects to **WireGuard** (UDP 51822 → piGateway `192.168.1.100`) when away from home.
- App API URL stays **`http://192.168.1.26:8000/locator`** (same on LAN or VPN).
- Phase 3 scripts and notes below are kept for a future attempt (Cloudflare Tunnel, own domain, etc.).

This document is historical context for the public-access / HTTPS work.

---

## Goal (Phase 3)

Make the Phone Locator API reachable from the phone **without VPN**, ideally over HTTPS:

- Target URL (original plan): `https://kklasmei.mooo.com`
- Phone app API base URL field accepts any URL (Retrofit paths are `api/v1/...`)
- Phase 3 acceptance criteria in `PROJECT.md` §16

**User constraint:** Does **not** want VPN as the long-term solution for phone → server access. Wants a truly public endpoint.

### Confirmed by user (Jul 26, 2026)

| Item | Status |
|------|--------|
| **Port forwarding protocol** | **TCP** for all piSensors web/API rules (80, 443, 8443, 51823→8000). **Not UDP.** UDP is only used for WireGuard (51822 → piGateway `.100`). |
| **Public IP address** | **`74.215.40.180`** — verified in a browser via [ifconfig.me](https://ifconfig.me/) (matches afraid.org DDNS). **CGNAT is unlikely** if router WAN IP also shows this address. |
| **External testing** | From **phone on AT&T cellular** (mobile data, Wi‑Fi off) — not home Wi‑Fi. Tests still **timeout** on `:51823`. |

---

## What works today

| Item | Status |
|------|--------|
| Phase 2 Android app (foreground service, upload queue, sync now) | ✅ Working |
| API on piSensors `127.0.0.1:8003` | ✅ Working |
| nginx LAN path `http://192.168.1.26:8000/locator/` | ✅ Working |
| Health check | `curl -s http://127.0.0.1:8000/locator/api/v1/health` → `{"status":"ok"}` |
| Phone uploads on home WiFi | ✅ Verified |
| Boot receiver / tracking after reboot | ✅ Verified |
| WireGuard VPN inbound UDP **51822** → `192.168.1.100` | ✅ Works from phone |

### Phone / API identifiers

| Item | Value |
|------|-------|
| Device ID (phone) | `0ab2b40f-c496-49f4-990d-9309573445d4` |
| API token | `/etc/phone-locator/phone-locator.env` on piSensors (`PHONE_LOCATOR_API_TOKEN`) |
| Latest endpoint | Requires `?device_id=` query param |

Example (run on piSensors, substitute token from env file):

```bash
curl -s -H "Authorization: Bearer <TOKEN>" \
  "http://127.0.0.1:8003/api/v1/location/latest?device_id=0ab2b40f-c496-49f4-990d-9309573445d4"
```

Helper script on Windows PC: `.\scripts\pisensors-query.ps1` (looks up device IDs + prints curl commands).

---

## Infrastructure

| Host | IP | Role |
|------|-----|------|
| piSensors | `192.168.1.26` | API, SQLite, nginx :8000 `/locator/` |
| piGateway | `192.168.1.100` | WireGuard VPN |
| Public DDNS | `kklasmei.mooo.com` | afraid.org → `74.215.40.180` |
| **Public IP (confirmed)** | **`74.215.40.180`** | User verified via browser at ifconfig.me |
| **ISP** | **Fuse.net / Altafiber — Fioptics / ZoomTown (fiber)** | Cincinnati area; see § ISP below |
| **Router** | **Netgear Nighthawk X6 (R8000)** | Port forwarding (not port triggering) |

### Internet service (confirmed)

User is on **Fuse.net** (branded **Altafiber**), **Fioptics / ZoomTown fiber** — not Lebanon DOCSIS cable. Per Altafiber's disclosure, this tier should **not** block arbitrary inbound TCP (only ports 23 and outbound 25). Port 80/443 ISP blocks on DOCSIS tiers likely **do not apply** to this account.

### piSensors ports (what actually listens)

| Port | Service | Notes |
|------|---------|-------|
| **8000** | nginx `pivpngateway` | **Phone Locator** at `/locator/` → proxies to `127.0.0.1:8003` |
| **8003** | FastAPI (localhost only) | `phone-locator.service` |
| **8080** | nginx `networktraffic` | **Different app** — "Network Activity" UI; `/locator/` returns **404** |
| **80** | nginx `default` | home-sensors dashboard |
| **443** | *(not listening)* | HTTPS not configured yet |
| **8443** | *(not listening)* | Forward rule exists on router but nothing on Pi |

**Critical:** External port forward to Pi port **8000** (not 8080) for Phone Locator HTTP.

### nginx sites enabled on piSensors

```
/etc/nginx/sites-enabled/
  default              # port 80 - home-sensors
  networktraffic       # port 8080
  phone-locator-https  # kklasmei.mooo.com (HTTP-only stub from failed certbot; no SSL yet)
  pivpngateway         # port 8000 - cameras, gateway, /locator/
  security-cameras
```

---

## Router configuration (Netgear Nighthawk X6 R8000)

**Model:** Netgear Nighthawk X6 **R8000**

User must use **Port Forwarding** (persistent), **not Port Triggering** (temporary; wrong for always-on API). On the R8000, custom services are under **Advanced → Advanced Setup → Port Forwarding / Port Triggering** — select **Port Forwarding**.

**Protocol (confirmed by user):** All rules to piSensors (`.26`) for web/API traffic use **TCP only — not UDP**. WireGuard to piGateway (`.100`) uses **UDP** only. HTTP/HTTPS/API is always **TCP**; UDP rules will not work for the locator API.

### Current rules (as of Jul 26, 2026)

| # | Service | External | Internal | IP | Protocol | Notes |
|---|---------|----------|----------|-----|----------|-------|
| 1 | VPN-PPTP-PiVPN | 51821 | 51821 | 192.168.1.100 | UDP? | piGateway |
| 2 | Wireguard | 51822 | 51822 | 192.168.1.100 | **UDP** | ✅ **Works** |
| 3 | Web Traffic | 443 | 443 | 192.168.1.26 | **TCP** ✅ | Nothing listening on Pi :443 yet |
| 4 | Web Traffic (Clear) | 80 | 80 | 192.168.1.26 | **TCP** ✅ | Pi nginx :80 (home-sensors, not locator) |
| 5 | Web Traffic (8443) | 8443 | 8443 | 192.168.1.26 | **TCP** ✅ | Nothing listening on Pi :8443 yet |
| 6 | Web Traffic (Clear 8080) | **51823** | **8000** | 192.168.1.26 | **TCP** ✅ | Intended public HTTP test URL; still timing out from internet |

### Intended public HTTP test URL (once TCP forward works)

```text
http://kklasmei.mooo.com:51823/locator/api/v1/health
```

Or by IP (bypass DNS):

```text
http://74.215.40.180:51823/locator/api/v1/health
```

**Phone app API URL would be:** `http://kklasmei.mooo.com:51823/locator`  
(App has `android:usesCleartextTraffic="true"` — HTTP is allowed.)

### Testing notes

- **External tests are from the user's phone on AT&T cellular** (mobile data, Wi‑Fi off) — correct method; avoids NAT hairpin issues on home Wi‑Fi.
- **Port forwarding only applies to traffic from the internet** (WAN → LAN).  
  `http://192.168.1.26:51823/...` on LAN hits Pi port **51823 directly** (wrong service / nothing) — **not** a valid test of the forward rule.
- On LAN, use `http://192.168.1.26:8000/locator/...` directly.
- Do **not** test public access from home Wi‑Fi — many routers lack NAT hairpin; `kklasmei.mooo.com` from home WiFi may hang even when forwarding works.
- External test from dev machine also **timed out** on `:51823` (curl exit 28) as of Jul 26.
- Phone on AT&T cellular: `http://74.215.40.180:51823/locator/api/v1/health` → **timeout** (still failing).

---

## What was tried (Phase 3) and results

### 1. Let's Encrypt HTTP-01 (port 80)

```bash
CERTBOT_EMAIL=kklasmei@yahoo.com bash server/deploy/install-https-pisensors.sh
```

**Result:** Failed — Let's Encrypt timeout connecting to `74.215.40.180:80`.

### 2. Let's Encrypt DNS-01 (manual, afraid.org)

```bash
sudo certbot certonly --manual --preferred-challenges dns \
  -d kklasmei.mooo.com --email kklasmei@yahoo.com --agree-tos
```

**Result:** Failed — `NXDOMAIN` for `_acme-challenge.kklasmei.mooo.com`.

**Root cause:** afraid.org **restricts subdomains starting with `_`** on shared `mooo.com` domains:

> "Creation of records beginning with '_' are presently restricted to the domain owner only"

User cannot add `_acme-challenge` TXT on `kklasmei.mooo.com` without domain-owner access. **DNS-01 with current DDNS hostname is not viable** unless afraid.org grants an exception or user buys their own domain.

**Note:** Certbot 4.0 removed `--manual-public-ip-logging-ok` flag.

### 3. acme.sh TLS-ALPN-01 (port 443)

```bash
sudo ~/.acme.sh/acme.sh --issue -d kklasmei.mooo.com --alpn --force --server letsencrypt
```

**Result:** Failed — LE timeout on `74.215.40.180:443`.

**Note:** Certbot does **not** support TLS-ALPN-01. acme.sh does, but LE still could not reach port 443.

### 4. Port forwarding confusion

- User initially used **Port Triggering** instead of **Port Forwarding** — wrong for always-on API.
- External **8080 → internal 8080** hits wrong Pi service (Network Activity on :8080), not Phone Locator (:8000).
- Correct mapping for locator: **external 51823 → internal 8000** on `192.168.1.26`, protocol **TCP**.

### 5. Public HTTP test on port 51823

**Result:** Timeout from internet. **Not yet working.**

- **Phone (AT&T cellular):** timeout on `http://74.215.40.180:51823/locator/api/v1/health` and hostname variant.
- **External curl:** timeout (exit 28).

WireGuard **UDP 51822** works from phone → proves **some** inbound reachability exists. User confirmed web/API rules are **TCP** (not UDP), so protocol mismatch is **ruled out**. Remaining suspects: router WAN IP mismatch vs ifconfig.me, wrong internal port, Pi firewall, or upstream block on TCP 51823.

---

## ISP research (Altafiber / Fuse.net)

**User's service:** Fuse.net / Altafiber **Fioptics / ZoomTown (fiber)** — residential fiber in Cincinnati area.

Source: [Altafiber network disclosure PDF (Oct 2024)](https://www.altafiber.com/getmedia/93cf7858-1b11-4c37-bb27-eb6ab82dc158/October-2024-Wireline-Disclosure-101024-altafiber.pdf)

| Service type | Inbound TCP policy | Applies to user? |
|--------------|-------------------|------------------|
| **Fioptics / ZoomTown (fiber)** | Does **not** generally block protocols. Only blocks **23** and outbound **25**. | **Yes — user's service** |
| **Lebanon DOCSIS (cable)** | Blocks inbound **TCP 80 and 443** on some residential tiers. Other ports may work. | No (not user's service) |

Altafiber policy suggests inbound TCP on port **51823** should be allowed on Fioptics fiber. The timeout issue is therefore **unlikely** to be a blanket ISP TCP block. **Ruled out:** TCP vs UDP (user uses **TCP** for all piSensors web rules). **Unlikely:** CGNAT (user's public IP is **`74.215.40.180`** per ifconfig.me in browser). Still worth confirming router **WAN IP** matches `74.215.40.180`.

### Public IP / CGNAT (confirmed via ifconfig.me)

User verified public IP in a browser: **[ifconfig.me](https://ifconfig.me/)** → **`74.215.40.180`** (matches afraid.org DDNS).

| Check | Result |
|-------|--------|
| ifconfig.me (browser) | **`74.215.40.180`** ✅ |
| afraid.org DDNS | **`74.215.40.180`** ✅ |
| Router WAN IP | **Should match** — confirm on R8000 status page if forwarding still fails |

| WAN IP | Meaning |
|--------|---------|
| `74.215.40.180` | Public IP — port forwarding should work if rules are correct |
| `100.64.x.x` or `10.x.x.x` | CGNAT / double NAT — inbound port forwarding will **not** work |

If router WAN IP differs from ifconfig.me: call Altafiber for **static/public IP** or use **Cloudflare Tunnel**.

---

## Repo artifacts for Phase 3

| File | Purpose |
|------|---------|
| `server/deploy/install-https-pisensors.sh` | certbot HTTP-01 + nginx HTTPS config |
| `server/deploy/install-https-pisensors-acme.sh` | acme.sh TLS-ALPN fallback (LE still timed out) |
| `server/deploy/install-https-pisensors-dns.sh` | Manual DNS-01 certbot (afraid.org blocked) |
| `server/deploy/nginx-locator-https.conf` | nginx template for `kklasmei.mooo.com` |
| `DEPLOY.md` | Phase 3 section (partially updated) |
| `android/.../SettingsRepository.kt` | `PRODUCTION_API_URL = https://kklasmei.mooo.com` |

Git: Phase 2 committed; Phase 3 deploy scripts committed locally (may need `git push`).

---

## Recommended next steps (priority order)

### A. Confirm root cause (15 min)

1. Router WAN IP vs `74.215.40.180` — user confirmed **`74.215.40.180`** via ifconfig.me in browser; verify router status page matches.
2. ~~Rule #6 protocol = **TCP**~~ **Confirmed: TCP** (not UDP) for all piSensors web rules.
3. ~~Test from **cellular**~~ **Done** — phone on **AT&T cellular**: `http://74.215.40.180:51823/locator/api/v1/health` → **timeout**.
4. Online TCP port checker: `74.215.40.180:51823`
5. On piSensors: `ss -tlnp | grep :8000` and check `ufw status` / firewall

### B. If TCP forward works — ship HTTP public API (quick win)

1. Phone app Settings → API URL: `http://kklasmei.mooo.com:51823/locator`
2. Document cleartext tradeoff (token + location not encrypted)
3. Phase 3 partially complete (public, not HTTPS)

### C. If TCP forward still fails — Cloudflare Tunnel (best no-VPN path)

1. User buys/moves domain to Cloudflare (or uses existing domain)
2. Run `cloudflared` on piSensors → tunnel to `127.0.0.1:8003` or `:8000/locator`
3. Phone uses `https://locator.example.com` — no inbound ports needed
4. See `PROJECT.md` and consider new `server/deploy/install-cloudflare-tunnel.sh`

### D. HTTPS with own domain (if TCP works)

1. Register domain user controls (not afraid.org `mooo.com` shared subdomain)
2. DNS-01 cert via certbot (no port 80 needed for issuance)
3. nginx listen **443** or **8443** with cert
4. Router forward external **8443 → 8443** (or 443 → 443)

### E. Call Altafiber

Ask: CGNAT status, static IP option, inbound TCP on port 51823 for self-hosting.

---

## Key commands reference

```bash
# On piSensors — local health (always works)
curl -s http://127.0.0.1:8000/locator/api/v1/health
curl -s http://127.0.0.1:8003/api/v1/health

# Public IP
curl -s https://ifconfig.me/

# What's listening
ss -tlnp | grep -E ':8000|:8080|:443|:8443'

# DNS TXT check (after apt install dnsutils)
dig TXT _acme-challenge.kklasmei.mooo.com +short @8.8.8.8

# Skip cert request, only install nginx HTTPS (after cert exists)
SKIP_CERT_REQUEST=1 CERTBOT_EMAIL=kklasmei@yahoo.com bash server/deploy/install-https-pisensors.sh
```

---

## Open questions for next agent

1. ~~Is router WAN IP public or CGNAT?~~ **Public IP `74.215.40.180` confirmed** via ifconfig.me in browser — still verify router WAN IP matches.
2. ~~Is port-forward rule #6 **TCP**?~~ **Yes — TCP, not UDP** for all piSensors web/API rules (UDP only for WireGuard to `.100`).
3. ~~Does public health URL work from cellular?~~ **No — timeout** from phone on **AT&T cellular** (Jul 26).
4. Does user want to proceed with **HTTP on 51823** (fast) or invest in **Cloudflare Tunnel** (proper HTTPS, no port forwarding)?
5. Will user buy own domain to escape afraid.org `_` subdomain restriction?

---

## Related PROJECT.md phases

| Phase | Notes |
|-------|-------|
| **3** | HTTPS + public URL — **in progress / blocked** |
| **9** | QR pairing for setup — future |
| **8** | Known Wi-Fi places — future |

User requested **no token rotation** until project complete. Token is in `android/secrets.properties` (gitignored) for debug builds only.
