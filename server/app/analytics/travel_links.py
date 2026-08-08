"""Match travel segments to adjacent visits."""

from typing import Any


def match_adjacent_visit_ids(
    travel_started_at: str,
    travel_ended_at: str,
    visits: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Return (from_visit_id, to_visit_id) for a travel segment."""
    from_id: int | None = None
    from_ended_at: str | None = None
    to_id: int | None = None

    for visit in visits:
        if visit["ended_at"] <= travel_started_at:
            if from_ended_at is None or visit["ended_at"] > from_ended_at:
                from_id = visit["id"]
                from_ended_at = visit["ended_at"]
        if to_id is None and visit["started_at"] >= travel_ended_at:
            to_id = visit["id"]

    return from_id, to_id
