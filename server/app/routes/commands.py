from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app import database
from app.auth import verify_api_token
from app.models import (
    CommandAckRequest,
    CommandCreateRequest,
    CommandOut,
    DeviceCommandSummary,
    PendingCommandsResponse,
)

router = APIRouter(prefix="/api/v1/devices", tags=["commands"])


@router.post("/{device_id}/commands", response_model=CommandOut)
def create_command(
    device_id: str,
    payload: CommandCreateRequest,
    _: Annotated[None, Depends(verify_api_token)],
) -> CommandOut:
    if payload.type != "ring":
        raise HTTPException(status_code=400, detail="unsupported command type")
    try:
        row = database.create_device_command(device_id, payload.type)
    except ValueError as exc:
        if str(exc) == "ring rate limit":
            raise HTTPException(status_code=429, detail="ring rate limit") from exc
        raise
    return CommandOut.from_row(row)


@router.get("/{device_id}/commands/pending", response_model=PendingCommandsResponse)
def pending_commands(
    device_id: str,
    _: Annotated[None, Depends(verify_api_token)],
) -> PendingCommandsResponse:
    rows = database.claim_pending_commands(device_id)
    return PendingCommandsResponse(
        commands=[
            DeviceCommandSummary(id=row["id"], type=row["command_type"])
            for row in rows
        ],
    )


@router.get("/{device_id}/commands/{command_id}", response_model=CommandOut)
def get_command(
    device_id: str,
    command_id: str,
    _: Annotated[None, Depends(verify_api_token)],
) -> CommandOut:
    row = database.get_device_command(command_id, device_id)
    if row is None:
        raise HTTPException(status_code=404, detail="command not found")
    return CommandOut.from_row(row)


@router.post("/{device_id}/commands/{command_id}/ack", response_model=CommandOut)
def ack_command(
    device_id: str,
    command_id: str,
    payload: CommandAckRequest,
    _: Annotated[None, Depends(verify_api_token)],
) -> CommandOut:
    row = database.ack_device_command(
        command_id,
        device_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
        message=payload.message,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="command not found")
    return CommandOut.from_row(row)
