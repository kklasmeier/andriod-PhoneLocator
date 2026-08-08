from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app import database
from app.analytics import service as analytics_service
from app.analytics.periods import resolve_range
from app.auth import verify_api_token
from app.models import (
    PlaceOut,
    PlaceRenameRequest,
    PlacesResponse,
    StatsSummaryResponse,
    TravelResponse,
    TravelSegmentOut,
    VisitsTimelineResponse,
)

places_router = APIRouter(prefix="/api/v1/places", tags=["analytics"])
visits_router = APIRouter(prefix="/api/v1/visits", tags=["analytics"])
travel_router = APIRouter(prefix="/api/v1/travel", tags=["analytics"])
stats_router = APIRouter(prefix="/api/v1/stats", tags=["analytics"])


@places_router.get("", response_model=PlacesResponse)
def list_places(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> PlacesResponse:
    analytics_service.ensure_computed(device_id)
    rows = database.get_places(device_id)
    places = [PlaceOut(**row) for row in rows]
    return PlacesResponse(device_id=device_id, count=len(places), places=places)


@places_router.put("/{place_id}", response_model=PlaceOut)
def rename_place(
    place_id: int,
    payload: PlaceRenameRequest,
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> PlaceOut:
    updated = database.update_place_name(place_id, device_id, payload.name)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Place not found")
    return PlaceOut(**updated)


@visits_router.get("", response_model=VisitsTimelineResponse)
def list_visits(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    from_value: Annotated[str | None, Query(alias="from")] = None,
    to_value: Annotated[str | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> VisitsTimelineResponse:
    from_iso, to_iso = resolve_range(from_value, to_value)
    items = analytics_service.build_visits_timeline(
        device_id=device_id,
        from_iso=from_iso,
        to_iso=to_iso,
        limit=limit,
    )
    return VisitsTimelineResponse(device_id=device_id, count=len(items), items=items)


@travel_router.get("", response_model=TravelResponse)
def list_travel(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    from_value: Annotated[str | None, Query(alias="from")] = None,
    to_value: Annotated[str | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> TravelResponse:
    from_iso, to_iso = resolve_range(from_value, to_value)
    analytics_service.ensure_computed(device_id)
    rows = database.get_travel_segments(
        device_id=device_id,
        from_iso=from_iso,
        to_iso=to_iso,
        limit=limit,
    )
    segments = [TravelSegmentOut(**row) for row in rows]
    return TravelResponse(device_id=device_id, count=len(segments), segments=segments)


@stats_router.get("/summary", response_model=StatsSummaryResponse)
def stats_summary(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    period: Annotated[Literal["today", "week"], Query()] = "today",
) -> StatsSummaryResponse:
    data = analytics_service.build_summary(device_id=device_id, period=period)
    return StatsSummaryResponse(**data)
