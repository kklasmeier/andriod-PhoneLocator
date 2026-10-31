"""Classify a trip as walked, ran, or drove from its pace and its neighbors.

Phone activity is not collected, and most points have no speed. The pace comes
from successive GPS fixes. A drive that sits in traffic has a slow average, so
a real stretch over 12 mph still counts as driving. One short GPS jump does not.
"""

from dataclasses import dataclass

from app.analytics.constants import (
    MOTION_LEG_MAX_GAP_SEC,
    RUN_SPEED_MPS,
    VEHICLE_NEIGHBOR_GAP_SEC,
    VEHICLE_SPEED_MPS,
    VEHICLE_STRETCH_MIN_LEGS,
    VEHICLE_STRETCH_MIN_M,
    WALK_SPEED_MPS,
)
from app.analytics.geo import haversine_m
from app.analytics.periods import parse_iso

MODE_VEHICLE = "vehicle"
MODE_RUNNING = "running"
MODE_WALKING = "walking"
MODE_SLOW = "slow"


def measure_motion(points: list[tuple[str, float, float]]) -> tuple[float, float, int]:
    """Return peak speed, distance covered over 12 mph, and how many legs that was.

    Each point is (recorded_at, latitude, longitude). Gaps longer than 10 minutes
    are ignored so a missing fix does not look like a highway jump.
    """
    peak = 0.0
    fast_distance_m = 0.0
    fast_leg_count = 0
    for prev, curr in zip(points, points[1:]):
        dt = (parse_iso(curr[0]) - parse_iso(prev[0])).total_seconds()
        if dt <= 0 or dt > MOTION_LEG_MAX_GAP_SEC:
            continue
        dist = haversine_m(prev[1], prev[2], curr[1], curr[2])
        speed = dist / dt
        if speed > peak:
            peak = speed
        if speed >= VEHICLE_SPEED_MPS:
            fast_distance_m += dist
            fast_leg_count += 1
    return peak, fast_distance_m, fast_leg_count


@dataclass
class MotionSegment:
    started_at: str
    ended_at: str
    avg_speed_mps: float | None
    peak_speed_mps: float | None
    fast_distance_m: float
    fast_leg_count: int


def _real_vehicle_stretch(segment: MotionSegment) -> bool:
    peak = segment.peak_speed_mps or 0.0
    if peak < VEHICLE_SPEED_MPS:
        return False
    return (
        segment.fast_leg_count >= VEHICLE_STRETCH_MIN_LEGS
        or segment.fast_distance_m >= VEHICLE_STRETCH_MIN_M
    )


def _neighbor_is_drive(segment: MotionSegment, other: MotionSegment) -> bool:
    avg = other.avg_speed_mps
    if avg is None or avg < VEHICLE_SPEED_MPS:
        return False
    gap = (parse_iso(other.started_at) - parse_iso(segment.ended_at)).total_seconds()
    if gap < 0:
        gap = (parse_iso(segment.started_at) - parse_iso(other.ended_at)).total_seconds()
    return gap <= VEHICLE_NEIGHBOR_GAP_SEC


def classify_modes(segments: list[MotionSegment]) -> list[str]:
    """Label chronological trips. Neighbors are the previous and next trip only."""
    modes: list[str] = []
    for index, segment in enumerate(segments):
        avg = segment.avg_speed_mps or 0.0
        peak = segment.peak_speed_mps or 0.0
        if avg >= VEHICLE_SPEED_MPS or _real_vehicle_stretch(segment):
            modes.append(MODE_VEHICLE)
            continue
        near_drive = False
        if peak < VEHICLE_SPEED_MPS:
            if index > 0 and _neighbor_is_drive(segment, segments[index - 1]):
                near_drive = True
            if index + 1 < len(segments) and _neighbor_is_drive(segment, segments[index + 1]):
                near_drive = True
        if near_drive:
            modes.append(MODE_VEHICLE)
        elif avg >= RUN_SPEED_MPS:
            modes.append(MODE_RUNNING)
        elif avg >= WALK_SPEED_MPS:
            modes.append(MODE_WALKING)
        else:
            modes.append(MODE_SLOW)
    return modes
