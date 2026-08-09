"""Per-calendar-day rollups and trend bucket aggregation."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterator

from app import config
from app.analytics.periods import parse_iso
from zoneinfo import ZoneInfo


def local_tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def iter_local_day_overlaps(start_iso: str, end_iso: str) -> Iterator[tuple[str, int]]:
    tz = local_tz()
    start = parse_iso(start_iso).astimezone(tz)
    end = parse_iso(end_iso).astimezone(tz)
    if end <= start:
        return

    day_start = start.replace(hour=0, minute=0, second=0, microsecond=0)
    while day_start < end:
        day_end = day_start + timedelta(days=1)
        seg_start = max(start, day_start)
        seg_end = min(end, day_end)
        if seg_end > seg_start:
            yield day_start.strftime("%Y-%m-%d"), int((seg_end - seg_start).total_seconds())
        day_start = day_end


def _empty_bucket() -> dict[str, Any]:
    return {
        "point_count": 0,
        "visits_count": 0,
        "stationary_duration_sec": 0,
        "travel_duration_sec": 0,
        "travel_distance_m": 0.0,
        "travel_trips": 0,
        "_places_seen": set(),
    }


def compute_daily_stats_rows(
    visits: list[dict[str, Any]],
    travels: list[dict[str, Any]],
    points: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(_empty_bucket)

    for visit in visits:
        for day, sec in iter_local_day_overlaps(visit["started_at"], visit["ended_at"]):
            bucket = buckets[day]
            bucket["stationary_duration_sec"] += sec
            bucket["visits_count"] += 1
            place_id = visit.get("place_id")
            if place_id is not None:
                bucket["_places_seen"].add(int(place_id))

    for travel in travels:
        total_sec = int(travel["duration_sec"])
        for day, sec in iter_local_day_overlaps(travel["started_at"], travel["ended_at"]):
            bucket = buckets[day]
            bucket["travel_duration_sec"] += sec
            bucket["travel_trips"] += 1
            if total_sec > 0:
                bucket["travel_distance_m"] += float(travel["distance_m"]) * sec / total_sec

    tz = local_tz()
    for point in points:
        day = parse_iso(point["recorded_at"]).astimezone(tz).strftime("%Y-%m-%d")
        buckets[day]["point_count"] += 1

    rows: list[dict[str, Any]] = []
    for day in sorted(buckets.keys()):
        bucket = buckets[day]
        rows.append(
            {
                "day": day,
                "point_count": int(bucket["point_count"]),
                "visits_count": int(bucket["visits_count"]),
                "places_visited_count": len(bucket["_places_seen"]),
                "stationary_duration_sec": int(bucket["stationary_duration_sec"]),
                "travel_duration_sec": int(bucket["travel_duration_sec"]),
                "travel_distance_m": float(bucket["travel_distance_m"]),
                "travel_trips": int(bucket["travel_trips"]),
            }
        )
    return rows


def iso_to_local_day(iso_value: str) -> str:
    return parse_iso(iso_value).astimezone(local_tz()).strftime("%Y-%m-%d")


def default_trends_day_range(days: int = 90) -> tuple[str, str]:
    tz = local_tz()
    end = datetime.now(tz).date()
    start = end - timedelta(days=days - 1)
    return start.isoformat(), end.isoformat()


def pick_granularity(from_day: str, to_day: str, requested: str | None) -> str:
    if requested in ("day", "week", "month"):
        return requested
    span_days = (date.fromisoformat(to_day) - date.fromisoformat(from_day)).days + 1
    if span_days <= 31:
        return "day"
    if span_days <= 120:
        return "week"
    return "month"


def week_start(day_str: str) -> str:
    day = date.fromisoformat(day_str)
    days_since_sunday = (day.weekday() + 1) % 7
    return (day - timedelta(days=days_since_sunday)).isoformat()


def week_label(week_start_day: str) -> str:
    start = date.fromisoformat(week_start_day)
    end = start + timedelta(days=6)
    if start.month == end.month:
        return f"{start.strftime('%b %d')}–{end.strftime('%d')}"
    return f"{start.strftime('%b %d')}–{end.strftime('%b %d')}"


def month_label(month_key: str) -> str:
    month = datetime.strptime(month_key, "%Y-%m").date()
    return month.strftime("%b %Y")


def aggregate_trend_buckets(
    rows: list[dict[str, Any]],
    granularity: str,
) -> list[dict[str, Any]]:
    if granularity == "day":
        return [
            {
                "bucket": row["day"],
                "label": datetime.strptime(row["day"], "%Y-%m-%d").strftime("%b %d"),
                **{key: row[key] for key in _NUMERIC_KEYS},
            }
            for row in rows
        ]

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if granularity == "week":
            bucket = week_start(row["day"])
            label = week_label(bucket)
        else:
            bucket = row["day"][:7]
            label = month_label(bucket)

        if bucket not in grouped:
            grouped[bucket] = {
                "bucket": bucket,
                "label": label,
                **{key: 0 for key in _NUMERIC_KEYS},
            }
        target = grouped[bucket]
        for key in _NUMERIC_KEYS:
            if key == "travel_distance_m":
                target[key] += float(row[key])
            else:
                target[key] += int(row[key])

    return [grouped[key] for key in sorted(grouped.keys())]


_NUMERIC_KEYS = (
    "point_count",
    "visits_count",
    "places_visited_count",
    "stationary_duration_sec",
    "travel_duration_sec",
    "travel_distance_m",
    "travel_trips",
)
