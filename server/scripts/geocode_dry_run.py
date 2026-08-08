"""Estimate how many reverse-geocode API calls auto-naming would need.

Standalone script — only Python stdlib + sqlite3 (no venv required).

Rules (match planned v1 + presentation):
- Only unnamed places
- Place must have at least one visit >= 5 min
- Group unnamed qualifying places within 50 m
- Clusters within 50 m of a manually named place inherit that name (0 geocodes)
- One Nominatim request per remaining cluster (first run; cache hits thereafter)

Usage on piSensors:
  python3 scripts/geocode_dry_run.py \\
    --db /var/lib/phone-locator/phone-locator.db \\
    --device-id YOUR-DEVICE-UUID
"""

from __future__ import annotations

import argparse
import math
import sqlite3
import sys
from pathlib import Path

MIN_VISIT_SEC = 300
MERGE_RADIUS_M = 50.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _cluster(points: list[dict], radius_m: float) -> list[list[dict]]:
    remaining = list(points)
    clusters: list[list[dict]] = []

    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        i = 0
        while i < len(remaining):
            other = remaining[i]
            if (
                haversine_m(
                    seed["center_lat"],
                    seed["center_lon"],
                    other["center_lat"],
                    other["center_lon"],
                )
                < radius_m
            ):
                cluster.append(other)
                remaining.pop(i)
            else:
                i += 1
        clusters.append(cluster)

    return clusters


def _near_any_named(place: dict, named_places: list[dict], radius_m: float) -> bool:
    for named in named_places:
        if (
            haversine_m(
                place["center_lat"],
                place["center_lon"],
                named["center_lat"],
                named["center_lon"],
            )
            < radius_m
        ):
            return True
    return False


def _default_db_path() -> str:
    candidates = [
        "/var/lib/phone-locator/phone-locator.db",
        str(Path(__file__).resolve().parents[1] / "data" / "phone-locator.db"),
    ]
    for path in candidates:
        if Path(path).is_file():
            return path
    return candidates[0]


def analyze(db_path: str, device_id: str) -> dict:
    if not Path(db_path).is_file():
        raise FileNotFoundError(f"Database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    places = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM places WHERE device_id = ? ORDER BY last_seen_at DESC, id DESC",
            (device_id,),
        ).fetchall()
    ]

    visits = [
        dict(row)
        for row in conn.execute(
            """
            SELECT * FROM visits
            WHERE device_id = ?
            ORDER BY started_at ASC, id ASC
            """,
            (device_id,),
        ).fetchall()
    ]
    conn.close()

    qualifying_place_ids: set[int] = set()
    for visit in visits:
        if visit["duration_sec"] >= MIN_VISIT_SEC and visit["place_id"] is not None:
            qualifying_place_ids.add(visit["place_id"])

    named = [p for p in places if p.get("name")]
    unnamed = [p for p in places if not p.get("name")]
    unnamed_qualifying = [p for p in unnamed if p["id"] in qualifying_place_ids]

    clusters = _cluster(unnamed_qualifying, MERGE_RADIUS_M)

    needs_geocode: list[list[dict]] = []
    inherits_name = 0
    for cluster in clusters:
        if any(_near_any_named(p, named, MERGE_RADIUS_M) for p in cluster):
            inherits_name += len(cluster)
        else:
            needs_geocode.append(cluster)

    geocode_queries = len(needs_geocode)
    places_covered = sum(len(c) for c in needs_geocode)

    return {
        "device_id": device_id,
        "db_path": db_path,
        "min_visit_sec": MIN_VISIT_SEC,
        "merge_radius_m": MERGE_RADIUS_M,
        "total_places": len(places),
        "named_places": len(named),
        "unnamed_places": len(unnamed),
        "named_labels": [p["name"] for p in named],
        "unnamed_with_5min_visit": len(unnamed_qualifying),
        "clusters_after_50m_merge": len(clusters),
        "places_inherit_near_manual_name": inherits_name,
        "geocode_queries_needed": geocode_queries,
        "unnamed_places_renamed_via_geocode": places_covered,
        "estimated_seconds_at_1_per_sec": geocode_queries,
        "sample_clusters": [
            {
                "place_ids": [p["id"] for p in cluster],
                "count": len(cluster),
                "lat": round(sum(p["center_lat"] for p in cluster) / len(cluster), 5),
                "lon": round(sum(p["center_lon"] for p in cluster) / len(cluster), 5),
                "total_visits": sum(p.get("visit_count", 0) for p in cluster),
            }
            for cluster in sorted(needs_geocode, key=lambda c: -sum(p.get("visit_count", 0) for p in c))[:15]
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Dry-run geocode query count for auto-naming")
    parser.add_argument("--device-id", required=True, help="Phone device UUID")
    parser.add_argument(
        "--db",
        default=_default_db_path(),
        help="Path to phone-locator SQLite database",
    )
    args = parser.parse_args()

    try:
        stats = analyze(args.db, args.device_id)
    except FileNotFoundError as err:
        print(f"Error: {err}", file=sys.stderr)
        sys.exit(1)

    print("=== Geocode dry run (planned v1 rules) ===")
    print(f"Database:            {stats['db_path']}")
    print(f"Device:              {stats['device_id']}")
    print(f"Min visit duration:  {stats['min_visit_sec']} sec ({stats['min_visit_sec'] // 60} min)")
    print(f"Merge radius:        {stats['merge_radius_m']} m")
    print()
    print(f"Total place rows:    {stats['total_places']}")
    print(f"  Already named:     {stats['named_places']}", end="")
    if stats["named_labels"]:
        print(f" ({', '.join(stats['named_labels'][:5])}" + ("…" if len(stats["named_labels"]) > 5 else "") + ")")
    else:
        print()
    print(f"  Unnamed:           {stats['unnamed_places']}")
    print()
    print(f"Unnamed w/ ≥5m stay: {stats['unnamed_with_5min_visit']}")
    print(f"After 50m grouping:  {stats['clusters_after_50m_merge']} clusters")
    print(f"Inherit manual name: {stats['places_inherit_near_manual_name']} places (no geocode)")
    print()
    print(f">>> GEOCODE QUERIES:  {stats['geocode_queries_needed']} <<<")
    print(f"    Places labeled:   {stats['unnamed_places_renamed_via_geocode']}")
    print(f"    First-run time:   ~{stats['estimated_seconds_at_1_per_sec']} sec at 1 req/sec")
    print(f"    After cache:      0 for unchanged locations")
    print()

    if stats["sample_clusters"]:
        print("Top clusters that would be geocoded (lat, lon, place count):")
        for i, c in enumerate(stats["sample_clusters"], 1):
            ids = c["place_ids"]
            suffix = "…" if len(ids) > 5 else ""
            print(
                f"  {i:2}. ({c['lat']}, {c['lon']}) — "
                f"{c['count']} place row(s), {c['total_visits']} visit(s), ids={ids[:5]}{suffix}"
            )


if __name__ == "__main__":
    main()
