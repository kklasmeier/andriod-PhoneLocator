"""Presentation rules for timeline, places, and summaries.

Raw location_points are never modified — only how visits/travel are derived for display.
"""

from typing import Literal

from app.analytics.constants import (
    MIN_TRAVEL_PRESENTATION_M,
    MIN_TRAVEL_PRESENTATION_SEC,
    MIN_VISIT_PRESENTATION_SEC,
    PLACE_MERGE_RADIUS_M,
)
from app.analytics.engine import TravelDraft, VisitDraft, _close_travel
from app.analytics.geo import centroid, haversine_m


TimelineEntry = tuple[Literal["visit", "travel"], VisitDraft | TravelDraft]


def _merge_visits(a: VisitDraft, b: VisitDraft) -> VisitDraft:
    points = a.points + b.points
    if points:
        lat, lon = centroid([(p.latitude, p.longitude) for p in points])
    else:
        lat = (a.center_lat + b.center_lat) / 2
        lon = (a.center_lon + b.center_lon) / 2
    return VisitDraft(
        started_at=min(a.started_at, b.started_at),
        ended_at=max(a.ended_at, b.ended_at),
        center_lat=lat,
        center_lon=lon,
        points=points,
    )


def _merge_travels(a: TravelDraft, b: TravelDraft) -> TravelDraft:
    points = a.points + b.points
    if not points:
        return TravelDraft(
            started_at=min(a.started_at, b.started_at),
            ended_at=max(a.ended_at, b.ended_at),
            distance_m=a.distance_m + b.distance_m,
            points=[],
        )
    return _close_travel(points)


def _interleave(visits: list[VisitDraft], travels: list[TravelDraft]) -> list[TimelineEntry]:
    items: list[TimelineEntry] = [("visit", v) for v in visits] + [("travel", t) for t in travels]
    items.sort(key=lambda row: row[1].started_at)
    return items


def _split_items(items: list[TimelineEntry]) -> tuple[list[VisitDraft], list[TravelDraft]]:
    visits: list[VisitDraft] = []
    travels: list[TravelDraft] = []
    for kind, draft in items:
        if kind == "visit":
            visits.append(draft)
        else:
            travels.append(draft)
    return visits, travels


def _visits_near(a: VisitDraft, b: VisitDraft, radius_m: float) -> bool:
    return haversine_m(a.center_lat, a.center_lon, b.center_lat, b.center_lon) < radius_m


def _is_significant_travel(travel: TravelDraft) -> bool:
    if travel.distance_m >= MIN_TRAVEL_PRESENTATION_M:
        return True
    return travel.duration_sec >= MIN_TRAVEL_PRESENTATION_SEC and travel.distance_m >= 50.0


def _absorb_short_visits(items: list[TimelineEntry]) -> list[TimelineEntry]:
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(items):
            kind, draft = items[i]
            if kind != "visit" or draft.duration_sec >= MIN_VISIT_PRESENTATION_SEC:
                i += 1
                continue

            short = draft
            if i > 0 and items[i - 1][0] == "visit":
                prev = items[i - 1][1]
                if _visits_near(prev, short, PLACE_MERGE_RADIUS_M):
                    items[i - 1] = ("visit", _merge_visits(prev, short))
                    items.pop(i)
                    changed = True
                    continue

            if i + 1 < len(items) and items[i + 1][0] == "visit":
                nxt = items[i + 1][1]
                if _visits_near(short, nxt, PLACE_MERGE_RADIUS_M):
                    items[i + 1] = ("visit", _merge_visits(short, nxt))
                    items.pop(i)
                    changed = True
                    continue

            if (
                i > 0
                and i + 1 < len(items)
                and items[i - 1][0] == "travel"
                and items[i + 1][0] == "travel"
            ):
                merged_travel = _merge_travels(items[i - 1][1], items[i + 1][1])
                items[i - 1] = ("travel", merged_travel)
                items.pop(i + 1)
                items.pop(i)
                changed = True
                continue

            items.pop(i)
            changed = True
    return items


def _collapse_short_travel(items: list[TimelineEntry]) -> list[TimelineEntry]:
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(items):
            kind, draft = items[i]
            if kind != "travel" or _is_significant_travel(draft):
                i += 1
                continue

            travel = draft
            prev_visit = items[i - 1][1] if i > 0 and items[i - 1][0] == "visit" else None
            next_visit = items[i + 1][1] if i + 1 < len(items) and items[i + 1][0] == "visit" else None

            if (
                prev_visit is not None
                and next_visit is not None
                and _visits_near(prev_visit, next_visit, PLACE_MERGE_RADIUS_M)
            ):
                items[i - 1] = ("visit", _merge_visits(prev_visit, next_visit))
                items.pop(i + 1)
                items.pop(i)
                changed = True
                continue

            if i > 0 and items[i - 1][0] == "travel":
                items[i - 1] = ("travel", _merge_travels(items[i - 1][1], travel))
                items.pop(i)
                changed = True
                continue

            if i + 1 < len(items) and items[i + 1][0] == "travel":
                items[i + 1] = ("travel", _merge_travels(travel, items[i + 1][1]))
                items.pop(i)
                changed = True
                continue

            items.pop(i)
            changed = True
    return items


def _merge_adjacent_nearby_visits(items: list[TimelineEntry]) -> list[TimelineEntry]:
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(items):
            if items[i][0] != "visit":
                i += 1
                continue
            j = i + 1
            while j < len(items) and items[j][0] == "travel":
                if _is_significant_travel(items[j][1]):
                    break
                j += 1
            if j >= len(items) or items[j][0] != "visit":
                i += 1
                continue
            if not _visits_near(items[i][1], items[j][1], PLACE_MERGE_RADIUS_M):
                i += 1
                continue
            merged = _merge_visits(items[i][1], items[j][1])
            del items[i : j + 1]
            items.insert(i, ("visit", merged))
            changed = True
    return items


def apply_presentation_rules(
    visits: list[VisitDraft],
    travels: list[TravelDraft],
) -> tuple[list[VisitDraft], list[TravelDraft]]:
    """Apply timeline presentation rules without altering raw GPS points."""
    items = _interleave(visits, travels)
    items = _absorb_short_visits(items)
    items = _collapse_short_travel(items)
    items = _merge_adjacent_nearby_visits(items)
    items = _absorb_short_visits(items)
    items = _collapse_short_travel(items)
    return _split_items(items)
