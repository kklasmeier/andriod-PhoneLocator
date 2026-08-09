from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app import database
from app.analytics import service as analytics_service
from app.auth import verify_api_token
from app.models import (
    BatchUploadRequest,
    BatchUploadResponse,
    DeviceCommandSummary,
    HeatmapBinOut,
    HeatmapResponse,
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
    command_rows = database.claim_pending_commands(payload.device_id)
    return BatchUploadResponse(
        accepted=accepted,
        duplicates=duplicates,
        errors=errors,
        commands=[
            DeviceCommandSummary(id=row["id"], type=row["command_type"])
            for row in command_rows
        ],
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


@router.get("/heatmap", response_model=HeatmapResponse)
def location_heatmap(
    device_id: Annotated[str, Query(min_length=1, max_length=128)],
    _: Annotated[None, Depends(verify_api_token)],
    min_count: Annotated[int, Query(ge=1, le=100)] = 1,
    limit: Annotated[int, Query(ge=1, le=5000)] = 5000,
) -> HeatmapResponse:
    data = analytics_service.build_heatmap(
        device_id,
        min_count=min_count,
        limit=limit,
    )
    return HeatmapResponse(
        device_id=data["device_id"],
        bin_count=data["bin_count"],
        total_points=data["total_points"],
        max_count=data["max_count"],
        cell_size_m=data["cell_size_m"],
        bins=[HeatmapBinOut(**row) for row in data["bins"]],
    )
