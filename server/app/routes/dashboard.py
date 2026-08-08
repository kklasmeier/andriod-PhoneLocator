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
    period: Annotated[Literal["today", "yesterday", "week", "month"], Query()] = "today",
) -> DashboardResponse:
    analytics_service.ensure_computed(device_id)
    from_iso, to_iso = resolve_period(period)
    summary = analytics_service.build_summary(device_id=device_id, period=period)

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
        period=period,
        **{"from": from_iso},
        to=to_iso,
        latest=latest,
        stale_minutes=stale_minutes,
        status=status,
        summary=StatsSummaryResponse(**summary),
    )
