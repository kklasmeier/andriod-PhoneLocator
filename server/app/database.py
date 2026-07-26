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
        conn.commit()


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
