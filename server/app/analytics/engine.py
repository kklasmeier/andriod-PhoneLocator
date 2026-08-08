"""Visit / travel segmentation and place clustering."""

from dataclasses import dataclass, field
from datetime import datetime

from app.analytics.constants import PLACE_CLUSTER_RADIUS_M, STATIONARY_RADIUS_M, STATIONARY_SPEED_MPS
from app.analytics.geo import centroid, haversine_m
from app.analytics.periods import parse_iso


@dataclass
class TrackPoint:
    recorded_at: str
    latitude: float
    longitude: float
    speed_mps: float | None = None


@dataclass
class VisitDraft:
    started_at: str
    ended_at: str
    center_lat: float
    center_lon: float
    points: list[TrackPoint] = field(default_factory=list)

    @property
    def duration_sec(self) -> int:
        start = parse_iso(self.started_at)
        end = parse_iso(self.ended_at)
        return max(0, int((end - start).total_seconds()))


@dataclass
class TravelDraft:
    started_at: str
    ended_at: str
    distance_m: float
    points: list[TrackPoint] = field(default_factory=list)

    @property
    def duration_sec(self) -> int:
        start = parse_iso(self.started_at)
        end = parse_iso(self.ended_at)
        return max(0, int((end - start).total_seconds()))

    @property
    def avg_speed_mps(self) -> float | None:
        if self.duration_sec <= 0:
            return None
        return self.distance_m / self.duration_sec


@dataclass
class PlaceDraft:
    center_lat: float
    center_lon: float
    radius_m: float
    first_seen_at: str
    last_seen_at: str
    visit_count: int = 1


def _effective_speed(prev: TrackPoint, curr: TrackPoint) -> float:
    if curr.speed_mps is not None:
        return max(0.0, curr.speed_mps)
    dt = (parse_iso(curr.recorded_at) - parse_iso(prev.recorded_at)).total_seconds()
    if dt <= 0:
        return 0.0
    dist = haversine_m(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
    return dist / dt


def _same_place(prev: TrackPoint, curr: TrackPoint) -> bool:
    dist = haversine_m(prev.latitude, prev.longitude, curr.latitude, curr.longitude)
    speed = _effective_speed(prev, curr)
    return dist < STATIONARY_RADIUS_M and speed < STATIONARY_SPEED_MPS


def _close_visit(points: list[TrackPoint]) -> VisitDraft:
    lat, lon = centroid([(p.latitude, p.longitude) for p in points])
    return VisitDraft(
        started_at=points[0].recorded_at,
        ended_at=points[-1].recorded_at,
        center_lat=lat,
        center_lon=lon,
        points=list(points),
    )


def _close_travel(points: list[TrackPoint]) -> TravelDraft:
    distance = 0.0
    for i in range(1, len(points)):
        distance += haversine_m(
            points[i - 1].latitude,
            points[i - 1].longitude,
            points[i].latitude,
            points[i].longitude,
        )
    return TravelDraft(
        started_at=points[0].recorded_at,
        ended_at=points[-1].recorded_at,
        distance_m=distance,
        points=list(points),
    )


def segment_points(points: list[TrackPoint]) -> tuple[list[VisitDraft], list[TravelDraft]]:
    """Split a chronological point stream into visits and travel segments."""
    if not points:
        return [], []

    visits: list[VisitDraft] = []
    travels: list[TravelDraft] = []
    in_visit = True
    bucket: list[TrackPoint] = [points[0]]

    for idx in range(1, len(points)):
        prev = points[idx - 1]
        curr = points[idx]
        stationary = _same_place(prev, curr)

        if in_visit:
            if stationary:
                bucket.append(curr)
            else:
                visits.append(_close_visit(bucket))
                bucket = [prev, curr]
                in_visit = False
        elif stationary:
            travels.append(_close_travel(bucket))
            bucket = [curr]
            in_visit = True
        else:
            bucket.append(curr)

    if in_visit:
        visits.append(_close_visit(bucket))
    else:
        travels.append(_close_travel(bucket))

    return visits, travels


def cluster_places(visits: list[VisitDraft]) -> list[PlaceDraft]:
    """Greedy cluster of visit centroids into places."""
    places: list[PlaceDraft] = []
    for visit in sorted(visits, key=lambda v: v.started_at):
        matched: PlaceDraft | None = None
        for place in places:
            if (
                haversine_m(visit.center_lat, visit.center_lon, place.center_lat, place.center_lon)
                < PLACE_CLUSTER_RADIUS_M
            ):
                matched = place
                break
        if matched is None:
            places.append(
                PlaceDraft(
                    center_lat=visit.center_lat,
                    center_lon=visit.center_lon,
                    radius_m=0.0,
                    first_seen_at=visit.started_at,
                    last_seen_at=visit.ended_at,
                    visit_count=1,
                )
            )
            continue

        n = matched.visit_count
        matched.center_lat = (matched.center_lat * n + visit.center_lat) / (n + 1)
        matched.center_lon = (matched.center_lon * n + visit.center_lon) / (n + 1)
        dist = haversine_m(visit.center_lat, visit.center_lon, matched.center_lat, matched.center_lon)
        matched.radius_m = max(matched.radius_m, dist)
        matched.visit_count += 1
        if visit.started_at < matched.first_seen_at:
            matched.first_seen_at = visit.started_at
        if visit.ended_at > matched.last_seen_at:
            matched.last_seen_at = visit.ended_at

    return places


def assign_visit_place_ids(
    visits: list[VisitDraft],
    places: list[tuple[int, float, float]],
) -> list[int | None]:
    """Map each visit to nearest place id within cluster radius."""
    place_ids: list[int | None] = []
    for visit in visits:
        best_id: int | None = None
        best_dist = PLACE_CLUSTER_RADIUS_M
        for place_id, lat, lon in places:
            dist = haversine_m(visit.center_lat, visit.center_lon, lat, lon)
            if dist < best_dist:
                best_dist = dist
                best_id = place_id
        place_ids.append(best_id)
    return place_ids
