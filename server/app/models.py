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

    model_config = {"populate_by_name": True}
