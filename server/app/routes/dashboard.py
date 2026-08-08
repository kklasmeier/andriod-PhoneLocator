from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app import database
from app.analytics import service as analytics_service
from app.analytics.periods import parse_iso, resolve_period
from app.auth import verify_api_token
from app.models import DashboardResponse, StatsSummaryResponse

router = APIRouter(prefix="/api/v1/stats", tags=["dashboard"])

STALE_MINUTES = 10
NO_DATA_HOURS = 24


@router.get("/dashboard", response_model=DashboardResponse)
def dashboard(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    period: Annotated[Literal["today", "yesterday", "week", "month"] | None, Query()] = None,
    from_value: Annotated[str | None, Query(alias="from")] = None,
    to_value: Annotated[str | None, Query(alias="to")] = None,
    include_week_teaser: Annotated[bool, Query()] = False,
) -> DashboardResponse:
    analytics_service.ensure_computed(device_id)

    if from_value and to_value:
        from_iso, to_iso = from_value, to_value
        period_label = period or "custom"
        summary = analytics_service.build_summary(
            device_id=device_id,
            period=period_label,
            from_iso=from_iso,
            to_iso=to_iso,
            include_week_teaser=include_week_teaser,
        )
    else:
        period_label = period or "today"
        from_iso, to_iso = resolve_period(period_label)
        summary = analytics_service.build_summary(
            device_id=device_id,
            period=period_label,
            include_week_teaser=include_week_teaser or period_label == "today",
        )

    latest = database.get_latest_point(device_id)

    status = "no_data"
    stale_minutes: int | None = None
    if latest is not None:
        age = datetime.now(timezone.utc) - parse_iso(latest.recorded_at).astimezone(timezone.utc)
        stale_minutes = int(age.total_seconds() // 60)
        if stale_minutes > NO_DATA_HOURS * 60:
            status = "no_data"
        elif stale_minutes > STALE_MINUTES:
            status = "stale"
        else:
            status = "ok"

    return DashboardResponse(
        device_id=device_id,
        period=period_label,
        **{"from": from_iso},
        to=to_iso,
        latest=latest,
        stale_minutes=stale_minutes,
        status=status,
        summary=StatsSummaryResponse(**summary),
    )
