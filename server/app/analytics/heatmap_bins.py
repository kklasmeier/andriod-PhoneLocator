"""~50 m geographic grid bins for lifetime map heatmaps."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

CELL_SIZE_M = 50.0


def _meters_per_degree(lat: float) -> tuple[float, float]:
    lat_rad = math.radians(lat)
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * max(math.cos(lat_rad), 0.01)
    return meters_per_deg_lat, meters_per_deg_lon


def point_to_grid(lat: float, lon: float) -> tuple[int, int]:
    meters_per_deg_lat, meters_per_deg_lon = _meters_per_degree(lat)
    grid_lat = int(math.floor(lat * meters_per_deg_lat / CELL_SIZE_M))
    grid_lon = int(math.floor(lon * meters_per_deg_lon / CELL_SIZE_M))
    return grid_lat, grid_lon


def grid_to_center(grid_lat: int, grid_lon: int, ref_lat: float) -> tuple[float, float]:
    meters_per_deg_lat, meters_per_deg_lon = _meters_per_degree(ref_lat)
    center_lat = (grid_lat + 0.5) * CELL_SIZE_M / meters_per_deg_lat
    center_lon = (grid_lon + 0.5) * CELL_SIZE_M / meters_per_deg_lon
    return center_lat, center_lon


def compute_heatmap_bins(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[int, int], dict[str, Any]] = defaultdict(
        lambda: {
            "point_count": 0,
            "lat_sum": 0.0,
            "lon_sum": 0.0,
            "first_seen_at": None,
            "last_seen_at": None,
        }
    )

    for point in points:
        lat = float(point["latitude"])
        lon = float(point["longitude"])
        recorded_at = point["recorded_at"]
        grid_lat, grid_lon = point_to_grid(lat, lon)
        bucket = buckets[(grid_lat, grid_lon)]
        bucket["point_count"] += 1
        bucket["lat_sum"] += lat
        bucket["lon_sum"] += lon
        if bucket["first_seen_at"] is None or recorded_at < bucket["first_seen_at"]:
            bucket["first_seen_at"] = recorded_at
        if bucket["last_seen_at"] is None or recorded_at > bucket["last_seen_at"]:
            bucket["last_seen_at"] = recorded_at

    rows: list[dict[str, Any]] = []
    for (grid_lat, grid_lon), bucket in buckets.items():
        count = int(bucket["point_count"])
        center_lat = bucket["lat_sum"] / count
        center_lon = bucket["lon_sum"] / count
        rows.append(
            {
                "grid_lat": grid_lat,
                "grid_lon": grid_lon,
                "center_lat": center_lat,
                "center_lon": center_lon,
                "point_count": count,
                "first_seen_at": bucket["first_seen_at"],
                "last_seen_at": bucket["last_seen_at"],
            }
        )

    rows.sort(key=lambda row: row["point_count"], reverse=True)
    return rows
