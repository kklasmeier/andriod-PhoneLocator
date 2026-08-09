"""Human-readable labels for travel segments (round trips, local loops)."""

from typing import Any

from app.analytics.constants import SAME_PLACE_LOCAL_MAX_M


def enrich_travel_segment(
    segment: dict[str, Any],
    *,
    from_place_name: str,
    to_place_name: str,
    from_place_id: int | None = None,
    to_place_id: int | None = None,
) -> dict[str, Any]:
    """Add route_label and route_kind for display and route aggregation."""
    distance_m = float(segment.get("distance_m") or 0)
    same_place_id = (
        from_place_id is not None
        and to_place_id is not None
        and from_place_id == to_place_id
    )
    same_name = (
        from_place_name.strip().lower() == to_place_name.strip().lower()
        and from_place_name not in ("Unknown", "Unknown place")
    )

    enriched = {
        **segment,
        "from_place_name": from_place_name,
        "to_place_name": to_place_name,
    }

    if same_place_id or same_name:
        if distance_m < SAME_PLACE_LOCAL_MAX_M:
            enriched.update(
                {
                    "route_label": f"At {from_place_name} (local)",
                    "route_kind": "local",
                }
            )
            return enriched
        enriched.update(
            {
                "route_label": f"Round trip from {from_place_name}",
                "route_kind": "round_trip",
                "to_place_name": "↩ return",
            }
        )
        return enriched

    enriched.update(
        {
            "route_label": f"{from_place_name} → {to_place_name}",
            "route_kind": "trip",
        }
    )
    return enriched


def is_local_loop_travel(
    *,
    from_place_id: int | None,
    to_place_id: int | None,
    distance_m: float,
) -> bool:
    """Same-place GPS noise or parking-lot drift — not a meaningful trip."""
    if from_place_id is None or to_place_id is None:
        return False
    if from_place_id != to_place_id:
        return False
    return distance_m < SAME_PLACE_LOCAL_MAX_M
