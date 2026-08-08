from typing import Any

from pydantic import BaseModel, Field


class LocationPointIn(BaseModel):
    client_point_id: str = Field(min_length=1, max_length=64)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = None
    altitude_m: float | None = None
    speed_mps: float | None = None
    bearing_deg: float | None = None
    location_provider: str | None = None
    activity: str | None = None
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    battery_charging: bool | None = None
    power_save_mode: bool | None = None
    network_type: str | None = None
    wifi_ssid: str | None = None
    cell_signal_dbm: int | None = None
    app_version: str | None = None
    upload_attempt: int | None = Field(default=None, ge=1)
    queued_duration_sec: int | None = Field(default=None, ge=0)
    recorded_at: str = Field(min_length=1)


class BatchUploadRequest(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    points: list[LocationPointIn] = Field(min_length=1, max_length=100)


class BatchUploadResponse(BaseModel):
    accepted: int
    duplicates: int
    errors: list[str]
    commands: list["DeviceCommandSummary"] = Field(default_factory=list)


class DeviceCommandSummary(BaseModel):
    id: str
    type: str


class CommandCreateRequest(BaseModel):
    type: str = Field(default="ring", min_length=1, max_length=32)


class CommandAckRequest(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    message: str | None = Field(default=None, max_length=256)


class CommandOut(BaseModel):
    id: str
    device_id: str
    type: str
    status: str
    created_at: str
    expires_at: str
    delivered_at: str | None = None
    acked_at: str | None = None
    ack_latitude: float | None = None
    ack_longitude: float | None = None
    ack_message: str | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "CommandOut":
        return cls(
            id=row["id"],
            device_id=row["device_id"],
            type=row["command_type"],
            status=row["status"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            delivered_at=row.get("delivered_at"),
            acked_at=row.get("acked_at"),
            ack_latitude=row.get("ack_latitude"),
            ack_longitude=row.get("ack_longitude"),
            ack_message=row.get("ack_message"),
        )


class PendingCommandsResponse(BaseModel):
    commands: list[DeviceCommandSummary]


class LocationPointOut(BaseModel):
    id: int
    device_id: str
    client_point_id: str
    latitude: float
    longitude: float
    accuracy_m: float | None = None
    altitude_m: float | None = None
    speed_mps: float | None = None
    bearing_deg: float | None = None
    location_provider: str | None = None
    activity: str | None = None
    battery_pct: int | None = None
    battery_charging: bool | None = None
    power_save_mode: bool | None = None
    network_type: str | None = None
    wifi_ssid: str | None = None
    cell_signal_dbm: int | None = None
    app_version: str | None = None
    upload_attempt: int | None = None
    queued_duration_sec: int | None = None
    recorded_at: str
    received_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "LocationPointOut":
        return cls(**row)


class LatestLocationResponse(BaseModel):
    device_id: str
    point: LocationPointOut | None


class HistoryResponse(BaseModel):
    device_id: str
    count: int
    total_count: int
    sampled: bool = False
    points: list[LocationPointOut]


class PlaceOut(BaseModel):
    id: int
    device_id: str
    name: str | None = None
    center_lat: float
    center_lon: float
    radius_m: float
    first_seen_at: str
    last_seen_at: str
    visit_count: int


class PlacesResponse(BaseModel):
    device_id: str
    count: int
    places: list[PlaceOut]


class PlaceRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class VisitItem(BaseModel):
    kind: str = "visit"
    id: int
    place_id: int | None = None
    place_name: str | None = None
    started_at: str
    ended_at: str
    duration_sec: int
    center_lat: float
    center_lon: float


class TravelItem(BaseModel):
    kind: str = "travel"
    id: int
    started_at: str
    ended_at: str
    duration_sec: int
    distance_m: float
    avg_speed_mps: float | None = None


class VisitsTimelineResponse(BaseModel):
    device_id: str
    count: int
    items: list[VisitItem | TravelItem]


class TravelSegmentOut(BaseModel):
    id: int
    device_id: str
    from_visit_id: int | None = None
    to_visit_id: int | None = None
    from_place_name: str | None = None
    to_place_name: str | None = None
    started_at: str
    ended_at: str
    duration_sec: int
    distance_m: float
    avg_speed_mps: float | None = None


class TravelResponse(BaseModel):
    device_id: str
    count: int
    segments: list[TravelSegmentOut]


class TopPlaceSummary(BaseModel):
    place_id: int
    name: str
    duration_sec: int


class WeekTeaser(BaseModel):
    places_count: int
    travel_duration_sec: int


class StatsSummaryResponse(BaseModel):
    device_id: str
    period: str
    from_: str = Field(alias="from")
    to: str
    places_count: int
    travel_duration_sec: int
    stationary_duration_sec: int
    top_places: list[TopPlaceSummary]
    week_teaser: WeekTeaser | None = None

    model_config = {"populate_by_name": True, "ser_json_by_alias": True}


class DashboardResponse(BaseModel):
    device_id: str
    period: str
    from_: str = Field(alias="from")
    to: str
    latest: LocationPointOut | None
    stale_minutes: int | None
    status: str
    summary: StatsSummaryResponse

    model_config = {"populate_by_name": True, "ser_json_by_alias": True}


class DeviceSettingsResponse(BaseModel):
    device_id: str
    auto_rename_places: bool


class DeviceSettingsUpdate(BaseModel):
    auto_rename_places: bool


class AutoNamePlacesResponse(BaseModel):
    device_id: str
    dry_run: bool
    skipped: bool = False
    reason: str | None = None
    running: bool = False
    started_at: str | None = None
    inherit_groups: int
    geocode_groups: int
    geocode_queries_needed: int
    places_inherited: int
    places_geocoded: int
    cache_hits: int
    api_calls: int
    errors: list[str]
    unnamed_skipped_short_stay: int | None = None


class AutoRenameStatusResponse(BaseModel):
    device_id: str
    running: bool
    started_at: str | None = None
    finished_at: str | None = None
    last_result: dict | None = None
