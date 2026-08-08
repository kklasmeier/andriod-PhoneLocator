"""Auto-name unnamed places via reverse geocoding."""

from __future__ import annotations

from typing import Any

from app.analytics.constants import MIN_VISIT_PRESENTATION_SEC, PLACE_MERGE_RADIUS_M
from app.analytics.geo import haversine_m
from app.analytics import geocode as geocode_client


def _cluster_places(places: list[dict[str, Any]], radius_m: float) -> list[list[dict[str, Any]]]:
    remaining = list(places)
    clusters: list[list[dict[str, Any]]] = []

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


def _nearest_named_place(place: dict[str, Any], named_places: list[dict[str, Any]], radius_m: float):
    best = None
    best_dist = radius_m
    for named in named_places:
        dist = haversine_m(
            place["center_lat"],
            place["center_lon"],
            named["center_lat"],
            named["center_lon"],
        )
        if dist < best_dist:
            best = named
            best_dist = dist
    return best


def plan_auto_naming(places: list[dict[str, Any]], visits: list[dict[str, Any]]) -> dict[str, Any]:
    qualifying_place_ids: set[int] = set()
    for visit in visits:
        if visit["duration_sec"] >= MIN_VISIT_PRESENTATION_SEC and visit["place_id"] is not None:
            qualifying_place_ids.add(visit["place_id"])

    named = [p for p in places if p.get("name")]
    unnamed = [p for p in places if not p.get("name")]
    unnamed_qualifying = [p for p in unnamed if p["id"] in qualifying_place_ids]
    clusters = _cluster_places(unnamed_qualifying, PLACE_MERGE_RADIUS_M)

    inherit_groups: list[dict[str, Any]] = []
    geocode_groups: list[dict[str, Any]] = []

    for cluster in clusters:
        donor = None
        for place in cluster:
            donor = _nearest_named_place(place, named, PLACE_MERGE_RADIUS_M)
            if donor is not None:
                break

        if donor is not None:
            inherit_groups.append(
                {
                    "name": donor["name"],
                    "place_ids": [p["id"] for p in cluster],
                    "lat": sum(p["center_lat"] for p in cluster) / len(cluster),
                    "lon": sum(p["center_lon"] for p in cluster) / len(cluster),
                }
            )
            continue

        lat = sum(p["center_lat"] for p in cluster) / len(cluster)
        lon = sum(p["center_lon"] for p in cluster) / len(cluster)
        geocode_groups.append(
            {
                "place_ids": [p["id"] for p in cluster],
                "lat": lat,
                "lon": lon,
            }
        )

    return {
        "inherit_groups": inherit_groups,
        "geocode_groups": geocode_groups,
        "geocode_queries_needed": len(geocode_groups),
    }


def auto_rename_places(device_id: str, *, dry_run: bool = False) -> dict[str, Any]:
    from app import database

    places = database.get_places(device_id)
    visits = database.get_visits(device_id, limit=100_000)
    plan = plan_auto_naming(places, visits)

    inherited = 0
    geocoded = 0
    cache_hits = 0
    api_calls = 0
    errors: list[str] = []

    if not dry_run:
        for group in plan["inherit_groups"]:
            count = database.set_place_names_if_null(device_id, group["place_ids"], group["name"])
            inherited += count

        for group in plan["geocode_groups"]:
            lat = group["lat"]
            lon = group["lon"]
            key = geocode_client.cache_key_for(lat, lon)
            cached = database.get_geocode_cache(key)
            if cached:
                label = cached["label"]
                cache_hits += 1
            else:
                try:
                    label, raw = geocode_client.reverse_geocode(lat, lon)
                    database.set_geocode_cache(key, label, raw)
                    api_calls += 1
                except RuntimeError as err:
                    errors.append(str(err))
                    continue

            count = database.set_place_names_if_null(device_id, group["place_ids"], label)
            geocoded += count

    return {
        "device_id": device_id,
        "dry_run": dry_run,
        "inherit_groups": len(plan["inherit_groups"]),
        "geocode_groups": len(plan["geocode_groups"]),
        "geocode_queries_needed": plan["geocode_queries_needed"],
        "places_inherited": inherited,
        "places_geocoded": geocoded,
        "cache_hits": cache_hits,
        "api_calls": api_calls,
        "errors": errors,
    }
