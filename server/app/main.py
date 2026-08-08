"""Phone Locator API — FastAPI application."""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app import database
from app.routes import analytics, health, location


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
app.include_router(analytics.places_router)
app.include_router(analytics.visits_router)
app.include_router(analytics.travel_router)
app.include_router(analytics.stats_router)
