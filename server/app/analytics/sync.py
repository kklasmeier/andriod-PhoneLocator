"""Repair derived aggregates for the local days touched by new points.

Raw location_points are the source of truth and are never deleted. A late point
marks its local day, plus the neighboring days, dirty. The sync below re-derives
visits, travel, and daily stats for that window from the stored points.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta, timezone

from app import database
from app.analytics.daily_stats import iso_to_local_day, local_tz
from app.analytics.engine import TrackPoint, segment_points
from app.analytics.periods import parse_iso
from app.analytics.presentation import apply_presentation_rules
from app.models import LocationPointIn

logger = logging.getLogger(__name__)

_FULL_REBUILD_SPAN_DAYS = 14
_locks_guard = threading.Lock()
_device_locks: dict[str, threading.Lock] = {}
_worker_guard = threading.Lock()
_worker_started = False


def _device_lock(device_id: str) -> threading.Lock:
    with _locks_guard:
        lock = _device_locks.get(device_id)
        if lock is None:
            lock = threading.Lock()
            _device_locks[device_id] = lock
        return lock


def _sql_bounds(start: datetime, end: datetime) -> tuple[str, str]:
    """Second-resolution bounds that sort correctly against mixed ISO timestamps."""
    return (
        start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
        end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"),
    )


def _local_day_bounds(day_value: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day_value, dt_time.min, tzinfo=local_tz())
    return start, start + timedelta(days=1)


def affected_local_days(recorded_at: str) -> list[str]:
    day = date.fromisoformat(iso_to_local_day(recorded_at))
    return [
        (day - timedelta(days=1)).isoformat(),
        day.isoformat(),
        (day + timedelta(days=1)).isoformat(),
    ]


def _later_timestamp(current: str | None, candidate: str) -> str:
    if current is None:
        return candidate
    return current if parse_iso(current) >= parse_iso(candidate) else candidate


def record_accepted_points(
    conn: object,
    device_id: str,
    points: list[LocationPointIn],
) -> None:
    """Mark affected days and add the new points to the heatmap. Caller commits."""
    days: set[str] = set()
    heatmap_points: list[tuple[float, float, str]] = []
    marker: str | None = None
    for point in points:
        days.update(affected_local_days(point.recorded_at))
        heatmap_points.append((point.latitude, point.longitude, point.recorded_at))
        marker = _later_timestamp(marker, point.recorded_at)
    database.mark_dirty_days(conn, device_id, sorted(days), "accepted_point")
    database.increment_heatmap_bins(conn, device_id, heatmap_points)
    if marker is None:
        return
    meta = conn.execute(
        "SELECT heatmap_bins_point_at FROM analytics_meta WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    current = meta["heatmap_bins_point_at"] if meta is not None else None
    if current is None or parse_iso(marker) >= parse_iso(current):
        database.set_heatmap_marker(conn, device_id, marker)


def sync_device(device_id: str) -> None:
    """Drain dirty days for one device. Safe to call after every upload."""
    with _device_lock(device_id):
        failures = 0
        while failures < 3:
            days = database.list_dirty_days(device_id)
            if not days:
                return
            try:
                synced = _sync_once(device_id, days)
            except Exception:
                logger.exception("aggregate sync failed device=%s days=%s", device_id, days)
                failures += 1
                continue
            if synced:
                failures = 0
            else:
                failures += 1
        remaining = database.list_dirty_days(device_id)
        if remaining:
            logger.error(
                "aggregate sync still pending device=%s days=%s",
                device_id,
                remaining,
            )


def _sync_once(device_id: str, days: list[str]) -> bool:
    min_day = date.fromisoformat(days[0])
    max_day = date.fromisoformat(days[-1])
    if (max_day - min_day).days > _FULL_REBUILD_SPAN_DAYS:
        return _full_rebuild(device_id, days)

    start, end = _local_day_bounds(min_day)[0], _local_day_bounds(max_day)[1]
    start, end = _expand_to_touching_segments(device_id, start, end)
    start_bound, end_bound = _sql_bounds(start, end)
    if database.count_visits(device_id) == 0 and database.has_points_before(device_id, start_bound):
        return _full_rebuild(device_id, days)

    token = database.point_token(device_id, start_bound, end_bound)
    points = [
        TrackPoint(
            recorded_at=row["recorded_at"],
            latitude=row["latitude"],
            longitude=row["longitude"],
            speed_mps=row["speed_mps"],
        )
        for row in database.load_points_between(device_id, start_bound, end_bound)
    ]
    visits, travels = apply_presentation_rules(*segment_points(points))
    refresh_days = _days_between(start, end)

    with database.get_connection() as conn:
        if database.point_token(device_id, start_bound, end_bound, conn=conn) != token:
            conn.rollback()
            return False
        latest = conn.execute(
            """
            SELECT recorded_at FROM location_points
            WHERE device_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
        latest_at = latest["recorded_at"] if latest else None
        created = 0
        if latest_at is not None:
            created = database.apply_window_analytics(
                conn,
                device_id,
                visits,
                travels,
                start_bound,
                end_bound,
                refresh_days,
                latest_at,
            )
        database._clear_dirty_days(conn, device_id, days)
        conn.commit()

    if created:
        from app.analytics.service import schedule_auto_rename

        schedule_auto_rename(device_id)
    logger.info(
        "synced aggregates device=%s days=%s points=%s new_places=%s",
        device_id,
        ",".join(refresh_days),
        len(points),
        created,
    )
    return True


def _expand_to_touching_segments(
    device_id: str,
    start: datetime,
    end: datetime,
) -> tuple[datetime, datetime]:
    for _ in range(6):
        start_bound, end_bound = _sql_bounds(start, end)
        seg_start, seg_end = database.overlapping_segment_bounds(device_id, start_bound, end_bound)
        changed = False
        if seg_start is not None:
            parsed_start = parse_iso(seg_start)
            if parsed_start < start:
                start = parsed_start
                changed = True
        if seg_end is not None:
            parsed_end = parse_iso(seg_end) + timedelta(milliseconds=1)
            if parsed_end > end:
                end = parsed_end
                changed = True
        rounded_start, rounded_end = _round_to_local_days(start, end)
        if rounded_start != start or rounded_end != end:
            start, end = rounded_start, rounded_end
            changed = True
        if not changed:
            break
    return _round_to_local_days(start, end)


def _round_to_local_days(start: datetime, end: datetime) -> tuple[datetime, datetime]:
    tz = local_tz()
    start_local = start.astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = end.astimezone(tz)
    if (
        end_local.hour,
        end_local.minute,
        end_local.second,
        end_local.microsecond,
    ) == (0, 0, 0, 0):
        end_day = end_local
    else:
        end_day = end_local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return start_local, end_day


def _days_between(start: datetime, end: datetime) -> list[str]:
    tz = local_tz()
    day = start.astimezone(tz).date()
    last = (end.astimezone(tz) - timedelta(microseconds=1)).date()
    days: list[str] = []
    while day <= last:
        days.append(day.isoformat())
        day += timedelta(days=1)
    return days


def _full_rebuild(device_id: str, days: list[str]) -> bool:
    token = database.point_token(device_id)
    from app.analytics.service import recompute_device

    recompute_device(device_id)
    with database.get_connection() as conn:
        if database.point_token(device_id, conn=conn) != token:
            conn.rollback()
            return False
        database._clear_dirty_days(conn, device_id, days)
        conn.commit()
    logger.info("full aggregate rebuild device=%s dirty_days=%s", device_id, len(days))
    return True


def _worker_loop() -> None:
    while True:
        try:
            for device_id in database.list_devices_with_dirty_days():
                sync_device(device_id)
        except Exception:
            logger.exception("aggregate sync worker failed")
        time.sleep(20)


def start_sync_worker() -> None:
    global _worker_started
    with _worker_guard:
        if _worker_started:
            return
        _worker_started = True
    threading.Thread(target=_worker_loop, name="aggregate-sync", daemon=True).start()
