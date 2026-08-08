import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from app import config
from app.models import LocationPointIn, LocationPointOut

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

CREATE TABLE IF NOT EXISTS travel_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    from_visit_id INTEGER,
    to_visit_id INTEGER,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    duration_sec INTEGER NOT NULL,
    distance_m REAL NOT NULL,
    avg_speed_mps REAL
);

CREATE INDEX IF NOT EXISTS idx_travel_device_started
    ON travel_segments(device_id, started_at);

CREATE TABLE IF NOT EXISTS analytics_meta (
    device_id TEXT PRIMARY KEY,
    last_computed_at TEXT NOT NULL,
    last_point_recorded_at TEXT
);

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
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
        _migrate_device_settings(conn)
        conn.commit()


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
    conn = sqlite3.connect(config.DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def insert_points(
    device_id: str,
    points: list[LocationPointIn],
) -> tuple[int, int, list[str]]:
    accepted = 0
    duplicates = 0
    errors: list[str] = []
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
                else:
                    duplicates += 1
            except sqlite3.Error as exc:
                errors.append(f"{point.client_point_id}: {exc}")
        conn.commit()

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
) -> list[LocationPointOut]:
    clauses = ["device_id = ?"]
    params: list[Any] = [device_id]

    if from_ts:
        clauses.append("recorded_at >= ?")
        params.append(from_ts)
    if to_ts:
        clauses.append("recorded_at <= ?")
        params.append(to_ts)

    params.append(limit)
    sql = f"""
        SELECT * FROM location_points
        WHERE {' AND '.join(clauses)}
        ORDER BY recorded_at ASC, id ASC
        LIMIT ?
    """

    with get_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    return [LocationPointOut.from_row(_row_to_dict(row)) for row in rows]


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

        for visit, place_id in zip(visits, assigned_place_ids):
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

        for travel in travels:
            conn.execute(
                """
                INSERT INTO travel_segments (
                    device_id, from_visit_id, to_visit_id, started_at, ended_at,
                    duration_sec, distance_m, avg_speed_mps
                ) VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    travel.started_at,
                    travel.ended_at,
                    travel.duration_sec,
                    travel.distance_m,
                    travel.avg_speed_mps,
                ),
            )

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
        conn.commit()


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
    column_end: str = "ended_at",
) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if from_iso:
        clauses.append(f"{column_end} >= ?")
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
    limit: int = 500,
) -> list[dict[str, Any]]:
    range_sql, range_params = _time_range_clause(from_iso, to_iso)
    params: list[Any] = [device_id, *range_params, limit]
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM visits
            WHERE device_id = ?{range_sql}
            ORDER BY started_at ASC, id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def get_travel_segments(
    device_id: str,
    from_iso: str | None = None,
    to_iso: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    range_sql, range_params = _time_range_clause(from_iso, to_iso)
    params: list[Any] = [device_id, *range_params, limit]
    with get_connection() as conn:
        rows = conn.execute(
            f"""
            SELECT * FROM travel_segments
            WHERE device_id = ?{range_sql}
            ORDER BY started_at ASC, id ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
