"""Estimate how many reverse-geocode API calls auto-naming would need.

Rules (match planned v1 + presentation):
- Only unnamed places
- Place must have at least one visit >= MIN_VISIT_PRESENTATION_SEC (5 min)
- Group unnamed qualifying places within PLACE_MERGE_RADIUS_M (50 m)
- Clusters within 50 m of a manually named place inherit that name (0 geocodes)
- One Nominatim request per remaining cluster (first run; cache hits thereafter)

Usage on piSensors:
  cd ~/andriod-PhoneLocator/server
  PHONE_LOCATOR_DATABASE_PATH=/var/lib/phone-locator/phone-locator.db \\
    python3 scripts/geocode_dry_run.py --device-id YOUR-DEVICE-UUID
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Allow running as: python3 scripts/geocode_dry_run.py
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.analytics.constants import MIN_VISIT_PRESENTATION_SEC, PLACE_MERGE_RADIUS_M
from app.analytics.geo import haversine_m
from app import database


def _cluster(points: list[dict], radius_m: float) -> list[list[dict]]:
    """Greedy spatial clustering by center_lat/center_lon."""
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


def analyze(device_id: str) -> dict:
    database.init_db()

    places = database.get_places(device_id)
    visits = database.get_visits(device_id, limit=100_000)

    qualifying_place_ids: set[int] = set()
    for visit in visits:
        if visit["duration_sec"] >= MIN_VISIT_PRESENTATION_SEC and visit["place_id"] is not None:
            qualifying_place_ids.add(visit["place_id"])

    named = [p for p in places if p.get("name")]
    unnamed = [p for p in places if not p.get("name")]
    unnamed_qualifying = [p for p in unnamed if p["id"] in qualifying_place_ids]

    clusters = _cluster(unnamed_qualifying, PLACE_MERGE_RADIUS_M)

    needs_geocode: list[list[dict]] = []
    inherits_name = 0
    for cluster in clusters:
        if any(_near_any_named(p, named, PLACE_MERGE_RADIUS_M) for p in cluster):
            inherits_name += len(cluster)
        else:
            needs_geocode.append(cluster)

    geocode_queries = len(needs_geocode)
    places_covered = sum(len(c) for c in needs_geocode)

    return {
        "device_id": device_id,
        "min_visit_sec": MIN_VISIT_PRESENTATION_SEC,
        "merge_radius_m": PLACE_MERGE_RADIUS_M,
        "total_places": len(places),
        "named_places": len(named),
        "unnamed_places": len(unnamed),
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
    args = parser.parse_args()

    if not os.environ.get("PHONE_LOCATOR_DATABASE_PATH"):
        print("Tip: set PHONE_LOCATOR_DATABASE_PATH=/var/lib/phone-locator/phone-locator.db", file=sys.stderr)

    stats = analyze(args.device_id)

    print("=== Geocode dry run (planned v1 rules) ===")
    print(f"Device:              {stats['device_id']}")
    print(f"Min visit duration:  {stats['min_visit_sec']} sec ({stats['min_visit_sec'] // 60} min)")
    print(f"Merge radius:        {stats['merge_radius_m']} m")
    print()
    print(f"Total place rows:    {stats['total_places']}")
    print(f"  Already named:     {stats['named_places']}")
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
            print(
                f"  {i:2}. ({c['lat']}, {c['lon']}) — "
                f"{c['count']} place row(s), {c['total_visits']} visit(s), ids={c['place_ids'][:5]}"
                + ("…" if len(c["place_ids"]) > 5 else "")
            )


if __name__ == "__main__":
    main()
