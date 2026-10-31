import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

logger = logging.getLogger(__name__)

from app import config
from app.models import LocationPointIn, LocationPointOut

HISTORY_POINT_COLUMNS = """
    id, device_id, client_point_id, latitude, longitude, accuracy_m, altitude_m,
    speed_mps, bearing_deg, location_provider, activity, battery_pct, battery_charging,
    power_save_mode, network_type, wifi_ssid, cell_signal_dbm, app_version,
    upload_attempt, queued_duration_sec, recorded_at, received_at
"""

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS location_points (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    client_point_id TEXT NOT NULL UNIQUE,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    accuracy_m REAL,
    altitude_m REAL,
    speed_mps REAL,
    bearing_deg REAL,
    location_provider TEXT,
    activity TEXT,
    battery_pct INTEGER,
    battery_charging INTEGER,
    power_save_mode INTEGER,
    network_type TEXT,
    wifi_ssid TEXT,
    cell_signal_dbm INTEGER,
    app_version TEXT,
    upload_attempt INTEGER,
    queued_duration_sec INTEGER,
    recorded_at TEXT NOT NULL,
    received_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_points_device_recorded
    ON location_points(device_id, recorded_at);
CREATE INDEX IF NOT EXISTS idx_points_device_received
    ON location_points(device_id, received_at);

CREATE TABLE IF NOT EXISTS places (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    name TEXT,
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    radius_m REAL NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    visit_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_places_device ON places(device_id);

CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    place_id INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    FOREIGN KEY (place_id) REFERENCES places(id)
);

CREATE INDEX IF NOT EXISTS idx_visits_device_started
    ON visits(device_id, started_at);
CREATE INDEX IF NOT EXISTS idx_visits_device_ended
    ON visits(device_id, ended_at);

CREATE TABLE IF NOT EXISTS travel_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    from_visit_id INTEGER,
    to_visit_id INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    distance_m REAL NOT NULL,
    avg_speed_mps REAL,
    peak_speed_mps REAL,
    fast_distance_m REAL NOT NULL DEFAULT 0,
    fast_leg_count INTEGER NOT NULL DEFAULT 0,
    travel_mode TEXT
);

CREATE INDEX IF NOT EXISTS idx_travel_device_started
    ON travel_segments(device_id, started_at);
CREATE INDEX IF NOT EXISTS idx_travel_device_ended
    ON travel_segments(device_id, ended_at);

CREATE TABLE IF NOT EXISTS analytics_dirty_days (
    device_id TEXT NOT NULL,
    day TEXT NOT NULL,
    reason TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (device_id, day)
);

CREATE TABLE IF NOT EXISTS analytics_meta (
    device_id TEXT PRIMARY KEY,
    last_computed_at TEXT NOT NULL,
    last_point_recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS daily_stats (
    device_id TEXT NOT NULL,
    day TEXT NOT NULL,
    point_count INTEGER NOT NULL DEFAULT 0,
    visits_count INTEGER NOT NULL DEFAULT 0,
    places_visited_count INTEGER NOT NULL DEFAULT 0,
    stationary_duration_sec INTEGER NOT NULL DEFAULT 0,
    travel_duration_sec INTEGER NOT NULL DEFAULT 0,
    travel_distance_m REAL NOT NULL DEFAULT 0,
    travel_trips INTEGER NOT NULL DEFAULT 0,
    walked_distance_m REAL NOT NULL DEFAULT 0,
    ran_distance_m REAL NOT NULL DEFAULT 0,
    drove_distance_m REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (device_id, day)
);

CREATE INDEX IF NOT EXISTS idx_daily_stats_device_day
    ON daily_stats(device_id, day);

CREATE TABLE IF NOT EXISTS heatmap_bins (
    device_id TEXT NOT NULL,
    grid_lat INTEGER NOT NULL,
    grid_lon INTEGER NOT NULL,
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    point_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (device_id, grid_lat, grid_lon)
);

CREATE INDEX IF NOT EXISTS idx_heatmap_bins_device
    ON heatmap_bins(device_id);

CREATE TABLE IF NOT EXISTS device_settings (
    device_id TEXT PRIMARY KEY,
    auto_rename_places INTEGER NOT NULL DEFAULT 1,
    auto_rename_running INTEGER NOT NULL DEFAULT 0,
    auto_rename_started_at TEXT,
    auto_rename_finished_at TEXT,
    auto_rename_last_result TEXT
);

CREATE TABLE IF NOT EXISTS geocode_cache (
    cache_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'nominatim',
    raw_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_commands (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    command_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    delivered_at TEXT,
    acked_at TEXT,
    ack_latitude REAL,
    ack_longitude REAL,
    ack_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_commands_device_status
    ON device_commands(device_id, status, created_at);
"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _int_to_bool(value: Any) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = dict(row)
    data["battery_charging"] = _int_to_bool(data.get("battery_charging"))
    data["power_save_mode"] = _int_to_bool(data.get("power_save_mode"))
    return data


def init_db() -> None:
    config.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    bootstrap = sqlite3.connect(config.DATABASE_PATH, timeout=5)
    bootstrap.isolation_level = None
    bootstrap.execute("PRAGMA journal_mode=WAL")
    bootstrap.close()
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_device_settings(conn)
        _migrate_analytics_meta(conn)
        _migrate_device_commands(conn)
        _migrate_travel_segments(conn)
        _migrate_daily_stats(conn)
        conn.commit()


def _migrate_analytics_meta(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(analytics_meta)")}
    additions = {
        "lifetime_stats_json": "TEXT",
        "lifetime_stats_point_at": "TEXT",
        "daily_stats_point_at": "TEXT",
        "heatmap_bins_point_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE analytics_meta ADD COLUMN {name} {ddl}")


def _migrate_device_settings(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(device_settings)")}
    additions = {
        "auto_rename_running": "INTEGER NOT NULL DEFAULT 0",
        "auto_rename_started_at": "TEXT",
        "auto_rename_finished_at": "TEXT",
        "auto_rename_last_result": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE device_settings ADD COLUMN {name} {ddl}")


def _migrate_travel_segments(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(travel_segments)")}
    additions = {
        "peak_speed_mps": "REAL",
        "fast_distance_m": "REAL NOT NULL DEFAULT 0",
        "fast_leg_count": "INTEGER NOT NULL DEFAULT 0",
        "travel_mode": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE travel_segments ADD COLUMN {name} {ddl}")


def _migrate_daily_stats(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(daily_stats)")}
    additions = {
        "walked_distance_m": "REAL NOT NULL DEFAULT 0",
        "ran_distance_m": "REAL NOT NULL DEFAULT 0",
        "drove_distance_m": "REAL NOT NULL DEFAULT 0",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE daily_stats ADD COLUMN {name} {ddl}")


def _migrate_device_commands(conn: sqlite3.Connection) -> None:
    columns = {row[1] for row in conn.execute("PRAGMA table_info(device_commands)")}
    additions = {
        "duration_sec": "INTEGER NOT NULL DEFAULT 30",
        "stop_requested_at": "TEXT",
        "stopped_by": "TEXT",
        "ring_started_at": "TEXT",
    }
    for name, ddl in additions.items():
        if name not in columns:
            conn.execute(f"ALTER TABLE device_commands ADD COLUMN {name} {ddl}")


def get_auto_rename_enabled(device_id: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT auto_rename_places FROM device_settings WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    if row is None:
        return True
    return bool(row["auto_rename_places"])


def set_auto_rename_enabled(device_id: str, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_settings (device_id, auto_rename_places)
            VALUES (?, ?)
            ON CONFLICT(device_id) DO UPDATE SET auto_rename_places = excluded.auto_rename_places
            """,
            (device_id, 1 if enabled else 0),
        )
        conn.commit()


def try_begin_auto_rename_run(device_id: str) -> bool:
    """Mark auto-rename as running. Returns False if a run is already in progress."""
    now = utc_now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT auto_rename_running FROM device_settings WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if row is not None and row["auto_rename_running"]:
            return False
        conn.execute(
            """
            INSERT INTO device_settings (
                device_id, auto_rename_places, auto_rename_running, auto_rename_started_at
            ) VALUES (?, 1, 1, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                auto_rename_running = 1,
                auto_rename_started_at = excluded.auto_rename_started_at
            """,
            (device_id, now),
        )
        conn.commit()
    return True


def finish_auto_rename_run(device_id: str, result: dict[str, Any]) -> None:
    import json

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE device_settings
            SET auto_rename_running = 0,
                auto_rename_finished_at = ?,
                auto_rename_last_result = ?
            WHERE device_id = ?
            """,
            (utc_now_iso(), json.dumps(result), device_id),
        )
        conn.commit()


def get_auto_rename_status(device_id: str) -> dict[str, Any]:
    import json

    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM device_settings WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    if row is None:
        return {
            "device_id": device_id,
            "running": False,
            "started_at": None,
            "finished_at": None,
            "last_result": None,
        }
    data = dict(row)
    last_result = None
    if data.get("auto_rename_last_result"):
        try:
            last_result = json.loads(data["auto_rename_last_result"])
        except json.JSONDecodeError:
            last_result = None
    return {
        "device_id": device_id,
        "running": bool(data.get("auto_rename_running")),
        "started_at": data.get("auto_rename_started_at"),
        "finished_at": data.get("auto_rename_finished_at"),
        "last_result": last_result,
    }


def get_geocode_cache(cache_key: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM geocode_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    return dict(row) if row else None


def set_geocode_cache(cache_key: str, label: str, raw_payload: dict[str, Any]) -> None:
    import json

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO geocode_cache (cache_key, label, source, raw_json, created_at)
            VALUES (?, ?, 'nominatim', ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                label = excluded.label,
                raw_json = excluded.raw_json,
                created_at = excluded.created_at
            """,
            (cache_key, label, json.dumps(raw_payload), utc_now_iso()),
        )
        conn.commit()


def set_place_names_if_null(device_id: str, place_ids: list[int], name: str) -> int:
    if not place_ids:
        return 0
    placeholders = ",".join("?" for _ in place_ids)
    params: list[Any] = [name, device_id, *place_ids]
    with get_connection() as conn:
        cursor = conn.execute(
            f"""
            UPDATE places
            SET name = ?
            WHERE device_id = ?
              AND name IS NULL
              AND id IN ({placeholders})
            """,
            params,
        )
        conn.commit()
        return cursor.rowcount


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection and commit on success.

    isolation_level=None makes transactions explicit, so this behaves the same
    on Python versions whose sqlite3 default is autocommit or implicit.
    """
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False, timeout=5)
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("BEGIN")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def insert_points(
    device_id: str,
    points: list[LocationPointIn],
) -> tuple[int, int, list[str]]:
    accepted = 0
    duplicates = 0
    errors: list[str] = []
    accepted_points: list[LocationPointIn] = []
    received_at = utc_now_iso()

    insert_sql = """
        INSERT OR IGNORE INTO location_points (
            device_id, client_point_id, latitude, longitude,
            accuracy_m, altitude_m, speed_mps, bearing_deg,
            location_provider, activity, battery_pct, battery_charging,
            power_save_mode, network_type, wifi_ssid, cell_signal_dbm,
            app_version, upload_attempt, queued_duration_sec,
            recorded_at, received_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
    """

    with get_connection() as conn:
        for point in points:
            try:
                cursor = conn.execute(
                    insert_sql,
                    (
                        device_id,
                        point.client_point_id,
                        point.latitude,
                        point.longitude,
                        point.accuracy_m,
                        point.altitude_m,
                        point.speed_mps,
                        point.bearing_deg,
                        point.location_provider,
                        point.activity,
                        point.battery_pct,
                        _bool_to_int(point.battery_charging),
                        _bool_to_int(point.power_save_mode),
                        point.network_type,
                        point.wifi_ssid,
                        point.cell_signal_dbm,
                        point.app_version,
                        point.upload_attempt,
                        point.queued_duration_sec,
                        point.recorded_at,
                        received_at,
                    ),
                )
                if cursor.rowcount == 1:
                    accepted += 1
                    accepted_points.append(point)
                else:
                    duplicates += 1
            except sqlite3.Error as exc:
                errors.append(f"{point.client_point_id}: {exc}")
        if accepted_points:
            # Raw points are already inserted above and are never deleted.
            # Record which local days need aggregate repair, then commit
            # before the repair so a sync failure cannot roll the points back.
            from app.analytics.sync import record_accepted_points

            record_accepted_points(conn, device_id, accepted_points)
        conn.commit()

    if accepted_points:
        try:
            from app.analytics.sync import sync_device

            sync_device(device_id)
        except Exception:
            logger.exception(
                "aggregate sync failed after accepting %s points for device=%s",
                len(accepted_points),
                device_id,
            )

    return accepted, duplicates, errors


def get_latest_point(device_id: str) -> LocationPointOut | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM location_points
            WHERE device_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
    if row is None:
        return None
    return LocationPointOut.from_row(_row_to_dict(row))


def get_history(
    device_id: str,
    from_ts: str | None = None,
    to_ts: str | None = None,
    limit: int = 500,
    offset: int = 0,
    order: str = "asc",
    sample: bool = True,
) -> tuple[list[LocationPointOut], int, bool]:
    clauses = ["device_id = ?"]
    params: list[Any] = [device_id]

    if from_ts:
        clauses.append("recorded_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("recorded_at <= ?")
        params.append(to_ts)

    where_sql = " AND ".join(clauses)
    order_dir = "DESC" if order == "desc" else "ASC"

    with get_connection() as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM location_points WHERE {where_sql}",
            params,
        ).fetchone()[0]

        if total == 0:
            return [], 0, False

        if not sample:
            rows = conn.execute(
                f"""
                SELECT {HISTORY_POINT_COLUMNS}
                FROM location_points
                WHERE {where_sql}
                ORDER BY recorded_at {order_dir}, id {order_dir}
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
            return [LocationPointOut.from_row(_row_to_dict(row)) for row in rows], total, False

        if total <= limit:
            rows = conn.execute(
                f"""
                SELECT {HISTORY_POINT_COLUMNS}
                FROM location_points
                WHERE {where_sql}
                ORDER BY recorded_at ASC, id ASC
                LIMIT ?
                """,
                [*params, limit],
            ).fetchall()
            return [LocationPointOut.from_row(_row_to_dict(row)) for row in rows], total, False

        step = max(1, (total + limit - 1) // limit)
        id_rows = conn.execute(
            f"""
            WITH numbered AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY recorded_at ASC, id ASC) AS rn
                FROM location_points
                WHERE {where_sql}
            )
            SELECT id FROM numbered
            WHERE ((rn - 1) % ?) = 0 OR rn = ?
            ORDER BY rn ASC
            """,
            [*params, step, total],
        ).fetchall()
        selected_ids = [row["id"] for row in id_rows]
        placeholders = ",".join("?" for _ in selected_ids)
        rows = conn.execute(
            f"""
            SELECT {HISTORY_POINT_COLUMNS}
            FROM location_points
            WHERE id IN ({placeholders})
            ORDER BY recorded_at ASC, id ASC
            """,
            selected_ids,
        ).fetchall()

    return [LocationPointOut.from_row(_row_to_dict(row)) for row in rows], total, True


def get_points_for_analytics(device_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT recorded_at, latitude, longitude, speed_mps
            FROM location_points
            WHERE device_id = ?
            ORDER BY recorded_at ASC, id ASC
            """,
            (device_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_dirty_days(device_id: str) -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT day FROM analytics_dirty_days
            WHERE device_id = ?
            ORDER BY day ASC
            """,
            (device_id,),
        ).fetchall()
    return [row["day"] for row in rows]


def list_devices_with_dirty_days() -> list[str]:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT DISTINCT device_id FROM analytics_dirty_days ORDER BY device_id ASC"
        ).fetchall()
    return [row["device_id"] for row in rows]


def clear_dirty_days(device_id: str, days: list[str]) -> None:
    if not days:
        return
    with get_connection() as conn:
        _clear_dirty_days(conn, device_id, days)
        conn.commit()


def _clear_dirty_days(conn: sqlite3.Connection, device_id: str, days: list[str]) -> None:
    placeholders = ",".join("?" for _ in days)
    conn.execute(
        f"""
        DELETE FROM analytics_dirty_days
        WHERE device_id = ? AND day IN ({placeholders})
        """,
        [device_id, *days],
    )


def point_token(
    device_id: str,
    start_bound: str | None = None,
    end_bound: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> tuple[int, int]:
    clauses = ["device_id = ?"]
    params: list[Any] = [device_id]
    if start_bound is not None:
        clauses.append("recorded_at >= ?")
        params.append(start_bound)
    if end_bound is not None:
        clauses.append("recorded_at < ?")
        params.append(end_bound)
    sql = f"""
        SELECT COUNT(*) AS c, COALESCE(MAX(id), 0) AS max_id
        FROM location_points
        WHERE {" AND ".join(clauses)}
    """
    if conn is None:
        with get_connection() as owned:
            row = owned.execute(sql, params).fetchone()
    else:
        row = conn.execute(sql, params).fetchone()
    return int(row["c"]), int(row["max_id"])


def count_location_points(device_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM location_points WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return int(row["c"])


def has_points_before(device_id: str, start_bound: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM location_points
            WHERE device_id = ? AND recorded_at < ?
            LIMIT 1
            """,
            (device_id, start_bound),
        ).fetchone()
    return row is not None


def count_visits(device_id: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM visits WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return int(row["c"])


def overlapping_segment_bounds(
    device_id: str,
    start_bound: str,
    end_bound: str,
) -> tuple[str | None, str | None]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT MIN(started_at) AS started_at, MAX(ended_at) AS ended_at
            FROM (
                SELECT started_at, ended_at FROM visits
                WHERE device_id = ? AND started_at < ? AND ended_at >= ?
                UNION ALL
                SELECT started_at, ended_at FROM travel_segments
                WHERE device_id = ? AND started_at < ? AND ended_at >= ?
            )
            """,
            (device_id, end_bound, start_bound, device_id, end_bound, start_bound),
        ).fetchone()
    if row is None or row["started_at"] is None:
        return None, None
    return row["started_at"], row["ended_at"]


def load_points_between(
    device_id: str,
    start_bound: str,
    end_bound: str,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT recorded_at, latitude, longitude, speed_mps
            FROM location_points
            WHERE device_id = ? AND recorded_at >= ? AND recorded_at < ?
            ORDER BY recorded_at ASC, id ASC
            """,
            (device_id, start_bound, end_bound),
        ).fetchall()
    return [dict(row) for row in rows]


def get_latest_point_recorded_at(device_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT recorded_at FROM location_points
            WHERE device_id = ?
            ORDER BY recorded_at DESC, id DESC
            LIMIT 1
            """,
            (device_id,),
        ).fetchone()
    return row["recorded_at"] if row else None


def get_analytics_meta(device_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return dict(row) if row else None


def _insert_travel_segment(
    conn: sqlite3.Connection,
    device_id: str,
    travel: Any,
    from_visit_id: int | None,
    to_visit_id: int | None,
) -> None:
    conn.execute(
        """
        INSERT INTO travel_segments (
            device_id, from_visit_id, to_visit_id, started_at, ended_at,
            duration_sec, distance_m, avg_speed_mps,
            peak_speed_mps, fast_distance_m, fast_leg_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            device_id,
            from_visit_id,
            to_visit_id,
            travel.started_at,
            travel.ended_at,
            travel.duration_sec,
            travel.distance_m,
            travel.avg_speed_mps,
            travel.peak_speed_mps,
            travel.fast_distance_m,
            travel.fast_leg_count,
        ),
    )


def _expand_sql_bounds(start_bound: str, end_bound: str, days: set[str] | list[str]) -> tuple[str, str]:
    """Widen a UTC window so it covers each local calendar day."""
    from datetime import date, time

    from app.analytics.daily_stats import local_tz

    tz = local_tz()
    for day_value in days:
        day = date.fromisoformat(day_value)
        day_start = datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        day_start_s = day_start.strftime("%Y-%m-%dT%H:%M:%S")
        day_end_s = day_end.strftime("%Y-%m-%dT%H:%M:%S")
        if day_start_s < start_bound:
            start_bound = day_start_s
        if day_end_s > end_bound:
            end_bound = day_end_s
    return start_bound, end_bound


def assign_travel_modes(conn: sqlite3.Connection, device_id: str) -> set[str]:
    """Label every stored trip. Returns local days whose label changed."""
    from app.analytics.daily_stats import iter_local_day_overlaps, iso_to_local_day
    from app.analytics.motion import MotionSegment, classify_modes

    rows = conn.execute(
        """
        SELECT
            id, started_at, ended_at, avg_speed_mps, peak_speed_mps,
            fast_distance_m, fast_leg_count, travel_mode
        FROM travel_segments
        WHERE device_id = ?
        ORDER BY started_at ASC, id ASC
        """,
        (device_id,),
    ).fetchall()
    modes = classify_modes(
        [
            MotionSegment(
                started_at=row["started_at"],
                ended_at=row["ended_at"],
                avg_speed_mps=row["avg_speed_mps"],
                peak_speed_mps=row["peak_speed_mps"],
                fast_distance_m=float(row["fast_distance_m"] or 0),
                fast_leg_count=int(row["fast_leg_count"] or 0),
            )
            for row in rows
        ]
    )
    changed_days: set[str] = set()
    for row, mode in zip(rows, modes):
        if row["travel_mode"] == mode:
            continue
        conn.execute(
            "UPDATE travel_segments SET travel_mode = ? WHERE id = ?",
            (mode, row["id"]),
        )
        overlaps = list(iter_local_day_overlaps(row["started_at"], row["ended_at"]))
        if overlaps:
            changed_days.update(day for day, _sec in overlaps)
        else:
            changed_days.add(iso_to_local_day(row["started_at"]))
    return changed_days


def backfill_travel_motion() -> int:
    """Measure existing trips from stored points and label them. Points are not changed."""
    with get_connection() as conn:
        device_ids = [
            row["device_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT device_id
                FROM travel_segments
                WHERE peak_speed_mps IS NULL OR travel_mode IS NULL
                """
            ).fetchall()
        ]
        measured = 0
        for device_id in device_ids:
            measured += _measure_unfilled_trips(conn, device_id)
            assign_travel_modes(conn, device_id)
            last_point = conn.execute(
                "SELECT MAX(recorded_at) AS recorded_at FROM location_points WHERE device_id = ?",
                (device_id,),
            ).fetchone()
            recorded_at = last_point["recorded_at"] if last_point else None
            if recorded_at:
                _rebuild_daily_stats(conn, device_id, recorded_at)
                _write_lifetime_stats(conn, device_id, recorded_at)
        if device_ids:
            logger.info(
                "travel mode backfill devices=%s segments_measured=%s",
                len(device_ids),
                measured,
            )
        return measured


def _measure_unfilled_trips(conn: sqlite3.Connection, device_id: str) -> int:
    import bisect

    from app.analytics.motion import measure_motion
    from app.analytics.periods import parse_iso

    points = conn.execute(
        """
        SELECT recorded_at, latitude, longitude
        FROM location_points
        WHERE device_id = ?
        ORDER BY recorded_at ASC, id ASC
        """,
        (device_id,),
    ).fetchall()
    times = [parse_iso(row["recorded_at"]) for row in points]
    segments = conn.execute(
        """
        SELECT id, started_at, ended_at
        FROM travel_segments
        WHERE device_id = ? AND peak_speed_mps IS NULL
        """,
        (device_id,),
    ).fetchall()
    for segment in segments:
        start = parse_iso(segment["started_at"])
        end = parse_iso(segment["ended_at"])
        begin = bisect.bisect_left(times, start)
        finish = bisect.bisect_right(times, end)
        chunk = [
            (row["recorded_at"], row["latitude"], row["longitude"])
            for row in points[begin:finish]
        ]
        peak, fast_distance_m, fast_leg_count = measure_motion(chunk)
        conn.execute(
            """
            UPDATE travel_segments
            SET peak_speed_mps = ?, fast_distance_m = ?, fast_leg_count = ?
            WHERE id = ?
            """,
            (peak, fast_distance_m, fast_leg_count, segment["id"]),
        )
    return len(segments)


def replace_analytics(
    device_id: str,
    visits: list[Any],
    travels: list[Any],
    place_drafts: list[Any],
    last_point_recorded_at: str | None,
) -> None:
    from app.analytics.constants import PLACE_CLUSTER_RADIUS_M
    from app.analytics.engine import assign_visit_place_ids
    from app.analytics.geo import haversine_m
    from app.analytics.travel_labels import is_local_loop_travel
    from app.analytics.travel_links import match_adjacent_visit_ids

    received_at = utc_now_iso()

    with get_connection() as conn:
        existing_places = conn.execute(
            "SELECT id, name, center_lat, center_lon FROM places WHERE device_id = ?",
            (device_id,),
        ).fetchall()

        conn.execute("DELETE FROM travel_segments WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM visits WHERE device_id = ?", (device_id,))
        conn.execute("DELETE FROM places WHERE device_id = ?", (device_id,))

        new_places: list[tuple[int, float, float, str | None]] = []

        for draft in place_drafts:
            name: str | None = None
            for existing in existing_places:
                if (
                    haversine_m(
                        draft.center_lat,
                        draft.center_lon,
                        existing["center_lat"],
                        existing["center_lon"],
                    )
                    < PLACE_CLUSTER_RADIUS_M
                ):
                    name = existing["name"]
                    break

            cursor = conn.execute(
                """
                INSERT INTO places (
                    device_id, name, center_lat, center_lon, radius_m,
                    first_seen_at, last_seen_at, visit_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    name,
                    draft.center_lat,
                    draft.center_lon,
                    draft.radius_m,
                    draft.first_seen_at,
                    draft.last_seen_at,
                    draft.visit_count,
                ),
            )
            new_id = cursor.lastrowid
            new_places.append((new_id, draft.center_lat, draft.center_lon, name))

        place_coords = [(pid, lat, lon) for pid, lat, lon, _ in new_places]
        assigned_place_ids = assign_visit_place_ids(visits, place_coords)

        inserted_visits: list[dict[str, Any]] = []
        for visit, place_id in zip(visits, assigned_place_ids):
            cursor = conn.execute(
                """
                INSERT INTO visits (
                    device_id, place_id, started_at, ended_at, duration_sec,
                    center_lat, center_lon
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    place_id,
                    visit.started_at,
                    visit.ended_at,
                    visit.duration_sec,
                    visit.center_lat,
                    visit.center_lon,
                ),
            )
            inserted_visits.append(
                {
                    "id": cursor.lastrowid,
                    "place_id": place_id,
                    "started_at": visit.started_at,
                    "ended_at": visit.ended_at,
                }
            )

        visits_by_id = {row["id"]: row for row in inserted_visits}

        for travel in travels:
            from_visit_id, to_visit_id = match_adjacent_visit_ids(
                travel.started_at,
                travel.ended_at,
                inserted_visits,
            )
            from_visit = visits_by_id.get(from_visit_id) if from_visit_id else None
            to_visit = visits_by_id.get(to_visit_id) if to_visit_id else None
            if from_visit and to_visit and is_local_loop_travel(
                from_place_id=from_visit.get("place_id"),
                to_place_id=to_visit.get("place_id"),
                distance_m=travel.distance_m,
            ):
                continue
            _insert_travel_segment(conn, device_id, travel, from_visit_id, to_visit_id)

        assign_travel_modes(conn, device_id)
        conn.execute(
            """
            INSERT INTO analytics_meta (device_id, last_computed_at, last_point_recorded_at)
            VALUES (?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                last_computed_at = excluded.last_computed_at,
                last_point_recorded_at = excluded.last_point_recorded_at
            """,
            (device_id, received_at, last_point_recorded_at),
        )
        if last_point_recorded_at is not None:
            _rebuild_daily_stats(conn, device_id, last_point_recorded_at)
            _write_lifetime_stats(conn, device_id, last_point_recorded_at)
            _rebuild_heatmap_bins(conn, device_id, last_point_recorded_at)
        conn.commit()


def mark_dirty_days(
    conn: sqlite3.Connection,
    device_id: str,
    days: list[str],
    reason: str,
) -> None:
    now = utc_now_iso()
    for day in sorted(set(days)):
        conn.execute(
            """
            INSERT INTO analytics_dirty_days (device_id, day, reason, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(device_id, day) DO UPDATE SET
                reason = excluded.reason,
                updated_at = excluded.updated_at
            """,
            (device_id, day, reason, now),
        )


def increment_heatmap_bins(
    conn: sqlite3.Connection,
    device_id: str,
    points: list[tuple[float, float, str]],
) -> None:
    """Add newly accepted points to heatmap bins. Points are insert-only, so this never subtracts."""
    from app.analytics.heatmap_bins import point_to_grid

    for latitude, longitude, recorded_at in points:
        grid_lat, grid_lon = point_to_grid(latitude, longitude)
        conn.execute(
            """
            INSERT INTO heatmap_bins (
                device_id, grid_lat, grid_lon, center_lat, center_lon,
                point_count, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(device_id, grid_lat, grid_lon) DO UPDATE SET
                point_count = heatmap_bins.point_count + 1,
                center_lat = (
                    heatmap_bins.center_lat * heatmap_bins.point_count + excluded.center_lat
                ) / (heatmap_bins.point_count + 1),
                center_lon = (
                    heatmap_bins.center_lon * heatmap_bins.point_count + excluded.center_lon
                ) / (heatmap_bins.point_count + 1),
                first_seen_at = MIN(heatmap_bins.first_seen_at, excluded.first_seen_at),
                last_seen_at = MAX(heatmap_bins.last_seen_at, excluded.last_seen_at)
            """,
            (device_id, grid_lat, grid_lon, latitude, longitude, recorded_at, recorded_at),
        )


def set_heatmap_marker(conn: sqlite3.Connection, device_id: str, recorded_at: str) -> None:
    conn.execute(
        """
        INSERT INTO analytics_meta (device_id, last_computed_at, heatmap_bins_point_at)
        VALUES (?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            heatmap_bins_point_at = excluded.heatmap_bins_point_at
        """,
        (device_id, utc_now_iso(), recorded_at),
    )


def apply_window_analytics(
    conn: sqlite3.Connection,
    device_id: str,
    visits: list[Any],
    travels: list[Any],
    start_bound: str,
    end_bound: str,
    refresh_days: list[str],
    latest_point_recorded_at: str,
) -> int:
    """Replace derived visits and travel that overlap one time window.

    location_points is not modified. Existing place ids and names are kept.
    """
    from app.analytics.engine import assign_visit_place_ids, cluster_places
    from app.analytics.travel_labels import is_local_loop_travel
    from app.analytics.travel_links import match_adjacent_visit_ids

    conn.execute(
        """
        DELETE FROM travel_segments
        WHERE device_id = ? AND started_at < ? AND ended_at >= ?
        """,
        (device_id, end_bound, start_bound),
    )
    conn.execute(
        """
        DELETE FROM visits
        WHERE device_id = ? AND started_at < ? AND ended_at >= ?
        """,
        (device_id, end_bound, start_bound),
    )

    existing_places = conn.execute(
        "SELECT id, center_lat, center_lon FROM places WHERE device_id = ?",
        (device_id,),
    ).fetchall()
    place_coords = [(row["id"], row["center_lat"], row["center_lon"]) for row in existing_places]
    assigned = assign_visit_place_ids(visits, place_coords)
    unmatched_indexes = [index for index, place_id in enumerate(assigned) if place_id is None]
    new_place_count = 0
    if unmatched_indexes:
        unmatched_visits = [visits[index] for index in unmatched_indexes]
        new_coords: list[tuple[int, float, float]] = []
        for draft in cluster_places(unmatched_visits):
            cursor = conn.execute(
                """
                INSERT INTO places (
                    device_id, name, center_lat, center_lon, radius_m,
                    first_seen_at, last_seen_at, visit_count
                ) VALUES (?, NULL, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    draft.center_lat,
                    draft.center_lon,
                    draft.radius_m,
                    draft.first_seen_at,
                    draft.last_seen_at,
                    draft.visit_count,
                ),
            )
            new_place_count += 1
            new_coords.append((int(cursor.lastrowid), draft.center_lat, draft.center_lon))
        remapped = assign_visit_place_ids(unmatched_visits, new_coords)
        for index, place_id in zip(unmatched_indexes, remapped):
            assigned[index] = place_id

    for visit, place_id in zip(visits, assigned):
        conn.execute(
            """
            INSERT INTO visits (
                device_id, place_id, started_at, ended_at, duration_sec,
                center_lat, center_lon
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                place_id,
                visit.started_at,
                visit.ended_at,
                visit.duration_sec,
                visit.center_lat,
                visit.center_lon,
            ),
        )

    all_visits = [
        dict(row)
        for row in conn.execute(
            """
            SELECT id, place_id, started_at, ended_at
            FROM visits
            WHERE device_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (device_id,),
        ).fetchall()
    ]
    visits_by_id = {row["id"]: row for row in all_visits}
    for travel in travels:
        from_visit_id, to_visit_id = match_adjacent_visit_ids(
            travel.started_at,
            travel.ended_at,
            all_visits,
        )
        from_visit = visits_by_id.get(from_visit_id) if from_visit_id else None
        to_visit = visits_by_id.get(to_visit_id) if to_visit_id else None
        if from_visit and to_visit and is_local_loop_travel(
            from_place_id=from_visit.get("place_id"),
            to_place_id=to_visit.get("place_id"),
            distance_m=travel.distance_m,
        ):
            continue
        _insert_travel_segment(conn, device_id, travel, from_visit_id, to_visit_id)

    changed_days = assign_travel_modes(conn, device_id)
    if changed_days:
        refresh_days = sorted(set(refresh_days) | changed_days)
        start_bound, end_bound = _expand_sql_bounds(start_bound, end_bound, changed_days)

    conn.execute(
        """
        UPDATE places
        SET visit_count = (
                SELECT COUNT(*) FROM visits AS visit WHERE visit.place_id = places.id
            ),
            first_seen_at = COALESCE(
                (SELECT MIN(visit.started_at) FROM visits AS visit WHERE visit.place_id = places.id),
                first_seen_at
            ),
            last_seen_at = COALESCE(
                (SELECT MAX(visit.ended_at) FROM visits AS visit WHERE visit.place_id = places.id),
                last_seen_at
            )
        WHERE device_id = ?
        """,
        (device_id,),
    )
    conn.execute(
        """
        DELETE FROM places
        WHERE device_id = ?
          AND name IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM visits AS visit WHERE visit.place_id = places.id
          )
        """,
        (device_id,),
    )
    conn.execute(
        """
        INSERT INTO analytics_meta (device_id, last_computed_at, last_point_recorded_at)
        VALUES (?, ?, ?)
        ON CONFLICT(device_id) DO UPDATE SET
            last_computed_at = excluded.last_computed_at,
            last_point_recorded_at = excluded.last_point_recorded_at
        """,
        (device_id, utc_now_iso(), latest_point_recorded_at),
    )
    _replace_daily_stats_for_days(
        conn,
        device_id,
        refresh_days,
        start_bound,
        end_bound,
        latest_point_recorded_at,
    )
    _write_lifetime_stats(conn, device_id, latest_point_recorded_at)
    return new_place_count


def _replace_daily_stats_for_days(
    conn: sqlite3.Connection,
    device_id: str,
    days: list[str],
    start_bound: str,
    end_bound: str,
    latest_point_recorded_at: str,
) -> None:
    from app.analytics.daily_stats import compute_daily_stats_rows

    if not days:
        return
    visits = [
        dict(row)
        for row in conn.execute(
            """
            SELECT place_id, started_at, ended_at, duration_sec
            FROM visits
            WHERE device_id = ? AND started_at < ? AND ended_at >= ?
            """,
            (device_id, end_bound, start_bound),
        ).fetchall()
    ]
    travels = [
        dict(row)
        for row in conn.execute(
            """
            SELECT started_at, ended_at, duration_sec, distance_m, travel_mode
            FROM travel_segments
            WHERE device_id = ? AND started_at < ? AND ended_at >= ?
            """,
            (device_id, end_bound, start_bound),
        ).fetchall()
    ]
    points = [
        dict(row)
        for row in conn.execute(
            """
            SELECT recorded_at
            FROM location_points
            WHERE device_id = ? AND recorded_at >= ? AND recorded_at < ?
            """,
            (device_id, start_bound, end_bound),
        ).fetchall()
    ]
    rows_by_day = {row["day"]: row for row in compute_daily_stats_rows(visits, travels, points)}
    for day in days:
        conn.execute(
            "DELETE FROM daily_stats WHERE device_id = ? AND day = ?",
            (device_id, day),
        )
        row = rows_by_day.get(day)
        if row is None:
            continue
        conn.execute(
            """
            INSERT INTO daily_stats (
                device_id, day, point_count, visits_count, places_visited_count,
                stationary_duration_sec, travel_duration_sec, travel_distance_m, travel_trips,
                walked_distance_m, ran_distance_m, drove_distance_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                row["day"],
                row["point_count"],
                row["visits_count"],
                row["places_visited_count"],
                row["stationary_duration_sec"],
                row["travel_duration_sec"],
                row["travel_distance_m"],
                row["travel_trips"],
                row["walked_distance_m"],
                row["ran_distance_m"],
                row["drove_distance_m"],
            ),
        )
    conn.execute(
        """
        UPDATE analytics_meta
        SET daily_stats_point_at = ?
        WHERE device_id = ?
        """,
        (latest_point_recorded_at, device_id),
    )


def get_places(device_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM places
            WHERE device_id = ?
            ORDER BY last_seen_at DESC, id DESC
            """,
            (device_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_place_name(place_id: int, device_id: str, name: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM places WHERE id = ? AND device_id = ?",
            (place_id, device_id),
        ).fetchone()
        if row is None:
            return None
        conn.execute(
            "UPDATE places SET name = ? WHERE id = ? AND device_id = ?",
            (name, place_id, device_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM places WHERE id = ?",
            (place_id,),
        ).fetchone()
    return dict(updated) if updated else None


def _time_range_clause(
    from_iso: str | None,
    to_iso: str | None,
    column_start: str = "started_at",
) -> tuple[str, list[Any]]:
    """Filter segments whose start time falls within the range (calendar-period strict)."""
    clauses: list[str] = []
    params: list[Any] = []
    if from_iso:
        clauses.append(f"{column_start} >= ?")
        params.append(from_iso)
    if to_iso:
        clauses.append(f"{column_start} <= ?")
        params.append(to_iso)
    if not clauses:
        return "", []
    return " AND " + " AND ".join(clauses), params


def get_visits(
    device_id: str,
    from_iso: str | None = None,
    to_iso: str | None = None,
    limit: int | None = 500,
) -> list[dict[str, Any]]:
    range_sql, range_params = _time_range_clause(from_iso, to_iso)
    params: list[Any] = [device_id, *range_params]
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM visits
            WHERE device_id = ?{range_sql}
            ORDER BY started_at ASC, id ASC
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_all_visits(device_id: str) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM visits
            WHERE device_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (device_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_travel_segments(
    device_id: str,
    from_iso: str | None = None,
    to_iso: str | None = None,
    limit: int | None = 500,
    order: str = "asc",
) -> list[dict[str, Any]]:
    range_sql, range_params = _time_range_clause(from_iso, to_iso)
    params: list[Any] = [device_id, *range_params]
    order_sql = "DESC" if order.lower() == "desc" else "ASC"
    limit_sql = ""
    if limit is not None:
        limit_sql = " LIMIT ?"
        params.append(limit)
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM travel_segments
            WHERE device_id = ?{range_sql}
            ORDER BY started_at {order_sql}, id {order_sql}
            {limit_sql}
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


COMMAND_EXPIRY_MINUTES = 15
COMMAND_RATE_LIMIT_SECONDS = 30


def _parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def _expire_stale_commands(conn: sqlite3.Connection, device_id: str | None = None) -> None:
    now = datetime.now(timezone.utc)
    now_iso = utc_now_iso()
    if device_id is None:
        conn.execute(
            "UPDATE device_commands SET status = 'expired' WHERE status IN ('pending', 'delivered') AND expires_at < ?",
            (now_iso,),
        )
        ringing_rows = conn.execute(
            "SELECT id, ring_started_at, duration_sec FROM device_commands WHERE status = 'ringing'",
        ).fetchall()
    else:
        conn.execute(
            """
            UPDATE device_commands
            SET status = 'expired'
            WHERE device_id = ? AND status IN ('pending', 'delivered') AND expires_at < ?
            """,
            (device_id, now_iso),
        )
        ringing_rows = conn.execute(
            """
            SELECT id, ring_started_at, duration_sec FROM device_commands
            WHERE device_id = ? AND status = 'ringing'
            """,
            (device_id,),
        ).fetchall()
    for row in ringing_rows:
        started_at = row["ring_started_at"]
        if not started_at:
            continue
        duration_sec = row["duration_sec"] or 30
        elapsed = (now - _parse_iso(started_at)).total_seconds()
        if elapsed > duration_sec + 120:
            conn.execute(
                """
                UPDATE device_commands
                SET status = 'completed',
                    acked_at = ?,
                    ack_message = COALESCE(ack_message, 'auto-completed (no phone ack)')
                WHERE id = ? AND status = 'ringing'
                """,
                (now_iso, row["id"]),
            )


def create_device_command(
    device_id: str,
    command_type: str = "ring",
    *,
    duration_sec: int = 30,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with get_connection() as conn:
        _expire_stale_commands(conn, device_id)
        recent = conn.execute(
            """
            SELECT created_at FROM device_commands
            WHERE device_id = ? AND command_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (device_id, command_type),
        ).fetchone()
        if recent is not None:
            created = datetime.fromisoformat(recent["created_at"].replace("Z", "+00:00"))
            if (now - created).total_seconds() < COMMAND_RATE_LIMIT_SECONDS:
                raise ValueError("ring rate limit")

        command_id = str(uuid.uuid4())
        created_at = utc_now_iso()
        expires_at = (now + timedelta(minutes=COMMAND_EXPIRY_MINUTES)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        conn.execute(
            """
            INSERT INTO device_commands (
                id, device_id, command_type, status, created_at, expires_at, duration_sec
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?)
            """,
            (command_id, device_id, command_type, created_at, expires_at, duration_sec),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM device_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
    return dict(row)


def get_device_command(command_id: str, device_id: str) -> dict[str, Any] | None:
    with get_connection() as conn:
        _expire_stale_commands(conn, device_id)
        row = conn.execute(
            "SELECT * FROM device_commands WHERE id = ? AND device_id = ?",
            (command_id, device_id),
        ).fetchone()
    return dict(row) if row else None


def claim_pending_commands(device_id: str) -> list[dict[str, Any]]:
    now = utc_now_iso()
    with get_connection() as conn:
        _expire_stale_commands(conn, device_id)
        rows = conn.execute(
            """
            SELECT * FROM device_commands
            WHERE device_id = ? AND status = 'pending' AND expires_at >= ?
            ORDER BY created_at ASC
            """,
            (device_id, now),
        ).fetchall()
        if not rows:
            return []
        ids = [row["id"] for row in rows]
        placeholders = ",".join("?" for _ in ids)
        conn.execute(
            f"""
            UPDATE device_commands
            SET status = 'delivered', delivered_at = ?
            WHERE id IN ({placeholders}) AND status = 'pending'
            """,
            (now, *ids),
        )
        conn.commit()
        delivered = conn.execute(
            f"""
            SELECT * FROM device_commands
            WHERE id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            tuple(ids),
        ).fetchall()
    return [dict(row) for row in delivered]


def start_ring_command(command_id: str, device_id: str) -> dict[str, Any] | None:
    now = utc_now_iso()
    with get_connection() as conn:
        _expire_stale_commands(conn, device_id)
        row = conn.execute(
            "SELECT * FROM device_commands WHERE id = ? AND device_id = ?",
            (command_id, device_id),
        ).fetchone()
        if row is None:
            return None
        if row["status"] == "ringing":
            return dict(row)
        if row["status"] not in ("pending", "delivered"):
            return dict(row)
        conn.execute(
            """
            UPDATE device_commands
            SET status = 'ringing',
                ring_started_at = ?,
                delivered_at = COALESCE(delivered_at, ?)
            WHERE id = ? AND device_id = ?
            """,
            (now, now, command_id, device_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM device_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
    return dict(updated) if updated else None


def request_command_stop(command_id: str, device_id: str) -> dict[str, Any] | None:
    now = utc_now_iso()
    with get_connection() as conn:
        _expire_stale_commands(conn, device_id)
        row = conn.execute(
            "SELECT * FROM device_commands WHERE id = ? AND device_id = ?",
            (command_id, device_id),
        ).fetchone()
        if row is None:
            return None
        if row["status"] not in ("pending", "delivered", "ringing"):
            return dict(row)
        conn.execute(
            """
            UPDATE device_commands
            SET stop_requested_at = ?
            WHERE id = ? AND device_id = ?
            """,
            (now, command_id, device_id),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM device_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
    return dict(updated) if updated else None


def ack_device_command(
    command_id: str,
    device_id: str,
    *,
    latitude: float | None = None,
    longitude: float | None = None,
    message: str | None = None,
    stopped_by: str | None = None,
) -> dict[str, Any] | None:
    now = utc_now_iso()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM device_commands WHERE id = ? AND device_id = ?",
            (command_id, device_id),
        ).fetchone()
        if row is None:
            return None
        if row["status"] in ("stopped", "completed", "acked", "expired"):
            return dict(row)
        if row["status"] not in ("pending", "delivered", "ringing"):
            return dict(row)
        if stopped_by in ("web", "phone"):
            final_status = "stopped"
            final_stopped_by = stopped_by
        elif stopped_by == "completed":
            final_status = "completed"
            final_stopped_by = None
        else:
            final_status = "acked"
            final_stopped_by = None
        conn.execute(
            """
            UPDATE device_commands
            SET status = ?,
                stopped_by = ?,
                acked_at = ?,
                ack_latitude = ?,
                ack_longitude = ?,
                ack_message = ?,
                delivered_at = COALESCE(delivered_at, ?)
            WHERE id = ? AND device_id = ?
            """,
            (
                final_status,
                final_stopped_by,
                now,
                latitude,
                longitude,
                message,
                now,
                command_id,
                device_id,
            ),
        )
        conn.commit()
        updated = conn.execute(
            "SELECT * FROM device_commands WHERE id = ?",
            (command_id,),
        ).fetchone()
    return dict(updated) if updated else None


def _empty_lifetime_stats(device_id: str) -> dict[str, Any]:
    return {
        "device_id": device_id,
        "first_point_at": None,
        "last_point_at": None,
        "calendar_days": 0,
        "days_with_data": 0,
        "days_without_data": 0,
        "point_count": 0,
        "places_count": 0,
        "places_visited_count": 0,
        "visits_count": 0,
        "travel_trips": 0,
        "stationary_duration_sec": 0,
        "travel_duration_sec": 0,
        "travel_distance_m": 0.0,
        "walked_distance_m": 0.0,
        "ran_distance_m": 0.0,
        "drove_distance_m": 0.0,
        "top_places": [],
        "top_place": None,
    }


def _tracking_day_counts(
    conn: sqlite3.Connection,
    device_id: str,
    first_point_at: str,
    last_point_at: str,
    utc_days_with_data: int,
) -> tuple[int, int, int]:
    from app.analytics.daily_stats import local_tz
    from app.analytics.periods import parse_iso

    tz = local_tz()
    first_day = parse_iso(first_point_at).astimezone(tz).date()
    last_day = parse_iso(last_point_at).astimezone(tz).date()
    calendar_days = (last_day - first_day).days + 1

    days_with_data = conn.execute(
        """
        SELECT COUNT(*) AS c
        FROM daily_stats
        WHERE device_id = ? AND point_count > 0
        """,
        (device_id,),
    ).fetchone()["c"]
    days_with_data = int(days_with_data)
    if days_with_data == 0 and calendar_days > 0:
        days_with_data = min(calendar_days, max(utc_days_with_data, 1))

    days_without_data = max(0, calendar_days - days_with_data)
    return calendar_days, days_with_data, days_without_data


def _compute_lifetime_stats(conn: sqlite3.Connection, device_id: str) -> dict[str, Any]:
    point_row = conn.execute(
        """
        SELECT
            MIN(recorded_at) AS first_point_at,
            MAX(recorded_at) AS last_point_at,
            COUNT(*) AS point_count,
            COUNT(DISTINCT substr(recorded_at, 1, 10)) AS days_with_data
        FROM location_points
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchone()
    if point_row is None or point_row["point_count"] == 0:
        return _empty_lifetime_stats(device_id)

    visit_row = conn.execute(
        """
        SELECT
            COUNT(*) AS visits_count,
            COALESCE(SUM(duration_sec), 0) AS stationary_duration_sec,
            COUNT(DISTINCT place_id) AS places_visited_count
        FROM visits
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchone()
    places_count = conn.execute(
        "SELECT COUNT(*) AS c FROM places WHERE device_id = ?",
        (device_id,),
    ).fetchone()["c"]
    travel_row = conn.execute(
        """
        SELECT
            COUNT(*) AS travel_trips,
            COALESCE(SUM(duration_sec), 0) AS travel_duration_sec,
            COALESCE(SUM(distance_m), 0) AS travel_distance_m,
            COALESCE(SUM(CASE WHEN travel_mode = 'walking' THEN distance_m ELSE 0 END), 0) AS walked_distance_m,
            COALESCE(SUM(CASE WHEN travel_mode = 'running' THEN distance_m ELSE 0 END), 0) AS ran_distance_m,
            COALESCE(SUM(CASE WHEN travel_mode = 'vehicle' THEN distance_m ELSE 0 END), 0) AS drove_distance_m
        FROM travel_segments
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchone()

    place_rows = conn.execute(
        "SELECT id, name FROM places WHERE device_id = ?",
        (device_id,),
    ).fetchall()
    places_by_id = {row["id"]: row for row in place_rows}

    top_rows = conn.execute(
        """
        SELECT place_id, SUM(duration_sec) AS duration_sec
        FROM visits
        WHERE device_id = ? AND place_id IS NOT NULL
        GROUP BY place_id
        ORDER BY duration_sec DESC
        LIMIT 10
        """,
        (device_id,),
    ).fetchall()

    stationary_sec = int(visit_row["stationary_duration_sec"])
    top_places: list[dict[str, Any]] = []
    for row in top_rows:
        place_id = int(row["place_id"])
        duration_sec = int(row["duration_sec"])
        place = places_by_id.get(place_id)
        name = place["name"] if place and place["name"] else f"Place {place_id}"
        top_places.append(
            {
                "place_id": place_id,
                "name": name,
                "duration_sec": duration_sec,
            }
        )

    top_place = None
    if top_places and stationary_sec > 0:
        leader = top_places[0]
        top_place = {
            "place_id": leader["place_id"],
            "name": leader["name"],
            "duration_sec": leader["duration_sec"],
            "share_pct": round(leader["duration_sec"] / stationary_sec * 100),
        }

    calendar_days, days_with_data, days_without_data = _tracking_day_counts(
        conn,
        device_id,
        point_row["first_point_at"],
        point_row["last_point_at"],
        int(point_row["days_with_data"]),
    )

    return {
        "device_id": device_id,
        "first_point_at": point_row["first_point_at"],
        "last_point_at": point_row["last_point_at"],
        "calendar_days": calendar_days,
        "days_with_data": days_with_data,
        "days_without_data": days_without_data,
        "point_count": int(point_row["point_count"]),
        "places_count": int(places_count),
        "places_visited_count": int(visit_row["places_visited_count"] or 0),
        "visits_count": int(visit_row["visits_count"]),
        "travel_trips": int(travel_row["travel_trips"]),
        "stationary_duration_sec": stationary_sec,
        "travel_duration_sec": int(travel_row["travel_duration_sec"]),
        "travel_distance_m": float(travel_row["travel_distance_m"]),
        "walked_distance_m": float(travel_row["walked_distance_m"]),
        "ran_distance_m": float(travel_row["ran_distance_m"]),
        "drove_distance_m": float(travel_row["drove_distance_m"]),
        "top_places": top_places,
        "top_place": top_place,
    }


def _write_lifetime_stats(
    conn: sqlite3.Connection,
    device_id: str,
    last_point_recorded_at: str,
) -> dict[str, Any]:
    stats = _compute_lifetime_stats(conn, device_id)
    conn.execute(
        """
        UPDATE analytics_meta
        SET lifetime_stats_json = ?, lifetime_stats_point_at = ?
        WHERE device_id = ?
        """,
        (json.dumps(stats), last_point_recorded_at, device_id),
    )
    return stats


def rebuild_lifetime_stats(device_id: str) -> dict[str, Any]:
    last_point = get_latest_point_recorded_at(device_id)
    if last_point is None:
        return _empty_lifetime_stats(device_id)
    with get_connection() as conn:
        meta = conn.execute(
            "SELECT device_id FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if meta is None:
            conn.execute(
                """
                INSERT INTO analytics_meta (device_id, last_computed_at, last_point_recorded_at)
                VALUES (?, ?, ?)
                """,
                (device_id, utc_now_iso(), last_point),
            )
        _rebuild_daily_stats(conn, device_id, last_point)
        stats = _write_lifetime_stats(conn, device_id, last_point)
        _rebuild_heatmap_bins(conn, device_id, last_point)
        conn.commit()
    return stats


def _rebuild_heatmap_bins(
    conn: sqlite3.Connection,
    device_id: str,
    last_point_recorded_at: str,
) -> None:
    from app.analytics.heatmap_bins import compute_heatmap_bins

    points = conn.execute(
        """
        SELECT latitude, longitude, recorded_at
        FROM location_points
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchall()

    rows = compute_heatmap_bins([dict(row) for row in points])

    conn.execute("DELETE FROM heatmap_bins WHERE device_id = ?", (device_id,))
    for row in rows:
        conn.execute(
            """
            INSERT INTO heatmap_bins (
                device_id, grid_lat, grid_lon, center_lat, center_lon,
                point_count, first_seen_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                row["grid_lat"],
                row["grid_lon"],
                row["center_lat"],
                row["center_lon"],
                row["point_count"],
                row["first_seen_at"],
                row["last_seen_at"],
            ),
        )

    conn.execute(
        """
        UPDATE analytics_meta
        SET heatmap_bins_point_at = ?
        WHERE device_id = ?
        """,
        (last_point_recorded_at, device_id),
    )


def rebuild_heatmap_bins(device_id: str) -> None:
    last_point = get_latest_point_recorded_at(device_id)
    if last_point is None:
        with get_connection() as conn:
            conn.execute("DELETE FROM heatmap_bins WHERE device_id = ?", (device_id,))
            conn.commit()
        return

    with get_connection() as conn:
        meta = conn.execute(
            "SELECT device_id FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if meta is None:
            conn.execute(
                """
                INSERT INTO analytics_meta (device_id, last_computed_at, last_point_recorded_at)
                VALUES (?, ?, ?)
                """,
                (device_id, utc_now_iso(), last_point),
            )
        _rebuild_heatmap_bins(conn, device_id, last_point)
        conn.commit()


def get_heatmap_bins_point_at(device_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT heatmap_bins_point_at FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return row["heatmap_bins_point_at"] if row else None


def get_heatmap_bins(
    device_id: str,
    *,
    min_count: int = 1,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                grid_lat, grid_lon, center_lat, center_lon,
                point_count, first_seen_at, last_seen_at
            FROM heatmap_bins
            WHERE device_id = ? AND point_count >= ?
            ORDER BY point_count DESC
            LIMIT ?
            """,
            (device_id, min_count, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def get_heatmap_summary(device_id: str) -> dict[str, int]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS bin_count,
                COALESCE(SUM(point_count), 0) AS total_points,
                COALESCE(MAX(point_count), 0) AS max_count
            FROM heatmap_bins
            WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()
    return {
        "bin_count": int(row["bin_count"]),
        "total_points": int(row["total_points"]),
        "max_count": int(row["max_count"]),
    }


def _rebuild_daily_stats(
    conn: sqlite3.Connection,
    device_id: str,
    last_point_recorded_at: str,
) -> None:
    from app.analytics.daily_stats import compute_daily_stats_rows

    visits = conn.execute(
        """
        SELECT place_id, started_at, ended_at, duration_sec
        FROM visits
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchall()
    travels = conn.execute(
        """
        SELECT started_at, ended_at, duration_sec, distance_m, travel_mode
        FROM travel_segments
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchall()
    points = conn.execute(
        """
        SELECT recorded_at
        FROM location_points
        WHERE device_id = ?
        """,
        (device_id,),
    ).fetchall()

    rows = compute_daily_stats_rows(
        [dict(row) for row in visits],
        [dict(row) for row in travels],
        [dict(row) for row in points],
    )

    conn.execute("DELETE FROM daily_stats WHERE device_id = ?", (device_id,))
    for row in rows:
        conn.execute(
            """
            INSERT INTO daily_stats (
                device_id, day, point_count, visits_count, places_visited_count,
                stationary_duration_sec, travel_duration_sec, travel_distance_m, travel_trips,
                walked_distance_m, ran_distance_m, drove_distance_m
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                row["day"],
                row["point_count"],
                row["visits_count"],
                row["places_visited_count"],
                row["stationary_duration_sec"],
                row["travel_duration_sec"],
                row["travel_distance_m"],
                row["travel_trips"],
                row["walked_distance_m"],
                row["ran_distance_m"],
                row["drove_distance_m"],
            ),
        )

    conn.execute(
        """
        UPDATE analytics_meta
        SET daily_stats_point_at = ?
        WHERE device_id = ?
        """,
        (last_point_recorded_at, device_id),
    )


def rebuild_daily_stats(device_id: str) -> None:
    last_point = get_latest_point_recorded_at(device_id)
    if last_point is None:
        with get_connection() as conn:
            conn.execute("DELETE FROM daily_stats WHERE device_id = ?", (device_id,))
            conn.commit()
        return

    with get_connection() as conn:
        meta = conn.execute(
            "SELECT device_id FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
        if meta is None:
            conn.execute(
                """
                INSERT INTO analytics_meta (device_id, last_computed_at, last_point_recorded_at)
                VALUES (?, ?, ?)
                """,
                (device_id, utc_now_iso(), last_point),
            )
        _rebuild_daily_stats(conn, device_id, last_point)
        conn.commit()


def get_daily_stats_point_at(device_id: str) -> str | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT daily_stats_point_at FROM analytics_meta WHERE device_id = ?",
            (device_id,),
        ).fetchone()
    return row["daily_stats_point_at"] if row else None


def get_daily_stats_range(
    device_id: str,
    from_day: str,
    to_day: str,
) -> list[dict[str, Any]]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                day, point_count, visits_count, places_visited_count,
                stationary_duration_sec, travel_duration_sec, travel_distance_m, travel_trips,
                walked_distance_m, ran_distance_m, drove_distance_m
            FROM daily_stats
            WHERE device_id = ? AND day >= ? AND day <= ?
            ORDER BY day ASC
            """,
            (device_id, from_day, to_day),
        ).fetchall()
    return [dict(row) for row in rows]


def get_cached_lifetime_stats(device_id: str) -> tuple[dict[str, Any] | None, str | None]:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT lifetime_stats_json, lifetime_stats_point_at
            FROM analytics_meta
            WHERE device_id = ?
            """,
            (device_id,),
        ).fetchone()
    if row is None or not row["lifetime_stats_json"]:
        return None, None
    try:
        return json.loads(row["lifetime_stats_json"]), row["lifetime_stats_point_at"]
    except json.JSONDecodeError:
        return None, None
