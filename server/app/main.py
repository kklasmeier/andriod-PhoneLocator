"""Phone Locator API — FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app import database
from app.routes import analytics, commands, dashboard, health, location


def _web_root() -> Path | None:
    base = Path(__file__).resolve().parents[1]
    for candidate in (base / "web", base.parent / "web"):
        if candidate.is_dir():
            return candidate
    return None


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    database.init_db()
    yield


app = FastAPI(
    title="Phone Locator API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(location.router)
app.include_router(commands.router)
app.include_router(analytics.places_router)
app.include_router(analytics.visits_router)
app.include_router(analytics.travel_router)
app.include_router(analytics.stats_router)
app.include_router(analytics.settings_router)
app.include_router(dashboard.router)


@app.middleware("http")
async def cache_control_for_web_assets(request: Request, call_next):
    """Avoid stale ES module caches on mobile after deploy (mixed old/new js files)."""
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".js", ".css", ".html")) or path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


_web_dir = _web_root()
if _web_dir is not None:
    app.mount("/", StaticFiles(directory=str(_web_dir), html=True), name="web")
