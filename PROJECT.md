# Phone Locator — Project Design

**Project:** Self-hosted Android phone location tracker  
**Last updated:** August 7, 2026  
**Status:** Phases **1–2, 4 complete**; Phase **3 deferred** (VPN-only remote access); Phases **5–9** not started  

**Revision notes (Aug 7):** Phase 4 app dashboard — status health indicators, 24h upload success %, service uptime, problem banners, activity log clear, settings permissions/advanced. Phase 3 public HTTPS deferred — remote access via WireGuard VPN and LAN API URL. Phases 1–2 shipped and verified on piSensors + Android.  

**Revision notes (Jul 26):** piSensors port audit; multi-site HTTPS via nginx; phone stores queue + summaries only (full history on server); web dashboard IA and layout; API backend port 8003; Android app IA (lean, collection-first); resizable Glance home screen widget; **Phase 8 — known Wi-Fi places** (SSID → learned location, skip GPS at home).  

This document is the single source of truth for *what* we are building and *why*. Implementation details (exact commands, file layouts, deploy scripts) will be added during build phases.

---

## Table of contents

1. [Problem statement](#1-problem-statement)
2. [Goals](#2-goals)
3. [Non-goals](#3-non-goals)
4. [Architecture overview](#4-architecture-overview)
5. [Infrastructure](#5-infrastructure)
6. [Security](#6-security)
7. [Data model](#7-data-model)
8. [API design](#8-api-design)
9. [Android app](#9-android-app)
    - [Design principles](#91-design-principles)
    - [Screen map](#92-screen-map)
    - [Status screen](#93-status-screen-home)
    - [Today screen](#94-today-screen)
    - [Activity log](#95-activity-log)
    - [Settings](#96-settings)
    - [Notification](#97-persistent-notification)
    - [What the app does not include](#98-what-the-app-does-not-include)
    - [Home screen widget](#910-home-screen-widget)
    - [Known Wi-Fi places (future)](#911-known-wi-fi-places-future)
10. [Web dashboard](#10-web-dashboard)
    - [Site map](#101-site-map)
    - [Global UI patterns](#102-global-ui-patterns)
    - [Home dashboard](#103-home-dashboard)
    - [Subpages](#104-subpages)
    - [Charts and rollups](#105-charts-and-rollups)
11. [Analytics engine](#11-analytics-engine)
12. [Offline queue and data integrity](#12-offline-queue-and-data-integrity)
13. [Data retention](#13-data-retention)
14. [HTTPS with Let's Encrypt](#14-https-with-lets-encrypt)
15. [Repository layout](#15-repository-layout)
16. [Build phases](#16-build-phases)
17. [Open items](#17-open-items)
18. [Quick reference](#18-quick-reference)

---

## 1. Problem statement

Google's **Find My Device** is frequently unable to connect to my phone when I need to locate it. This has persisted across multiple phones over many years. Likely contributors include battery saver, Doze mode, and the fundamental model: Google must reach *into* the phone on demand via FCM/push, which fails when the device is not actively listening.

I want a **self-hosted alternative** that I control: an Android app that **pushes** location and device telemetry to an API on my home network on a regular schedule (~every 3 minutes). A web dashboard on the same backend provides maps, history, and analytics.

---

## 2. Goals

| # | Goal |
|---|------|
| G1 | **Reliable location tracking** — phone actively pushes location outbound; no dependency on Google push infrastructure |
| G2 | **No data loss** — local queue on phone; flush to server when connectivity returns |
| G3 | **Rich telemetry** — capture all meaningful device/location context, not just lat/lon |
| G4 | **Dual timestamps** — store both when the reading was taken (`recorded_at`) and when the server received it (`received_at`) |
| G5 | **Phone app as more than uploader** — operational stats, health, and cached summaries from server (not a full local copy of history) |
| G6 | **Web dashboard** — richer maps, history, heatmaps, reports, and place management |
| G7 | **Self-hosted** — API and data stay on my Raspberry Pi; accessible from outside via afraid.org DDNS |
| G8 | **Keep all data forever** — no automatic purge; manual purge only when I choose |

---

## 3. Non-goals

- Replacing Google Find My Device for the general public (personal/family use only)
- Real-time sub-second tracking (3-minute interval is sufficient)
- iOS support (Android only for v1)
- Selling or distributing on Play Store (sideload / personal build)
- Geofence push alerts (possible later; not v1)

---

## 4. Architecture overview

```text
┌─────────────────────────────────────────────────────────────────┐
│  Android Phone                                                  │
│  ┌──────────────┐  ┌─────────────┐  ┌────────────────────────┐ │
│  │ Location +   │  │ Local       │  │ App UI: stats, health, │ │
│  │ telemetry    │→ │ queue only  │→ │ cached summaries       │ │
│  │ collector    │  │ + summaries │  │ (from API)             │ │
│  └──────────────┘  └──────┬──────┘  └────────────────────────┘ │
└───────────────────────────┼─────────────────────────────────────┘
                            │ HTTPS POST (batch)
                            ▼
              kklasmei.mooo.com (afraid.org DDNS)
                            │
                            ▼
              Router port forward :443 → piSensors
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│  piSensors (192.168.1.26) │                                     │
│  ┌────────────┐  ┌────────▼───────┐  ┌──────────────────────┐  │
│  │ nginx      │→ │ FastAPI        │→ │ SQLite               │  │
│  │ + Let's    │  │ location API   │  │ location_points,     │  │
│  │   Encrypt  │  │ + analytics    │  │ places, visits, …    │  │
│  └────────────┘  └────────┬───────┘  └──────────────────────┘  │
│                             │                                   │
│                    ┌────────▼───────┐                           │
│                    │ Web dashboard  │  ← browser (LAN or VPN)   │
│                    │ map, history,  │                           │
│                    │ reports        │                           │
│                    └────────────────┘                           │
└─────────────────────────────────────────────────────────────────┘
```

**Why push beats pull:** Outbound connections from the phone work through NAT, firewalls, and battery saver far more reliably than inbound "wake the phone" requests from a third party.

**Why piSensors:** Already hosts FastAPI services, nginx on port 8000, and deploy tooling (see `klasmeier-pi-gateway-ui`). Adding a `/locator/` path and backend fits existing patterns.

**Full history lives on piSensors only.** The phone keeps an upload queue (unsynced points) and lightweight cached summaries — not a complete mirror of all location data.

---

## 5. Infrastructure

### Home network

| Host alias  | IP             | OS              | SSH user | Role in this project        |
|-------------|----------------|-----------------|---------|-----------------------------|
| piGateway   | 192.168.1.100  | Raspberry Pi OS | `pi`    | Not primary host for locator  |
| piSensors   | 192.168.1.26   | Raspberry Pi OS | `pi`    | **API, DB, web dashboard**  |
| piMonitor   | 192.168.1.16   | Ubuntu          | `ubuntu`| Not primary host for locator  |

SSH config on Windows (`C:\Users\kklas\.ssh\config`):

```ssh-config
Host piGateway
    HostName 192.168.1.100
    User pi
    IdentityFile ~/.ssh/id_ed25519

Host piSensors
    HostName 192.168.1.26
    User pi
    IdentityFile ~/.ssh/id_ed25519

Host piMonitor
    HostName 192.168.1.16
    User ubuntu
    IdentityFile ~/.ssh/id_ed25519
```

### Public access

| Item | Value |
|------|-------|
| DDNS provider | afraid.org (FreeDNS) |
| Hostname | `kklasmei.mooo.com` |
| Current A record | `74.215.40.180` (home ISP public IP) |
| Phone upload URL | `https://kklasmei.mooo.com/api/v1/...` |
| Web dashboard (LAN) | `http://192.168.1.26:8000/locator/` (new nginx path on existing port 8000) |
| Web dashboard (public, optional) | `https://kklasmei.mooo.com/locator/` (same nginx, port 443) |

### piSensors port audit (Jul 26, 2026)

**Port 8000 is in use** — not free. nginx already listens on `0.0.0.0:8000`:

| Path on :8000 | Backend | Service |
|---------------|---------|---------|
| `/gateway/` | `127.0.0.1:8001` | Pi Gateway UI |
| `/home-vpn/` | `127.0.0.1:8001` | Home VPN UI |
| `/` (default) | `127.0.0.1:8002` | Security Camera API |

Other ports on piSensors:

| Port | Listener | Service |
|------|----------|---------|
| 80 | nginx | Home Sensor Dashboard (SvelteKit + API on 8090) |
| 443 | *(not listening yet)* | **Available** for Let's Encrypt + public sites |
| 8080 | nginx | Network traffic site |
| 8888 | nginx | Security cameras (alternate) |

**Plan for Phone Locator:** Run FastAPI on a new localhost port (e.g. `127.0.0.1:8003`) and add a `/locator/` location block to the existing `pivpngateway` nginx config on port 8000. No new LAN port required.

### Port forwarding (router)

- External `443` → piSensors `443` (nginx terminates TLS)
- nginx routes by hostname and path to multiple backends — Phone Locator does not monopolize port 443

### Multi-site HTTPS on port 443 (future home lab sites)

**Yes — hosting Phone Locator on 443 does not block other websites.** nginx acts as a reverse proxy: one public port, many sites.

```text
Internet :443 → piSensors nginx
                    │
    ┌───────────────┼───────────────┬──────────────────┐
    ▼               ▼               ▼                  ▼
server_name:   kklasmei.mooo.com   site2.example.com   …
    │               │
    ├─ /api/v1/*  → phone-locator (127.0.0.1:8003)
    ├─ /locator/  → phone-locator dashboard
    ├─ /gateway/  → (optional) proxy to :8001
    └─ /          → other site or default
```

**How multiple sites work:**

| Method | Example | Use when |
|--------|---------|----------|
| **Hostname routing** (`server_name`) | `kklasmei.mooo.com` vs `cameras.mooo.com` | Different afraid.org subdomains — preferred for separate sites |
| **Path routing** (`location`) | `/locator/`, `/gateway/`, `/` | Same hostname, different apps — current piSensors pattern on :8000 |
| **Both** | `kklasmei.mooo.com/locator/` + `other.mooo.com` | Mix as needed |

Each `server_name` gets its own Let's Encrypt cert (or one cert with multiple SANs). Adding a new site later = new nginx `server {}` block + certbot run — no conflict with Phone Locator.

**Phone upload URL** stays at `https://kklasmei.mooo.com/api/v1/...` regardless of how many other sites share port 443.

### Development workflow

Follow the same pattern as `klasmeier-pi-gateway-ui`:

- Edit on Windows (Cursor) or via NFS from Pi5Desktop
- Deploy to piSensors via git + `deploy.sh`
- Android app built on PC, sideloaded to phone

---

## 6. Security

### HTTPS

Use **Let's Encrypt** (free, auto-renewed, trusted by Android and browsers). See [§14](#14-https-with-lets-encrypt).

Self-signed certificates are a fallback only; they require extra Android network-security configuration.

### API authentication

- Long random **Bearer token** generated at setup
- Phone sends `Authorization: Bearer <token>` on every request
- Token stored in app secure storage and server environment/config
- Reject requests with missing or invalid token (401)

### Web dashboard authentication

- HTTP Basic Auth (same pattern as `klasmeier-pi-gateway-ui`), or
- LAN-only access if preferred (phone still uses public HTTPS endpoint)

### Rate limiting

- Cap requests per device per minute to reduce abuse if port is scanned
- Log and reject repeated bad auth attempts

### Privacy

- All location data stays on piSensors
- No third-party analytics or cloud storage
- DDNS hostname is public; API must require auth

---

## 7. Data model

### Primary table: `location_points`

Every GPS/telemetry reading from the phone. **Two timestamps are required:**

| Column | Type | Source | Description |
|--------|------|--------|-------------|
| `id` | INTEGER PK | Server | Auto-increment |
| `device_id` | TEXT | Phone | Stable device identifier |
| `client_point_id` | TEXT UNIQUE | Phone | UUID per reading — idempotent uploads, dedup on retry |
| `latitude` | REAL | Phone | Required |
| `longitude` | REAL | Phone | Required |
| `accuracy_m` | REAL | Phone | Horizontal accuracy in meters |
| `altitude_m` | REAL | Phone | Optional |
| `speed_mps` | REAL | Phone | Speed in m/s |
| `bearing_deg` | REAL | Phone | Direction of travel |
| `location_provider` | TEXT | Phone | `gps`, `network`, `fused` |
| `activity` | TEXT | Phone | `still`, `walking`, `running`, `in_vehicle`, etc. |
| `battery_pct` | INTEGER | Phone | 0–100 |
| `battery_charging` | BOOLEAN | Phone | Plugged in? |
| `power_save_mode` | BOOLEAN | Phone | Battery saver active? |
| `network_type` | TEXT | Phone | `wifi`, `cellular`, `none` |
| `wifi_ssid` | TEXT | Phone | Optional; requires location permission on Android 10+ |
| `cell_signal_dbm` | INTEGER | Phone | Optional |
| `app_version` | TEXT | Phone | For debugging after updates |
| `upload_attempt` | INTEGER | Phone | 1 = first try, 2+ = retry |
| `queued_duration_sec` | INTEGER | Phone | Seconds between `recorded_at` and actual upload |
| `recorded_at` | TEXT | Phone | ISO 8601 UTC — **when the phone took the reading** |
| `received_at` | TEXT | Server | ISO 8601 UTC — **when piSensors stored the row** (default `NOW()`) |

**Indexes:**

```sql
CREATE INDEX idx_points_device_recorded ON location_points(device_id, recorded_at);
CREATE INDEX idx_points_device_received ON location_points(device_id, received_at);
```

**Why both timestamps:**

- Phone clock skew → `recorded_at` may be wrong; `received_at` is ground truth for arrival
- Offline batch flush → many old `recorded_at`, one `received_at` → identifies backlog sync
- Gap analysis → distinguish "phone stopped recording" vs "phone recorded but couldn't reach server"

### Derived tables (analytics)

Computed by server (batch job or on-demand). Not sent by phone.

#### `places`

Clustered locations where the user spends time.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | |
| `device_id` | TEXT | |
| `name` | TEXT | User-assigned label ("Home", "Work") — nullable until named |
| `center_lat` | REAL | Centroid of cluster |
| `center_lon` | REAL | |
| `radius_m` | REAL | Cluster radius |
| `first_seen_at` | TEXT | |
| `last_seen_at` | TEXT | |
| `visit_count` | INTEGER | |

#### `visits`

A continuous stay at a place.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | |
| `device_id` | TEXT | |
| `place_id` | INTEGER FK | Nullable if place not yet clustered |
| `started_at` | TEXT | First point in visit (`recorded_at`) |
| `ended_at` | TEXT | Last point in visit |
| `duration_sec` | INTEGER | Computed |
| `center_lat` | REAL | |
| `center_lon` | REAL | |

#### `travel_segments`

Movement between visits.

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER PK | |
| `device_id` | TEXT | |
| `from_visit_id` | INTEGER FK | Nullable |
| `to_visit_id` | INTEGER FK | Nullable |
| `started_at` | TEXT | |
| `ended_at` | TEXT | |
| `duration_sec` | INTEGER | |
| `distance_m` | REAL | Sum of point-to-point distances |
| `avg_speed_mps` | REAL | |

### Optional future columns

| Column | Description |
|--------|-------------|
| `pressure_hpa` | Barometric pressure — floor detection |
| `satellites_used` | GPS quality |
| `mock_location` | Detect spoofed GPS |

---

## 8. API design

Base URL (phone, external): `https://kklasmei.mooo.com`  
Base URL (LAN): `http://192.168.1.26:8000/locator` (path TBD during nginx setup)

All authenticated endpoints require `Authorization: Bearer <token>`.

### Endpoints

| Method | Path | Caller | Description |
|--------|------|--------|-------------|
| `POST` | `/api/v1/location/batch` | Phone | Upload 1–N location points |
| `GET` | `/api/v1/location/latest` | Web / App | Most recent point per device |
| `GET` | `/api/v1/location/history` | Web / App | Points in time range (`?from=&to=&device_id=`) |
| `GET` | `/api/v1/places` | Web / App | Clustered places |
| `PUT` | `/api/v1/places/{id}` | Web | Rename a place |
| `GET` | `/api/v1/visits` | Web / App | Visits in time range |
| `GET` | `/api/v1/travel` | Web / App | Travel segments in time range |
| `GET` | `/api/v1/stats/summary` | Web / App | Daily/weekly summary (time by place, travel time) |
| `GET` | `/api/v1/health` | Monitor | Uptime check (no auth, minimal response) |
| `DELETE` | `/api/v1/data/purge` | Web | Manual purge by date range or device (auth required) |

### Batch upload request

```json
{
  "device_id": "pixel-8-kklas",
  "points": [
    {
      "client_point_id": "550e8400-e29b-41d4-a716-446655440000",
      "latitude": 42.123456,
      "longitude": -83.123456,
      "accuracy_m": 12.5,
      "altitude_m": 250.0,
      "speed_mps": 0.0,
      "bearing_deg": null,
      "location_provider": "fused",
      "activity": "still",
      "battery_pct": 67,
      "battery_charging": false,
      "power_save_mode": false,
      "network_type": "wifi",
      "wifi_ssid": "HomeWiFi",
      "app_version": "1.0.0",
      "upload_attempt": 1,
      "queued_duration_sec": 0,
      "recorded_at": "2026-07-26T18:00:00Z"
    }
  ]
}
```

### Batch upload response

```json
{
  "accepted": 1,
  "duplicates": 0,
  "errors": []
}
```

- `client_point_id` uniqueness → safe retries; duplicates are counted, not rejected
- Server sets `received_at` at insert time

---

## 9. Android app

The Android app is **small, battery-conscious, and collection-first**. Its primary job is to reliably gather location + telemetry and push it to piSensors. Everything else is a lightweight glance — not a mirror of the web dashboard.

**Tech:** Kotlin, Jetpack Compose, Room (queue + cache only), WorkManager, Retrofit, Fused Location Provider, Activity Recognition API. Patterns aligned with `klasmeier-pi-gateway-ui` (foreground service, boot receiver, path monitor).

---

### 9.1 Design principles

| Principle | Meaning |
|-----------|---------|
| **Collect first** | Background service is the product; UI is secondary |
| **Minimal screens** | 4 screens + setup wizard — not a multi-page analytics app |
| **No local history** | Queue unsynced points only; delete after upload |
| **Stats from server** | Today/week summaries fetched from API and cached — not computed from raw GPS on phone |
| **Open web for depth** | Link to web dashboard for maps, charts, history, admin |
| **Honest status** | Surface problems clearly (queue backlog, auth fail, OS killed service) |
| **Low interaction** | After setup, user should rarely need to open the app |

**Division of labor:**

| Phone app | Web dashboard |
|-----------|---------------|
| Collect & send data | Store full history |
| Queue when offline | Maps, trails, heatmaps |
| Service health | Charts & rollups |
| Today's quick summary | Place naming, purge, export |
| Force sync / pause | Health deep-dive |

---

### 9.2 Screen map

```text
App (4 tabs + setup)
├── Setup wizard          First run only — permissions, URL, token, test
├── Status                Default home — is it working? (★ primary screen)
├── Today                 Light stats — cached summary from server
├── Log                   Recent upload events (success/fail)
└── Settings              Config, permissions, pause tracking
```

**Bottom navigation (3 tabs + settings gear):**

```text
┌────────────────────────────────────────────────┐
│  Phone Locator                          [⚙]   │
├────────────────────────────────────────────────┤
│                                                │
│              (screen content)                  │
│                                                │
├────────────────────────────────────────────────┤
│   [ Status ]      [ Today ]      [ Log ]       │
└────────────────────────────────────────────────┘
```

Settings opens from the gear icon (not a tab — rarely used).

---

### 9.3 Status screen (home)

**Purpose:** Answer "Is my phone being tracked and sent to the server?" in one glance.

#### Layout

```text
┌────────────────────────────────────────────────┐
│  ● ACTIVE                    [Pause tracking]  │
│  Collecting every 3 min                        │
├────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐     │
│  │ Last sent       │  │ Queue           │     │
│  │ 2 min ago ✓     │  │ 0 pending       │     │
│  └─────────────────┘  └─────────────────┘     │
│  ┌─────────────────┐  ┌─────────────────┐     │
│  │ Last reading    │  │ Upload success  │     │
│  │ 1 min ago       │  │ 98% (24h)       │     │
│  └─────────────────┘  └─────────────────┘     │
├────────────────────────────────────────────────┤
│  CURRENT LOCATION (read-only)                  │
│  Home · 42.123, -83.456 · ±8 m                │
│  Battery 67% · WiFi · Still                    │
│  [Open in Google Maps]                         │
├────────────────────────────────────────────────┤
│  ⚠ Setup needed (only if problem)              │
│  → Battery optimization not disabled           │
│  → Background location denied                  │
├────────────────────────────────────────────────┤
│  [ Sync now ]                                  │
│  Open dashboard →  (browser link when on LAN)  │
└────────────────────────────────────────────────┘
```

#### Status states

| State | Indicator | When |
|-------|-----------|------|
| **Active** | Green ● | Service running, queue draining normally |
| **Syncing** | Blue ⟳ | Upload in progress |
| **Paused** | Gray ○ | User paused tracking |
| **Warning** | Amber ⚠ | Queue >10, stale >15 min, or permission issue |
| **Error** | Red ✕ | Auth failed, service killed, no network 1h+ |

#### Status screen elements

| Element | Source | Notes |
|---------|--------|-------|
| Service state | Local | Foreground service alive? |
| Last sent | Local ops log | Last successful batch upload |
| Queue count | Local Room | Unsynced points |
| Last reading | Local | Last GPS fix taken (may be unsent) |
| Upload success % | Local | Rolling 24h success rate |
| Current location | Local latest fix | Text only — no in-app map |
| Battery / network / activity | Latest fix payload | |
| Problem banners | Local checks | Actionable — tap to fix (opens Settings or system dialog) |
| **Sync now** | Action | Collect fresh GPS, upload immediately, log result, show status feedback |
| **Pause tracking** | Action | Stops collection; notification updates |
| **Open dashboard** | Deep link | `http://192.168.1.26:8000/locator/` — works on home WiFi |

No charts on this screen. Cards only.

---

### 9.4 Today screen

**Purpose:** Light "how's my day going?" without duplicating the web reports.

Fetches `GET /api/v1/stats/summary?period=today` and `GET /api/v1/visits?from=today` on open (and after successful sync). Caches response in `summary_cache` table.

#### Layout

```text
┌────────────────────────────────────────────────┐
│  Today · Jul 26              Updated 2 min ago   │
├────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ Places   │ │ Travel   │ │ Stationary│       │
│  │ 3        │ │ 42 min   │ │ 5h 12m   │       │
│  └──────────┘ └──────────┘ └──────────┘       │
├────────────────────────────────────────────────┤
│  WHERE TODAY (top 3 — simple bars)             │
│  Home      ████████████  4h 12m                │
│  Work      ██████        2h 05m                │
│  Store     █             0h 28m                │
├────────────────────────────────────────────────┤
│  VISITS TODAY (compact list, max 8)            │
│  Home        8:12 am – 10:45 am   2h 33m      │
│  → Travel    10:45 am – 11:02 am   17m        │
│  Work        11:02 am – 5:30 pm   6h 28m      │
│  → Travel    5:30 pm – 5:52 pm     22m        │
│  Home        5:52 pm – now        ongoing     │
├────────────────────────────────────────────────┤
│  This week: 3 places · 6h travel   [See web →]│
└────────────────────────────────────────────────┘
```

#### Today screen rules

| Rule | Detail |
|------|--------|
| **Period** | Today only — no day/week/month/year picker on phone |
| **Offline** | Show cached data + "Last updated 3h ago" banner |
| **No map** | Text and simple bars only |
| **Visit list** | Max 8 rows; "See web for full timeline" if more |
| **Week teaser** | One line summary; tap opens web dashboard |
| **Pull to refresh** | Re-fetch from API |

This is the only analytics screen. Keep it scannable in <10 seconds.

---

### 9.5 Activity log

**Purpose:** Debug upload reliability — "did it send?" — not a GPS history browser.

#### Layout

```text
┌────────────────────────────────────────────────┐
│  Activity log                    [Clear old]   │
├────────────────────────────────────────────────┤
│  ✓ 2:47 pm  Sent 1 point                      │
│  ✓ 2:44 pm  Sent 1 point                      │
│  ✗ 2:41 pm  Failed — timeout (queued)         │
│  ✓ 2:38 pm  Sent 3 points (flush)             │
│  ✓ 2:35 pm  Sent 1 point                      │
│  …                                             │
│  (last 50 events, local only)                │
└────────────────────────────────────────────────┘
```

| Event type | Example |
|------------|---------|
| Send success | `Sent N points` |
| Send fail | `Failed — timeout` / `401 unauthorized` / `no network` |
| Queue flush | `Sent 47 points (offline catch-up)` |
| Collection | `Reading recorded` (optional, off by default — noisy) |
| Service | `Service started` / `Service stopped` / `Boot restart` |

Stored locally in a small `activity_log` table (max 50–100 rows, FIFO). Not synced to server.

---

### 9.6 Settings

**Purpose:** One-time setup and occasional maintenance. Not for daily use.

#### Sections

| Section | Fields / actions |
|---------|------------------|
| **Connection** | API URL, API token, Device ID, Test connection |
| **Collection** | Upload interval (3 / 5 / 10 min), Pause tracking toggle |
| **Permissions** | Status indicators + tap to fix: Location, Background location, Activity recognition, Battery optimization |
| **About** | App version, server health check, link to web dashboard |
| **Advanced** | View queue size, clear activity log, reset cache |

**Not in app settings:** place naming, data purge, token regenerate (web only).

#### Setup wizard (first run)

Shown once before main UI. Steps:

1. **Welcome** — explain foreground notification (required)
2. **Permissions** — location (foreground → background), activity recognition
3. **Battery** — prompt to disable optimization for this app
4. **Connection** — URL (default LAN or production), token (typed, debug pre-fill, or **Phase 9** QR scan), device ID
5. **Test** — POST test point, confirm success
6. **Done** — start foreground service

---

### 9.7 Persistent notification

Required for reliable background location. This is the UI most days — user never opens the app.

```text
┌────────────────────────────────────────────────┐
│  Phone Locator                                 │
│  Active · sent 2m ago · queue 0                │
└────────────────────────────────────────────────┘
```

| State | Notification text |
|-------|-------------------|
| Active | `Active · sent 2m ago · queue 0` |
| Syncing | `Syncing… · queue 12` |
| Paused | `Paused` |
| Warning | `⚠ Queue 23 · last sent 1h ago` |
| Error | `✕ Upload failed · tap to open` |

Tap notification → Status screen.

Optional: notification action buttons **Sync now** and **Pause**.

---

### 9.8 What the app does NOT include

Explicitly out of scope — use the web dashboard instead:

| Not in app | Why |
|------------|-----|
| Full-screen map / trail | Web does this better |
| Heatmaps | Web only |
| Reports (week/month/year) | Web only |
| Charts beyond 3 simple bars | Web only |
| Raw point history browser | Web only |
| Place rename / merge | Web only |
| Data purge | Web only |
| Multi-device management | Web only |
| Health deep-dive (lag histograms) | Web only |
| Export CSV/JSON | Web only |

---

### 9.9 Core behavior (background)

| Feature | Description |
|---------|-------------|
| **Periodic collection** | ~every 3 minutes (configurable in Settings) |
| **Foreground service** | Persistent notification — required for reliable background location |
| **Boot receiver** | Restart service after phone reboot |
| **Battery exemption** | Prompt user to disable battery optimization (setup wizard + Settings) |
| **Local upload queue** | Buffer unsynced readings only; delete after successful upload |
| **No full local history** | Full data lives on piSensors |
| **Batch upload** | Send up to 50 queued points per request |
| **Retry with backoff** | On failure, keep in queue and retry |
| **WorkManager backup** | Secondary flush trigger if foreground service is killed |
| **Network monitor** | Flush queue immediately on WiFi/cellular reconnect |

### Permissions

- `ACCESS_FINE_LOCATION`
- `ACCESS_COARSE_LOCATION`
- `ACCESS_BACKGROUND_LOCATION`
- `INTERNET`
- `ACCESS_NETWORK_STATE`
- `FOREGROUND_SERVICE`
- `FOREGROUND_SERVICE_LOCATION`
- `RECEIVE_BOOT_COMPLETED`
- `ACTIVITY_RECOGNITION` (for activity type)
- `REQUEST_IGNORE_BATTERY_OPTIMIZATIONS` (prompt only)

### Local storage (Room)

| Table | Purpose | Retention |
|-------|---------|-----------|
| `upload_queue` | Unsynced points | Until uploaded |
| `summary_cache` | API responses (today, week teaser) | Until refreshed; small |
| `activity_log` | Upload events | Last 50–100 rows, FIFO |
| `ops_counters` | 24h success rate, last sent timestamps | Rolling |
| `known_wifi_places` | *(Phase 8)* SSID → learned lat/lon | Until user deletes or re-learns |

### API calls from app

| Call | When |
|------|------|
| `POST /api/v1/location/batch` | Every collection cycle + sync now + queue flush |
| `GET /api/v1/stats/summary?period=today` | Today screen open, after successful sync |
| `GET /api/v1/stats/summary?period=week` | Today screen — one-line teaser only |
| `GET /api/v1/visits?from=today` | Today screen |
| `GET /api/v1/location/latest` | Optional — verify server has latest after sync |
| `GET /api/v1/health` | Settings → test connection |

### Adaptive interval (future — Phase 7)

- 3 min when moving
- 10–15 min when stationary (same cluster for >15 min)
- Reduces battery and data volume without losing place detection accuracy

### 9.11 Known Wi-Fi places (future — Phase 8)

**Motivation:** GPS is the dominant battery cost per collection cycle. When the phone is on a **known Wi-Fi network** (e.g. home SSID `ZNet`), the app can skip the GPS radio and send a **learned fixed location** for that network instead.

**Already in place (Phase 2):** each upload includes `network_type` and optional `wifi_ssid` (requires location permission on Android 10+). This phase adds *behavior* on top of that data.

#### Concept

```text
Learning (first visits on ZNet):
  → collect GPS as today (several good fixes)
  → store mapping: SSID "ZNet" → (lat, lon, accuracy, learned_at)

Routine (later visits on ZNet):
  → detect connected Wi-Fi SSID matches known entry
  → skip GPS; enqueue point with learned coordinates + wifi_ssid
  → set location_provider = "wifi_known" (or similar) for analytics

Away from known Wi-Fi:
  → fall back to normal GPS collection (unchanged)
```

#### Expected battery impact

| Scenario | GPS every 3 min | Known Wi-Fi shortcut |
|----------|-----------------|----------------------|
| At home on ZNet (~16 h/day) | Full GPS wake each cycle | Wi-Fi/SSID check only |
| Away / cellular | Full GPS | Full GPS (unchanged) |

Rough expectation: **meaningful savings during long stationary home periods** (often 30–50% less location-related drain while at home). Exact savings depend on interval, OEM, and how much time is spent on known networks.

#### Learning modes (to align in design)

| Mode | Description |
|------|-------------|
| **Auto-learn** | After *N* GPS fixes on the same SSID within *M* days, compute centroid (or best-accuracy fix) and enable shortcut |
| **User-labeled** | Settings UI: "ZNet = Home" — confirm or override learned coordinates |
| **Server hint** *(optional)* | Phase 5 place clusters where `wifi_ssid` is dominant → suggest name/coords to app |

#### Local storage (`known_wifi_places`)

| Column | Type | Notes |
|--------|------|-------|
| `ssid` | TEXT PK | Normalized SSID (e.g. `ZNet`) |
| `latitude` | REAL | Learned |
| `longitude` | REAL | Learned |
| `accuracy_m` | REAL | Typical accuracy when learned |
| `label` | TEXT | Optional user name ("Home") |
| `learned_at` | TEXT ISO | When mapping was created/updated |
| `sample_count` | INTEGER | Fixes used for learning |
| `enabled` | BOOLEAN | User can disable per network |

#### Edge cases (open — see §17 O9)

- **Duplicate SSIDs** — same SSID name at a different physical location (friend's router, ISP default)
- **`<unknown ssid>`** — Android privacy restriction; must fall back to GPS
- **VPN / captive portal** — connected to Wi-Fi but not truly "at" that place (rare for home)
- **In-home movement** — single point per SSID is enough for "phone is at home"; not room-level
- **Re-learn** — user moves home router or coordinates drift; manual reset or periodic re-sample

#### Relationship to other phases

| Phase | Role |
|-------|------|
| **5 Analytics** | Server may infer SSID ↔ place from history; can feed suggestions |
| **7 Polish** | Adaptive interval complements Wi-Fi shortcut (slower GPS when stationary, no GPS when on known Wi-Fi) |
| **8 Known Wi-Fi** | This feature — phone-side SSID map and GPS skip logic |

#### Android build order (Phase 8)

| Step | Deliverable |
|------|-------------|
| B1 | Room `known_wifi_places` + DAO |
| B2 | Learning logic after GPS collect (auto-learn threshold) |
| B3 | Collection path: SSID match → skip GPS, use cached coords |
| B4 | Settings UI — list known networks, rename, disable, forget, re-learn |
| B5 | Activity log entries when shortcut used vs GPS |
| B6 | Unit tests for matching, learning threshold, fallback |

### Android build order

| Step | Status | Deliverable |
|------|--------|-------------|
| A1 | ✅ | Project scaffold, Room, Retrofit, permissions |
| A2 | ✅ | Foreground service + collection + upload queue |
| A3 | ✅ | Setup wizard + Settings |
| A4 | ✅ | Status screen + notification |
| A5 | ✅ | Activity log |
| A6 | ⬜ | Today screen (API cache) |
| A7 | ⬜ | Resizable home screen widget |

### 9.10 Home screen widget

A **resizable Glance widget** (same stack as `klasmeier-pi-gateway-ui` `PathWidget`) gives at-a-glance status without opening the app.

**Tap behavior:** Tapping **anywhere** on the widget opens the app to the **Status** screen. If setup is incomplete, tap opens the **setup wizard** instead. The entire widget surface is clickable — no dead zones.

**Design goals:** Works at **1×2** and **2×1** (smallest footprints) and scales up responsively. Reads from **local ops snapshot only** — no API calls from the widget (battery-friendly, works offline).

#### Widget provider sizing

```xml
android:targetCellWidth="2"
android:targetCellHeight="1"
android:minResizeWidth="57dp"      <!-- ~1 cell wide -->
android:minResizeHeight="48dp"     <!-- ~1 cell tall -->
android:maxResizeWidth="320dp"
android:maxResizeHeight="400dp"
android:resizeMode="horizontal|vertical"
android:updatePeriodMillis="0"   <!-- push updates from app only -->
```

`minResizeWidth` + `minResizeHeight` at one cell each allows the user to place or resize to **either** minimum shape:

| Minimum shape | Grid | Orientation |
|---------------|------|-------------|
| **2×1** | 2 wide × 1 tall | Horizontal strip (default target) |
| **1×2** | 1 wide × 2 tall | Vertical strip |

User can then resize wider, taller, or both on supported launchers.

**Implementation:** `GlanceModifier.clickable(actionStartActivity<MainActivity>())` on the root container at every size tier (same as gateway `PathWidget`).

#### Responsive layouts (by `LocalSize.current`)

Use width/height breakpoints to pick a layout — same pattern as gateway `PathWidget`:

| Size tier | Approx grid | Layout |
|-----------|-------------|--------|
| **Compact vertical** | 1×2, 1×3 | Vertical stack — status dot + state + last sent |
| **Compact horizontal** | 2×1 | Single row — dot + Active + last sent |
| **Narrow** | 2×2 | Status + current place name |
| **Medium** | 2×3, 3×2, 4×2 | Status row + place + battery/network + queue |
| **Expanded** | 3×3, 4×3, 4×4 | All medium content + top place today + visit count |

Breakpoint hint: if `width < height` and narrow → vertical compact; if `height < width` and short → horizontal compact (2×1).

#### Layout wireframes

**2×1 — Compact horizontal (default target)**

```text
┌────────────────────────┐
│ ● Active · 2m ago    │  tap → opens app
└────────────────────────┘
```

**1×2 — Compact vertical**

```text
┌──────┐
│  ●   │  green/amber/red dot
│Active│  tap → opens app
│2m ago│
└──────┘
```

**2×2 — Narrow**

```text
┌─────────────┐
│ ● Active    │
│ Home        │
│ sent 2m ago │
└─────────────┘
```

**4×2 — Medium (horizontal)**

```text
┌──────────────────────────────┐
│ ● Active    Home    2m ago   │
│ 67% · WiFi · queue 0         │
└──────────────────────────────┘
```

**4×4 — Expanded**

```text
┌──────────────────────────────┐
│ ● Active          2m ago     │
│ Home · ±8 m                │
│ 67% · WiFi · queue 0        │
├──────────────────────────────┤
│ Today: 3 places · 42m travel│
│ Home ████████  4h 12m        │
│ Work ████      2h 05m        │
└──────────────────────────────┘
```

At expanded sizes, **today summary** comes from `summary_cache` (same cache as Today screen) — still no live API call in the widget.

#### Widget content by field

| Field | 2×1 | 1×2 | Narrow | Medium | Expanded |
|-------|-----|-----|--------|--------|----------|
| Status dot + label | ✓ | ✓ | ✓ | ✓ | ✓ |
| Last sent | ✓ | ✓ | ✓ | ✓ | ✓ |
| Current place | | | ✓ | ✓ | ✓ |
| Battery / network | | | | ✓ | ✓ |
| Queue (if >0 or warning) | dot color | dot color | | ✓ | ✓ |
| Today: place count / travel | | | | | ✓ |
| Top 1–2 places (bars) | | | | | ✓ |

**Warning state:** Amber/red dot surfaces even at 2×1 and 1×2 — user sees trouble without resizing.

**Not in widget:** Map, charts, full visit list, inline buttons. **Tap widget → open app** for sync, settings, and full detail.

#### Data source

`WidgetRepository.widgetSnapshot()` reads from local storage:

| Field | Source |
|-------|--------|
| `serviceState` | Foreground service |
| `lastSentAt` | `ops_counters` |
| `queueCount` | `upload_queue` count |
| `currentPlace` | Latest reading or cached summary place name |
| `batteryPct`, `networkType` | Latest reading |
| `todayPlaces`, `todayTravel`, `topPlaces` | `summary_cache` (expanded only; omit if stale/missing) |

#### When widget updates

Push refresh from app (not periodic OS polling):

| Event | Update widget |
|-------|---------------|
| Successful upload | Yes |
| Failed upload (queue growing) | Yes |
| Service start / stop / pause | Yes |
| Today cache refreshed | Yes (expanded layout) |
| Boot | Yes |

Use `WidgetUpdater.updateAll()` after these events (same as gateway app).

#### Setup state

If app not configured: show **"Tap to set up"** at all sizes; tap opens setup wizard (matches gateway widget pattern).

---

## 10. Web dashboard

The web dashboard is the **primary place for rich analysis**. The phone app shows a quick operational glance; the website holds maps, history, charts, rollups, and admin tools.

**URL base:** `http://192.168.1.26:8000/locator/` (LAN) · `https://kklasmei.mooo.com/locator/` (optional public, auth required)

**Tech:** HTML/CSS/JS (or lightweight framework), **Leaflet** + OpenStreetMap, **Chart.js** (or similar) for charts. Served by FastAPI on `127.0.0.1:8003`, proxied by nginx.

**Access:** LAN primary; home VPN optional. HTTP Basic Auth on all pages.

---

### 10.1 Site map

```text
/locator/
├── /                          Home — map + dashboard cards (default landing)
├── /map                       Full-screen map + trail controls
├── /timeline                  Day timeline (visits + travel segments)
├── /places                    All places (named + unnamed clusters)
│   └── /places/:id            Place detail — visits, time chart, mini map
├── /travel                    Travel log — segments, routes, stats
├── /reports                   Charts hub — rollups by day/week/month/year
│   ├── /reports/time          Where time is spent (stacked bar, donut)
│   ├── /reports/travel        Travel distance, duration, frequency
│   └── /reports/trends        Long-term trends over months/years
├── /history                   Raw point browser + export
├── /health                    Upload gaps, lag, battery, connectivity
└── /settings                  Place names, purge data, device config
```

**Top navigation (persistent on every page):**

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  📍 Phone Locator    [Home] [Map] [Timeline] [Places] [Travel] [Reports] │
│                      [History] [Health] [Settings]                       │
│                                                                          │
│  Device: [Pixel 8 ▼]     Period: [Today ▼] [Day|Week|Month|Year|Custom] │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### 10.2 Global UI patterns

These controls appear in the header (or a sticky bar) and apply across pages unless a page overrides them.

#### Device selector

- Dropdown when multiple phones are registered
- v1: single device, hidden or disabled

#### Period selector

| Preset | Range | Used for |
|--------|-------|----------|
| **Today** | Midnight → now (local TZ) | Default on Home |
| **Yesterday** | Full previous calendar day | |
| **This week** | Mon–Sun (or Sun–Sat, configurable) | |
| **This month** | 1st → now | |
| **This year** | Jan 1 → now | |
| **Custom** | Date picker start + end | Reports, History |

Period selection drives cards, map trail, charts, and tables on every page.

#### Status banner (conditional)

Shown when something needs attention:

| Condition | Banner |
|-----------|--------|
| No update in >10 min | ⚠️ **Stale** — last seen 23 min ago |
| Gap in `recorded_at` >30 min (phone was offline) | ℹ️ **Data gap** — 2h 15m with no readings (Jul 25, 3:00–5:15 pm) |
| Upload lag high | ℹ️ **Sync delay** — average 45 min between recorded and received |

---

### 10.3 Home dashboard

**Purpose:** Answer "where is my phone right now?" and "what's the day looking like?" in under 5 seconds.

#### Layout

```text
┌─────────────────────────────────────────────────────────────────────────┐
│  [Status banner if stale / gap]                                         │
├─────────────────────────────────────────────────────────────────────────┤
│  DASHBOARD CARDS (row of 4–6)                                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐     │
│  │ Last seen   │ │ Current     │ │ Battery     │ │ Today at    │     │
│  │ 2 min ago   │ │ place       │ │ 67%         │ │ places: 3   │     │
│  │ 2:47 pm     │ │ Home        │ │ not charging│ │             │     │
│  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘     │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                       │
│  │ Travel today│ │ Stationary  │ │ Accuracy    │                       │
│  │ 42 min      │ │ 5h 12m      │ │ ±8 m        │                       │
│  └─────────────┘ └─────────────┘ └─────────────┘                       │
├─────────────────────────────────────────────────────────────────────────┤
│  MAP (60–70% of viewport height)                                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  • Pin = latest location + accuracy circle                        │  │
│  │  • Polyline = today's trail (or selected period)                  │  │
│  │  • Markers at named places visited today                          │  │
│  │  • [Fit trail] [Satellite] [Heat overlay toggle]                  │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│  TODAY AT A GLANCE (compact row below map)                              │
│  ┌──────────────────────────────┐  ┌──────────────────────────────┐    │
│  │ Mini timeline (horizontal)   │  │ Top 3 places today (bars)    │    │
│  │ ████░░░░████░░░░░░████████   │  │ Home      ████████  4h 12m   │    │
│  │ 8am    12pm    4pm    8pm    │  │ Work      ████      2h 05m   │    │
│  └──────────────────────────────┘  │ Store     █         0h 28m   │    │
│                                     └──────────────────────────────┘    │
│  [View full timeline →]  [View reports →]                               │
└─────────────────────────────────────────────────────────────────────────┘
```

#### Dashboard cards (detail)

| Card | Primary value | Subtext | Click → |
|------|---------------|---------|---------|
| **Last seen** | Relative time ("2 min ago") | Absolute timestamp, network type | `/health` |
| **Current place** | Named place or "Traveling" / "Unknown" | Address reverse-geocode (optional) | `/places/:id` or `/map` |
| **Battery** | Percentage | Charging yes/no, trend if dropping fast | `/health` |
| **Places today** | Count of distinct places | vs yesterday (+1) | `/places?period=today` |
| **Travel today** | Total travel duration | Distance (mi/km) | `/travel?period=today` |
| **Stationary today** | Time at places (not moving) | % of day so far | `/reports/time?period=today` |
| **Accuracy** | Latest fix accuracy | GPS / network / fused | `/history?latest` |

Cards use color hints: green = fresh & healthy, amber = stale or gap, red = no data in 24h+.

---

### 10.4 Subpages

Each subpage goes deeper on one topic. All respect the global **Device** and **Period** selectors.

#### `/map` — Full-screen map

| Element | Description |
|---------|-------------|
| **Map** | Full viewport; pan, zoom, satellite toggle |
| **Layers** | Trail, heatmap, place markers, travel segment arrows |
| **Trail controls** | Show/hide trail, color by speed or time, animate playback |
| **Point popup** | Click any point on trail → time, accuracy, battery, speed |
| **Sidebar** | List of visits in period; click to zoom map to that visit |
| **Export** | Download trail as GPX/GeoJSON |

#### `/timeline` — Day view

Horizontal or vertical timeline for the selected period (best for single day; week view collapses to day strips).

```text
Jul 26, 2026
────────────────────────────────────────────────────────
08:12 ──████ Home ────────────────────────── 10:45  (2h 33m)
10:45 ──▶▶ travel ────────────────────────── 11:02  (17m, 4.2 mi)
11:02 ──████ Work ────────────────────────── 17:30  (6h 28m)
17:30 ──▶▶ travel ────────────────────────── 17:52  (22m, 5.1 mi)
17:52 ──████ Home ────────────────────────── now    (ongoing)
```

- Click a segment → detail panel (distance, avg speed, points count)
- Filter: show travel only / places only

#### `/places` — Places list

| Column | Content |
|--------|---------|
| Name | User label or "Unnamed cluster #12" |
| Total time | In selected period |
| Visits | Count |
| Last visit | Date/time |
| Actions | Rename, merge, hide |

Sort by: time spent, visit count, last visit, name.

**`/places/:id` — Place detail**

- Mini map centered on place with radius circle
- Visit history table for this place
- Chart: time spent here by day/week/month (bar chart)
- Edit name, adjust radius (advanced)

#### `/travel` — Travel log

Table of travel segments in period:

| From | To | Started | Duration | Distance | Avg speed |
|------|-----|---------|----------|----------|-----------|
| Home | Work | 10:45 am | 17 min | 4.2 mi | 24 mph |
| Work | Home | 5:30 pm | 22 min | 5.1 mi | 22 mph |

- Click row → map shows route polyline for that segment
- Summary cards: total travel time, total distance, longest trip, most frequent route

#### `/history` — Raw data browser

- Paginated table of `location_points` (recorded_at, received_at, lat, lon, accuracy, battery, …)
- Filters: date range, gap detection, min accuracy
- Export CSV / JSON for selected range
- Admin: link to purge (with confirmation)

#### `/health` — System health

For debugging reliability (why Google fails vs why this works):

| Panel | Content |
|-------|---------|
| **Upload timeline** | Success/fail dots over 24h |
| **Gaps** | List of gaps in `recorded_at` with duration |
| **Receive lag** | Histogram: `received_at − recorded_at` |
| **Battery at gap** | Was phone dead or app stopped? |
| **Network** | WiFi vs cellular breakdown |
| **Power save** | Correlation with power_save_mode flag |

#### `/settings` — Admin

- API token display/regenerate (careful)
- Device list
- Place management bulk tools
- **Purge data** by date range or device (with confirmation)
- Default timezone, distance units (mi/km)

---

### 10.5 Reports, aggregates, and self-healing

**Purpose:** Rich all-time and period statistics live on **`/reports`**, not Home. Home stays operational (“where is my phone, how’s today?”). Reports answers “how have I spent my time over weeks, months, and all time?”

#### Data volume assumptions

| Layer | Scale (~3 min uploads) | Used for |
|-------|------------------------|----------|
| `location_points` | ~175k rows/year | Raw trail, heatmap binning, analytics **recompute only** |
| `visits` | ~2k–7k rows/year | Time-at-place, place rankings |
| `travel_segments` | ~1k–5k rows/year | Travel time, distance, trip counts |
| `places` | tens–low hundreds | Named clusters, place metadata |

Lifetime and period **reports never scan all raw GPS points** on page load. They aggregate `visits`, `travel_segments`, and `places` via SQL (`SUM`, `COUNT`, `GROUP BY`). Map/history APIs may sample `location_points` for display.

#### Three-tier aggregation strategy

| Tier | What | When | Used by |
|------|------|------|---------|
| **1 — SQL on derived tables** | Ad-hoc `SUM`/`GROUP BY` on visits/travels | Any API read | Period summaries, place rankings |
| **2 — Cached lifetime snapshot** | One JSON blob per device in `analytics_meta` | Updated on analytics recompute | `/reports` all-time band (instant read) |
| **3 — Daily rollup table** (`daily_stats`) | One row per device per calendar day | Future: built on recompute | `/reports/trends`, monthly charts |

**v1 ships Tier 1 + 2.** Tier 3 is planned when trend charts need monthly buckets without scanning visits.

#### Cached lifetime stats (Tier 2)

Stored in `analytics_meta`:

- `lifetime_stats_json` — totals, top places, tracking span
- `lifetime_stats_point_at` — `recorded_at` of latest point when cache was built (invalidation key)

**Contents (all time):**

- `first_point_at`, `last_point_at`, `days_with_data`, `point_count`
- `places_count`, `visits_count`, `travel_trips`
- `stationary_duration_sec`, `travel_duration_sec`, `travel_distance_m`
- `top_places` — top 10 by duration `[{ place_id, name, duration_sec }]`
- `top_place` — #1 place + share of stationary time (optional)

#### Self-healing behavior

Aggregates must recover automatically — no manual “rebuild stats” step required.

| Trigger | Action |
|---------|--------|
| New location upload | `ensure_computed()` → full analytics recompute if stale → **refresh lifetime cache** |
| `GET /api/v1/stats/lifetime` or `/stats/reports` | `ensure_lifetime_stats()` — if cache missing or `lifetime_stats_point_at ≠ latest point`, rebuild from derived tables |
| Server restart | Same as above on first read; no background daemon required |
| DB migration / new column | `init_db()` migrations add columns; first read rebuilds cache |

**Invariant:** If visits/travels are up to date with `location_points`, lifetime cache can always be rebuilt deterministically from SQL aggregates.

**Future:** Optional nightly `daily_stats` backfill job; if interrupted, next recompute or first reports read fills gaps (same self-heal pattern).

#### Reports page layout (`/reports`)

```text
┌─────────────────────────────────────────────────────────────┐
│  [ Lifetime | This period ]   ← subnav tabs (one visible)   │
├─────────────────────────────────────────────────────────────┤
│  Active tab content (cards + top places)                    │
│  Period tab shows current period label; period bar above    │
│  controls range. Tab choice persists when changing period.    │
└─────────────────────────────────────────────────────────────┘
```

Home may link “View reports →” but does **not** show lifetime stats.

#### Geographic heatmap (separate from lifetime numbers)

- **Map page** layer toggle — not the Reports hub
- Server **grid bins** (~50 m cells) refreshed on recompute; browser loads ~500–2k cells, not 175k points
- Planned after Reports v1

#### Build order (reports track)

| Step | Deliverable | Status |
|------|-------------|--------|
| R1 | Lifetime SQL + cached snapshot + self-heal + `GET /stats/lifetime`, `/stats/reports` | **v1.9.12** |
| R2 | `/reports` hub UI (all-time band + period section) | **v1.9.12** |
| R3 | Travel sections on Reports (routes + trip tables) | **v1.9.15** |
| R4 | Map heatmap layer + grid bin table | Planned |
| R5 | `daily_stats` + `/reports/trends` | Planned |
| R6 | `/reports/travel` charts + temporal heatmap | Planned |

---

### 10.6 Charts and rollups

**`/reports`** is the charts hub. Subpages organize by question type. All charts support **Day / Week / Month / Year** rollup via the period selector or dedicated granularity toggle.

#### `/reports` — Hub landing

Summary cards + links to sub-reports:

| Card | Chart preview | Link |
|------|---------------|------|
| Time by place | Donut (today) | `/reports/time` |
| Travel summary | Bar (this week) | `/reports/travel` |
| Long-term trend | Sparkline (90 days) | `/reports/trends` |

#### `/reports/time` — Where time is spent

**Question:** "Where am I spending my time?"

| Chart | Type | Rollups |
|-------|------|---------|
| **Time by place** | Horizontal bar or donut | Day, week, month, year |
| **Stacked time** | Stacked bar — place vs travel vs unknown | Week, month |
| **Place ranking** | Table + bar — top N places | Any period |
| **Time at place over time** | Line or stacked area — one line per top place | Month, year |

Example — **week rollup:**

```text
Time by place (Jul 20–26)
Home     ████████████████████  52h
Work     ████████████          31h
Gym      ██                     4h
Travel   ████                   8h
Other    █                      2h
```

#### `/reports/travel` — Travel analysis

**Question:** "Where do I travel to, and how much time do I spend traveling?"

| Chart | Type | Rollups |
|-------|------|---------|
| **Travel time** | Bar per day/week/month | Day → year |
| **Travel distance** | Bar per day/week/month | Day → year |
| **Trips count** | Bar — number of segments | Day → year |
| **Route frequency** | Table — Home→Work: 12 trips, avg 18 min | Week, month, year |
| **Travel by hour** | Heatmap — when you travel most (day of week × hour) | Month, year |
| **Avg trip duration** | Line trend | Month, year |

#### `/reports/trends` — Long-term patterns

**Question:** "How are my habits changing over months/years?"

| Chart | Type | Rollups |
|-------|------|---------|
| **Monthly place time** | Stacked area — top 5 places per month | Year, multi-year |
| **Travel % of day** | Line — travel time / waking hours | Month, year |
| **Places visited count** | Line — distinct places per week/month | Month, year |
| **First time at place** | Timeline — when new clusters first appeared | All time |
| **Year comparison** | Side-by-side bars — 2025 vs 2026 same month | Year |

#### Rollup behavior

| Granularity | X-axis buckets | Example |
|-------------|----------------|---------|
| **Day** | Hours (or visits) | Jul 26: time per place per hour |
| **Week** | Days (Mon–Sun) | Jul 20–26: time per place per day |
| **Month** | Days or weeks | July 2026: time per place per week |
| **Year** | Months | 2026: time per place per month |
| **Custom** | Auto-pick bucket size based on range length | 3 days → hourly; 90 days → weekly |

#### Chart interactions (all report pages)

- Hover → exact duration, percentage, visit count
- Click place in legend → filter all charts to that place
- Click bar → drill down (year → month → week → day)
- Download chart as PNG; underlying data as CSV

---

### 10.7 API endpoints needed by web UI

Extends [§8](#8-api-design):

| Method | Path | Used by |
|--------|------|---------|
| `GET` | `/api/v1/stats/dashboard` | Home cards (single call) |
| `GET` | `/api/v1/stats/reports` | Reports hub (lifetime + period summary) |
| `GET` | `/api/v1/stats/lifetime` | All-time stats only (cached, self-healing) |
| `GET` | `/api/v1/stats/summary?period=&granularity=` | Reports, mini charts |
| `GET` | `/api/v1/stats/travel?period=&granularity=` | Travel reports |
| `GET` | `/api/v1/stats/trends?from=&to=&granularity=` | Long-term trends |
| `GET` | `/api/v1/location/trail?from=&to=` | Map polyline (simplified points) |
| `GET` | `/api/v1/health/gaps?from=&to=` | Health page, status banner |
| `GET` | `/api/v1/health/upload-stats?from=&to=` | Health page |

---

### 10.8 Responsive layout

| Viewport | Behavior |
|----------|----------|
| **Desktop** | Cards row + large map; sidebar on subpages |
| **Tablet** | Cards wrap 2×3; map below |
| **Mobile** | Cards stack; map full width; nav collapses to hamburger |

Primary use is desktop/tablet at home — mobile web is secondary.

---

### 10.9 Build order (web)

| Step | Pages |
|------|-------|
| W1 | Home (cards + map + today mini chart) |
| W2 | `/map` full-screen, `/timeline` |
| W3 | `/places` list + detail |
| W4 | `/travel` |
| W5 | `/reports` hub (lifetime + period) — **R1/R2 shipped v1.9.12** |
| W5b | `/reports/time` and `/reports/travel` |
| W6 | `/reports/trends`, `/health`, `/history`, `/settings` |

### Map stack

- **Leaflet** + **OpenStreetMap** tiles (no API key required)
- Optional: Esri satellite layer toggle

### Access

- Primary: LAN browser at `http://192.168.1.26:8000/locator/`
- Optional: `https://kklasmei.mooo.com/locator/` via home VPN or public with auth
- HTTP Basic Auth on all pages (same pattern as gateway UI)

---

## 11. Analytics engine

Runs on piSensors against full `location_points` history.

### Place detection (v1 algorithm)

1. Sort points by `recorded_at` for a device
2. If distance from previous point < **~100 m** and speed < **~1 m/s** → same place
3. If distance jumps or speed high → traveling segment
4. Merge consecutive same-place readings into a **visit**
5. Periodically cluster visit centroids into named **places**

Constants (100 m, 1 m/s) should be configurable.

### Computed outputs

- `places` — clustered centroids with visit counts
- `visits` — time ranges at a place
- `travel_segments` — between visits with distance and duration
- Summary stats: total travel time, total stationary time, top N places by duration

### Execution

- **On ingest** (light): update "latest" caches only
- **Scheduled job** (e.g. nightly): recompute visits/places for new data
- **On demand** (web): recompute for selected date range

Phone app calls `/api/v1/stats/summary`, `/api/v1/places`, and `/api/v1/visits` (limited window) and caches results locally. Server is the sole source of truth for analytics.

---

## 12. Offline queue and data integrity

```text
Get location
    → Write to upload queue (local SQLite — unsynced only)
    → Network up?
        Yes → POST batch to API
            Success → Delete from queue (data now lives on piSensors only)
            Fail  → Keep in queue, exponential backoff
        No  → Keep in queue, retry when connectivity changes
```

**No long-term local history.** The queue is a temporary buffer for points not yet accepted by the server. Once uploaded, rows are removed from the phone. There is no second copy of the full dataset on the device.

### Phone local storage (two tables)

#### `upload_queue` — unsynced points only

| Column | Description |
|--------|-------------|
| `client_point_id` | UUID — matches server dedup key |
| `payload_json` | Full point JSON |
| `recorded_at` | For ordering |
| `sync_attempts` | Retry count |

Rows deleted on successful upload.

#### `summary_cache` — aggregated API responses

| Column | Description |
|--------|-------------|
| `cache_key` | e.g. `summary:day`, `visits:7d`, `latest` |
| `payload_json` | API response blob |
| `fetched_at` | When last refreshed from server |
| `expires_at` | Optional TTL for stale indicator |

Small, bounded storage — refreshed when app opens or on successful upload.

### Triggers to flush queue

1. Foreground service timer (every collection cycle)
2. WorkManager periodic task
3. `NetworkChangeMonitor` — on WiFi/cellular reconnect
4. Boot receiver — after restart

### Idempotency

- Every point has unique `client_point_id`
- Server `INSERT OR IGNORE` (or equivalent) on `client_point_id`
- Retries never create duplicate rows

---

## 13. Data retention

| Policy | Value |
|--------|-------|
| Automatic deletion | **None** — keep all data forever |
| Manual purge | Admin endpoint + web UI (by date range, device, or all) |
| Storage estimate | ~480 points/day × ~500 bytes ≈ 240 KB/day ≈ 88 MB/year per phone — negligible on Pi |

---

## 14. HTTPS with Let's Encrypt

**Let's Encrypt** provides free TLS certificates, trusted by Android and browsers, renewed automatically every ~90 days.

### What we need

1. **Public hostname** pointing at home IP — `kklasmei.mooo.com` (afraid.org) ✓
2. **Port 443** forwarded from router to piSensors (port is currently **free** on piSensors)
3. **ACME client** on piSensors — **certbot** (with nginx plugin) or **Caddy** (automatic HTTPS)

### What is Let's Encrypt? (quick primer)

- A free certificate authority — no purchase, no annual fee
- Certificates are domain-validated (proves you control `kklasmei.mooo.com`)
- **certbot** talks to Let's Encrypt, proves ownership (HTTP challenge on port 80 or TLS on 443), installs the cert into nginx
- Auto-renews every ~60–90 days via a systemd timer
- Android and browsers trust it natively — no special app config

### High-level setup (during Phase 3/4)

```text
1. Install certbot on piSensors
2. Add nginx server block listening on 443 for kklasmei.mooo.com
       → proxy /api/v1/* and /locator/ to 127.0.0.1:8003
3. Run certbot --nginx -d kklasmei.mooo.com
4. Certbot installs cert and sets up auto-renewal (systemd timer)
5. Android app uses https://kklasmei.mooo.com — no extra cert config needed
6. Later: add more server_name blocks + certbot -d other.mooo.com for additional sites
```

### Renewal

- Certbot timer renews before expiry; nginx reloads automatically
- Monitor via piMonitor or a simple cron health check

### Fallback: self-signed

Only if Let's Encrypt is blocked (ISP port 80/443 filtering, etc.). Requires Android `network_security_config` to trust the cert. Not planned for v1.

---

## 15. Repository layout

```text
andriod-PhoneLocator/
├── PROJECT.md              # This document
├── DEPLOY.md               # Deploy steps (written during Phase 1)
├── android/                # Kotlin app
│   ├── app/
│   └── README.md
├── server/                 # FastAPI + SQLite
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── routes/
│   │   └── analytics/
│   ├── deploy/
│   │   ├── deploy.sh
│   │   ├── nginx-locator.conf.snippet
│   │   └── systemd service file
│   └── requirements.txt
└── web/                    # Static dashboard (or served by FastAPI)
    ├── index.html
    ├── map.js
    └── style.css
```

Tech stack aligned with existing projects:

| Layer | Technology |
|-------|------------|
| Android | Kotlin, Jetpack Compose, Room, WorkManager, Retrofit/OkHttp |
| Server | Python 3, FastAPI, SQLite, uvicorn |
| Web | HTML/JS, Leaflet, OpenStreetMap |
| TLS | Let's Encrypt via certbot + nginx |
| Deploy | systemd service on piSensors, nginx reverse proxy |

---

## 16. Build phases

Execute in order. Phases 1–2 are complete. Phase 3 (public HTTPS) is deferred; remote access uses WireGuard VPN.

| Phase | Name | Status | Deliverable |
|-------|------|--------|-------------|
| **1** | API + DB | ✅ **Done** | FastAPI on piSensors, SQLite schema, batch ingest, token auth, `recorded_at` + `received_at` |
| **2** | Android MVP | ✅ **Done** | Foreground service, collect location + telemetry, local queue, batch upload, setup screen |
| **3** | HTTPS + port forward | ⏸ **Deferred** | Public HTTPS deferred; remote access via WireGuard VPN + LAN URL on phone |
| **4** | App dashboard | ✅ **Done** | Status health states, 24h upload %, uptime, problem banners, activity log, settings |
| **5** | Analytics | ✅ **Done** | Place/visit/travel segmentation on server; summary API |
| **6** | Web dashboard | ✅ **Done** | Home, map, timeline, places, travel, history, settings (LAN via `/locator/`) |
| **7** | Polish | ⬜ Not started | Adaptive interval, place naming, purge UI, multi-device support |
| **8** | Known Wi-Fi places | ⬜ Not started | Learn SSID → location on phone; skip GPS when on known Wi-Fi (e.g. ZNet at home) |
| **9** | QR pairing | ⬜ Not started | Server shows setup QR (URL + token); phone scans to fill setup — no typing |

### Phase 1 acceptance criteria ✅

- [x] `POST /api/v1/location/batch` accepts points, sets `received_at`, dedupes on `client_point_id`
- [x] `GET /api/v1/location/latest` returns most recent point
- [x] Invalid token returns 401
- [x] SQLite file persists across service restart
- [x] Deploy script installs and starts systemd service on piSensors

### Phase 2 acceptance criteria ✅

- [x] App collects location every ~3 min with foreground service
- [x] Points written to local queue before upload attempt
- [x] Successful upload clears queue entries
- [x] Failed upload retains queue; retries on next cycle
- [x] App survives reboot (boot receiver)
- [x] Setup screen saves URL + token

### Phase 3 acceptance criteria ⏸ deferred

Public HTTPS via Nighthawk port forwarding was not completed. **Interim:** WireGuard VPN + `http://192.168.1.26:8000/locator` on the phone.

- [ ] `https://kklasmei.mooo.com/api/v1/health` responds from outside home network
- [ ] Valid TLS certificate (no browser/app warnings)
- [ ] Cert auto-renewal configured

### Phase 4 acceptance criteria ✅

- [x] Status screen shows health state (active / syncing / paused / warning / error)
- [x] Queue depth and last sent / last reading visible on Status screen
- [x] Rolling 24h upload success rate from local activity log
- [x] Service uptime shown while tracking service is running
- [x] Problem banners for permissions, battery optimization, and stopped service
- [x] Activity log lists send/fail/service events with clear and refresh
- [x] Settings shows permission status, battery optimization, queue size, clear log

### Phase 5 acceptance criteria ✅

- [x] Server segments location history into visits and travel (100 m / 1 m/s thresholds)
- [x] Visit centroids clustered into `places`; user can rename via `PUT /api/v1/places/{id}`
- [x] `GET /api/v1/places`, `/visits`, `/travel`, `/stats/summary` (period=today|week)
- [x] Analytics recomputed on demand when new points arrive
- [x] Named places preserved across recompute when cluster overlaps

### Phase 6 acceptance criteria ✅

- [x] Web UI at `http://192.168.1.26:8000/locator/` (served by FastAPI static + nginx)
- [x] Home dashboard — status cards, map with trail, top places
- [x] Map page — full-screen trail with latest pin and accuracy circle
- [x] Timeline — visits and travel segments for selected period
- [x] Places — list, sort by visits, rename in UI
- [x] Travel — segment table with duration/distance/speed
- [x] History — point browser with CSV export
- [x] Settings — API token, device ID, connection test
- [ ] Reports hub, health panel, purge UI *(deferred to Phase 7 polish)*

### Phase 8 acceptance criteria *(draft — align before build)*

- [ ] App learns coordinates for a Wi-Fi SSID after configurable GPS samples
- [ ] On known SSID, collection skips GPS and uploads learned lat/lon with `wifi_ssid` set
- [ ] Unknown SSID, cellular, or `<unknown ssid>` falls back to normal GPS
- [ ] Settings shows known networks with rename / disable / forget / re-learn
- [ ] Activity log distinguishes `wifi_known` vs GPS-sourced points
- [ ] Battery impact measurable on home Wi-Fi (manual check: Settings → Battery)

### Phase 9 acceptance criteria *(draft — align before build)*

- [ ] Server (or deploy script) can display/generate a one-time or rotatable pairing QR
- [ ] QR payload includes API base URL and Bearer token (or short-lived pairing code exchanged for token)
- [ ] Android setup screen has **Scan QR** — fills URL + token fields
- [ ] Works on LAN first; optional public HTTPS URL in QR after Phase 3
- [ ] Token never committed to git; QR generated on demand from piSensors config

**Debug shortcut (Phase 2):** `android/secrets.properties` (gitignored) → `BuildConfig.DEFAULT_API_TOKEN` for local debug APKs only. Sync via `scripts/sync-android-secrets.ps1 -FromPiSensors`.

---

## 17. Open items

| # | Item | Notes |
|---|------|-------|
| O1 | Port 443 on router | **Deferred** (Phase 3) — VPN-only for now |
| O2 | nginx integration | ✅ Done — `/locator/` on `pivpngateway` :8000; FastAPI on `127.0.0.1:8003` |
| O8 | Port 8000 | **In use** — share via path routing; do not bind a second listener on 8000 |
| O3 | Web dashboard access | LAN-only vs public with auth — lean LAN + VPN |
| O4 | Multiple phones | Schema supports `device_id`; v1 may ship with one device |
| O5 | Place cluster radius | Default 100 m — tune after real-world data |
| O6 | Persistent notification text | Required by Android; wording TBD |
| O7 | afraid.org IP updates | Confirm DDNS client keeps `kklasmei.mooo.com` current if ISP IP changes |
| O9 | **Known Wi-Fi places (Phase 8)** | Design alignment: auto-learn thresholds (N fixes, min accuracy); duplicate-SSID policy; user labeling vs auto-only; whether server (Phase 5) suggests mappings; `location_provider` value for shortcut points; re-learn cadence |

---

## 18. Quick reference

| Item | Value |
|------|-------|
| Project repo | `c:\Projects\andriod-PhoneLocator` |
| API host | piSensors (`192.168.1.26`) |
| API backend port | `127.0.0.1:8003` (new; localhost only) |
| LAN URL | `http://192.168.1.26:8000/locator/` |
| Remote access | WireGuard VPN (UDP 51822 → piGateway); same LAN URL on phone |
| Public URL | `https://kklasmei.mooo.com` *(Phase 3 — deferred)* |
| Port 8000 on piSensors | In use (gateway, cameras) — `/locator/` path added ✅ |
| Port 443 on piSensors | Free — multi-site HTTPS via nginx `server_name` *(not configured)* |
| DDNS | afraid.org → `kklasmei.mooo.com` → `74.215.40.180` |
| Upload interval | ~3 minutes |
| Auth | Bearer token |
| TLS | Let's Encrypt *(Phase 3 — deferred)* |
| Database | SQLite on piSensors |
| Retention | Forever; manual purge only |
| Timestamps | `recorded_at` (phone), `received_at` (server) |

---

## Appendix: comparison to Google Find My Device

| | Google Find My Device | Phone Locator |
|--|----------------------|---------------|
| Model | Google calls *into* phone | Phone pushes *out* to your server |
| Battery saver | Often breaks connectivity | Foreground service + exemption prompt |
| History | Limited | Full trail, forever |
| Extra data | Location only | Battery, network, activity, speed, accuracy, … |
| Privacy | Google holds data | Data on your Pi |
| Dependency | FCM, Play Services | Your API only |
| Offline | Gaps with no backfill | Local queue flushes when online |
| Analytics | None | Places, visits, travel time |
