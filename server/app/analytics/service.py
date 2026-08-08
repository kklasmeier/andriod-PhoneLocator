"""Orchestrate analytics recompute and summary queries."""

from app import database
from app.analytics.engine import TrackPoint, assign_visit_place_ids, cluster_places, segment_points
from app.analytics.presentation import apply_presentation_rules
from app.analytics.periods import overlap_seconds, resolve_period


def recompute_device(device_id: str) -> None:
    rows = database.get_points_for_analytics(device_id)
    points = [
        TrackPoint(
            recorded_at=row["recorded_at"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            speed_mps=row["speed_mps"],
        )
        for row in rows
    ]
    visits, travels = segment_points(points)
    visits, travels = apply_presentation_rules(visits, travels)
    place_drafts = cluster_places(visits)

    database.replace_analytics(
        device_id=device_id,
        visits=visits,
        travels=travels,
        place_drafts=place_drafts,
        last_point_recorded_at=rows[-1]["recorded_at"] if rows else None,
    )


def ensure_computed(device_id: str) -> None:
    latest = database.get_latest_point_recorded_at(device_id)
    if latest is None:
        return
    meta = database.get_analytics_meta(device_id)
    if meta is None or meta["last_point_recorded_at"] != latest:
        recompute_device(device_id)


def build_summary(
    device_id: str,
    period: str | None = None,
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
    include_week_teaser: bool = False,
) -> dict:
    ensure_computed(device_id)
    if from_iso is None or to_iso is None:
        if period is None:
            period = "today"
        from_iso, to_iso = resolve_period(period)
    else:
        period = period or "custom"

    visits = database.get_visits(device_id, from_iso=from_iso, to_iso=to_iso)
    travels = database.get_travel_segments(device_id, from_iso=from_iso, to_iso=to_iso)
    places_by_id = {p["id"]: p for p in database.get_places(device_id)}

    stationary_duration_sec = 0
    place_durations: dict[int, int] = {}
    place_ids_seen: set[int] = set()

    for visit in visits:
        overlap = overlap_seconds(visit["started_at"], visit["ended_at"], from_iso, to_iso)
        stationary_duration_sec += overlap
        if visit["place_id"] is not None:
            place_ids_seen.add(visit["place_id"])
            place_durations[visit["place_id"]] = place_durations.get(visit["place_id"], 0) + overlap

    travel_duration_sec = sum(
        overlap_seconds(t["started_at"], t["ended_at"], from_iso, to_iso) for t in travels
    )

    top_places = sorted(place_durations.items(), key=lambda item: item[1], reverse=True)[:3]
    top_place_rows = []
    for place_id, duration_sec in top_places:
        place = places_by_id.get(place_id)
        name = place["name"] if place and place["name"] else f"Place {place_id}"
        top_place_rows.append(
            {
                "place_id": place_id,
                "name": name,
                "duration_sec": duration_sec,
            }
        )

    result = {
        "device_id": device_id,
        "period": period,
        "from": from_iso,
        "to": to_iso,
        "places_count": len(place_ids_seen),
        "travel_duration_sec": travel_duration_sec,
        "stationary_duration_sec": stationary_duration_sec,
        "top_places": top_place_rows,
    }

    if include_week_teaser:
        week_from, week_to = resolve_period("week")
        week_visits = database.get_visits(device_id, from_iso=week_from, to_iso=week_to)
        week_travels = database.get_travel_segments(device_id, from_iso=week_from, to_iso=week_to)
        week_place_ids = {v["place_id"] for v in week_visits if v["place_id"] is not None}
        week_travel_sec = sum(
            overlap_seconds(t["started_at"], t["ended_at"], week_from, week_to) for t in week_travels
        )
        result["week_teaser"] = {
            "places_count": len(week_place_ids),
            "travel_duration_sec": week_travel_sec,
        }

    return result


def build_visits_timeline(
    device_id: str,
    from_iso: str | None,
    to_iso: str | None,
    limit: int = 50,
) -> list[dict]:
    ensure_computed(device_id)
    visits = database.get_visits(device_id, from_iso=from_iso, to_iso=to_iso)
    travels = database.get_travel_segments(device_id, from_iso=from_iso, to_iso=to_iso)
    places_by_id = {p["id"]: p for p in database.get_places(device_id)}

    items: list[dict] = []
    for visit in visits:
        place_name = None
        if visit["place_id"] is not None:
            place = places_by_id.get(visit["place_id"])
            if place and place["name"]:
                place_name = place["name"]
            elif visit["place_id"] is not None:
                place_name = f"Place {visit['place_id']}"
        items.append(
            {
                "kind": "visit",
                "id": visit["id"],
                "place_id": visit["place_id"],
                "place_name": place_name,
                "started_at": visit["started_at"],
                "ended_at": visit["ended_at"],
                "duration_sec": visit["duration_sec"],
                "center_lat": visit["center_lat"],
                "center_lon": visit["center_lon"],
            }
        )

    for travel in travels:
        items.append(
            {
                "kind": "travel",
                "id": travel["id"],
                "started_at": travel["started_at"],
                "ended_at": travel["ended_at"],
                "duration_sec": travel["duration_sec"],
                "distance_m": travel["distance_m"],
                "avg_speed_mps": travel["avg_speed_mps"],
            }
        )

    items.sort(key=lambda row: row["started_at"])
    return items[:limit]
