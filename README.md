# Phone Locator

Self-hosted Android phone location tracker. The phone pushes GPS and telemetry to an API on a Raspberry Pi; a web dashboard provides maps, history, and analytics.

**Status:** Phases 1–2 and 4 complete. Remote access via **WireGuard VPN** (Phase 3 public HTTPS deferred).

## Personal project

This is a personal home-lab project. The repository is public for reference, but **contributions are not accepted** (no pull requests, no issues).

## Stack (planned)

- **Android** — Kotlin, foreground service, offline upload queue
- **Server** — Python, FastAPI, SQLite on Raspberry Pi
- **Web** — Leaflet maps, charts, reports
