from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app import database
from app.auth import verify_api_token
from app.models import (
    BatchUploadRequest,
    BatchUploadResponse,
    HistoryResponse,
    LatestLocationResponse,
)

router = APIRouter(prefix="/api/v1/location", tags=["location"])


@router.post("/batch", response_model=BatchUploadResponse)
def upload_batch(
    payload: BatchUploadRequest,
    _: Annotated[None, Depends(verify_api_token)],
) -> BatchUploadResponse:
    accepted, duplicates, errors = database.insert_points(
        device_id=payload.device_id,
        points=payload.points,
    )
    return BatchUploadResponse(
        accepted=accepted,
        duplicates=duplicates,
        errors=errors,
    )


@router.get("/latest", response_model=LatestLocationResponse)
def latest_location(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
) -> LatestLocationResponse:
    point = database.get_latest_point(device_id)
    return LatestLocationResponse(device_id=device_id, point=point)


@router.get("/history", response_model=HistoryResponse)
def location_history(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    from_ts: Annotated[str | None, Query(alias="from")] = None,
    to_ts: Annotated[str | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    order: Annotated[Literal["asc", "desc"], Query()] = "asc",
    sample: Annotated[bool, Query()] = True,
) -> HistoryResponse:
    points, total_count, sampled = database.get_history(
        device_id=device_id,
        from_ts=from_ts,
        to_ts=to_ts,
        limit=limit,
        offset=offset,
        order=order,
        sample=sample,
    )
    return HistoryResponse(
        device_id=device_id,
        count=len(points),
        total_count=total_count,
        sampled=sampled,
        points=points,
    )
