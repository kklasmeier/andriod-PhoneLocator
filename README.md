# Phone Locator

Self-hosted Android phone location tracker. The phone pushes GPS and telemetry to an API on a Raspberry Pi; a web dashboard provides maps, history, and analytics.

**Status:** Phase 3 in progress (HTTPS + public API) — Phase 2 Android MVP complete

## Personal project

This is a personal home-lab project. The repository is public for reference, but **contributions are not accepted** (no pull requests, no issues).

## Stack (planned)

- **Android** — Kotlin, foreground service, offline upload queue
- **Server** — Python, FastAPI, SQLite on Raspberry Pi
- **Web** — Leaflet maps, charts, reports
