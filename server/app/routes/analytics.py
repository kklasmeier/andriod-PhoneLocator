from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app import database
from app.analytics import service as analytics_service
from app.analytics.auto_naming import auto_rename_places
from app.analytics.periods import resolve_period, resolve_range
from app.auth import verify_api_token
from app.models import (
    AutoNamePlacesResponse,
    AutoRenameStatusResponse,
    DeviceSettingsResponse,
    DeviceSettingsUpdate,
    LifetimeStatsResponse,
    FrequentRouteOut,
    PlaceOut,
    PlaceRenameRequest,
    PlacesResponse,
    ReportsResponse,
    ReportsTravelOut,
    StatsSummaryResponse,
    TravelResponse,
    TravelSegmentOut,
    VisitsTimelineResponse,
)

places_router = APIRouter(prefix="/api/v1/places", tags=["analytics"])
visits_router = APIRouter(prefix="/api/v1/visits", tags=["analytics"])
travel_router = APIRouter(prefix="/api/v1/travel", tags=["analytics"])
stats_router = APIRouter(prefix="/api/v1/stats", tags=["analytics"])
settings_router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def _reports_travel_out(data: dict) -> ReportsTravelOut:
    return ReportsTravelOut(
        trip_count=data["trip_count"],
        duration_sec=data["duration_sec"],
        distance_m=data["distance_m"],
        frequent_routes=[FrequentRouteOut(**row) for row in data["frequent_routes"]],
        segments=[TravelSegmentOut(**row) for row in data["segments"]],
        recent_segments=[TravelSegmentOut(**row) for row in data["recent_segments"]],
    )


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


@places_router.post("/auto-name", response_model=AutoNamePlacesResponse)
def auto_name_places(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    dry_run: Annotated[bool, Query()] = False,
) -> AutoNamePlacesResponse:
    analytics_service.ensure_computed(device_id)
    result = auto_rename_places(device_id, dry_run=dry_run)
    return AutoNamePlacesResponse(**result)


@places_router.get("/auto-name/status", response_model=AutoRenameStatusResponse)
def auto_name_status(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> AutoRenameStatusResponse:
    status = database.get_auto_rename_status(device_id)
    return AutoRenameStatusResponse(**status)


@settings_router.get("", response_model=DeviceSettingsResponse)
def get_settings(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> DeviceSettingsResponse:
    return DeviceSettingsResponse(
        device_id=device_id,
        auto_rename_places=database.get_auto_rename_enabled(device_id),
    )


@settings_router.put("", response_model=DeviceSettingsResponse)
def update_settings(
    payload: DeviceSettingsUpdate,
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> DeviceSettingsResponse:
    database.set_auto_rename_enabled(device_id, payload.auto_rename_places)
    return DeviceSettingsResponse(
        device_id=device_id,
        auto_rename_places=payload.auto_rename_places,
    )


@visits_router.get("", response_model=VisitsTimelineResponse)
def list_visits(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    from_value: Annotated[str | None, Query(alias="from")] = None,
    to_value: Annotated[str | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 100,
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
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
) -> TravelResponse:
    from_iso, to_iso = resolve_range(from_value, to_value)
    segments = analytics_service.build_travel_list(
        device_id=device_id,
        from_iso=from_iso,
        to_iso=to_iso,
        limit=limit,
    )
    return TravelResponse(
        device_id=device_id,
        count=len(segments),
        segments=[TravelSegmentOut(**row) for row in segments],
    )


@stats_router.get("/summary", response_model=StatsSummaryResponse)
def stats_summary(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    period: Annotated[Literal["today", "yesterday", "week", "month"], Query()] = "today",
) -> StatsSummaryResponse:
    data = analytics_service.build_summary(device_id=device_id, period=period)
    return StatsSummaryResponse(**data)


@stats_router.get("/lifetime", response_model=LifetimeStatsResponse)
def stats_lifetime(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> LifetimeStatsResponse:
    data = analytics_service.ensure_lifetime_stats(device_id)
    return LifetimeStatsResponse(**data)


@stats_router.get("/reports", response_model=ReportsResponse)
def stats_reports(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    from_value: Annotated[str | None, Query(alias="from")] = None,
    to_value: Annotated[str | None, Query(alias="to")] = None,
    period: Annotated[str | None, Query()] = None,
) -> ReportsResponse:
    lifetime = analytics_service.ensure_lifetime_stats(device_id)

    if from_value and to_value:
        from_iso, to_iso = from_value, to_value
        period_label = period or "custom"
        summary = analytics_service.build_summary(
            device_id=device_id,
            period=period_label,
            from_iso=from_iso,
            to_iso=to_iso,
            max_places=None,
        )
    else:
        period_label = period or "today"
        from_iso, to_iso = resolve_period(period_label)
        summary = analytics_service.build_summary(
            device_id=device_id,
            period=period_label,
            from_iso=from_iso,
            to_iso=to_iso,
            max_places=None,
        )

    period_travel = analytics_service.build_reports_travel(
        device_id,
        from_iso,
        to_iso,
        segment_limit=200,
    )
    lifetime_travel = analytics_service.build_reports_travel(
        device_id,
        None,
        None,
        segment_limit=500,
        recent_limit=30,
    )

    return ReportsResponse(
        device_id=device_id,
        period=period_label,
        **{"from": from_iso},
        to=to_iso,
        lifetime=LifetimeStatsResponse(**lifetime),
        summary=StatsSummaryResponse(**summary),
        lifetime_travel=_reports_travel_out(lifetime_travel),
        period_travel=_reports_travel_out(period_travel),
    )
