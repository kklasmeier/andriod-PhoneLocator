"""Trip mode: walking, running, and driving from pace and neighboring trips."""

import unittest

from app.analytics.motion import (
    MODE_RUNNING,
    MODE_SLOW,
    MODE_VEHICLE,
    MODE_WALKING,
    MotionSegment,
    classify_modes,
    measure_motion,
)


def _seg(
    start: str,
    end: str,
    avg_mph: float,
    peak_mph: float = 0.0,
    fast_m: float = 0.0,
    fast_legs: int = 0,
) -> MotionSegment:
    return MotionSegment(
        started_at=start,
        ended_at=end,
        avg_speed_mps=avg_mph * 1609.344 / 3600,
        peak_speed_mps=peak_mph * 1609.344 / 3600,
        fast_distance_m=fast_m,
        fast_leg_count=fast_legs,
    )


class MotionMeasureTests(unittest.TestCase):
    def test_ignores_a_gap_longer_than_ten_minutes(self) -> None:
        points = [
            ("2026-08-01T12:00:00Z", 42.0, -83.0),
            ("2026-08-01T12:30:00Z", 42.1, -83.0),
        ]
        peak, fast_m, fast_legs = measure_motion(points)
        self.assertEqual(peak, 0.0)
        self.assertEqual(fast_m, 0.0)
        self.assertEqual(fast_legs, 0)

    def test_counts_a_fast_stretch(self) -> None:
        # About 200 m in 10 seconds is well over 12 mph.
        points = [
            ("2026-08-01T12:00:00Z", 42.0, -83.0),
            ("2026-08-01T12:00:10Z", 42.0018, -83.0),
        ]
        peak, fast_m, fast_legs = measure_motion(points)
        self.assertGreater(peak, 12 * 1609.344 / 3600)
        self.assertGreaterEqual(fast_m, 80)
        self.assertEqual(fast_legs, 1)


class ClassifyModeTests(unittest.TestCase):
    def test_average_over_12_mph_is_a_drive(self) -> None:
        modes = classify_modes([_seg("2026-08-01T12:00:00Z", "2026-08-01T12:20:00Z", 30)])
        self.assertEqual(modes, [MODE_VEHICLE])

    def test_slow_average_with_a_real_fast_stretch_is_a_drive(self) -> None:
        modes = classify_modes(
            [_seg("2026-08-01T12:00:00Z", "2026-08-01T12:40:00Z", 8, peak_mph=28, fast_m=400, fast_legs=4)]
        )
        self.assertEqual(modes, [MODE_VEHICLE])

    def test_one_short_gps_jump_stays_on_foot(self) -> None:
        modes = classify_modes(
            [_seg("2026-08-01T12:00:00Z", "2026-08-01T12:20:00Z", 3, peak_mph=40, fast_m=30, fast_legs=1)]
        )
        self.assertEqual(modes, [MODE_WALKING])

    def test_jog_pace_is_running(self) -> None:
        modes = classify_modes([_seg("2026-08-01T12:00:00Z", "2026-08-01T12:20:00Z", 6, peak_mph=8)])
        self.assertEqual(modes, [MODE_RUNNING])

    def test_walk_pace_is_walking(self) -> None:
        modes = classify_modes([_seg("2026-08-01T12:00:00Z", "2026-08-01T12:20:00Z", 3, peak_mph=4)])
        self.assertEqual(modes, [MODE_WALKING])

    def test_crawl_is_not_a_walk(self) -> None:
        modes = classify_modes([_seg("2026-08-01T12:00:00Z", "2026-08-01T12:20:00Z", 1.2, peak_mph=2)])
        self.assertEqual(modes, [MODE_SLOW])

    def test_slow_trip_next_to_a_drive_counts_as_driving(self) -> None:
        modes = classify_modes(
            [
                _seg("2026-08-01T12:00:00Z", "2026-08-01T12:10:00Z", 3, peak_mph=4),
                _seg("2026-08-01T12:20:00Z", "2026-08-01T13:00:00Z", 40, peak_mph=60, fast_m=5000, fast_legs=20),
            ]
        )
        self.assertEqual(modes, [MODE_VEHICLE, MODE_VEHICLE])

    def test_slow_trip_hours_away_from_a_drive_stays_a_walk(self) -> None:
        modes = classify_modes(
            [
                _seg("2026-08-01T08:00:00Z", "2026-08-01T08:20:00Z", 3, peak_mph=4),
                _seg("2026-08-01T18:00:00Z", "2026-08-01T18:40:00Z", 40, peak_mph=60, fast_m=5000, fast_legs=20),
            ]
        )
        self.assertEqual(modes, [MODE_WALKING, MODE_VEHICLE])


if __name__ == "__main__":
    unittest.main()
