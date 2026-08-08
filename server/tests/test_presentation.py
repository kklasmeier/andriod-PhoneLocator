"""Presentation rule tests for timeline analytics."""

import unittest
from datetime import datetime, timedelta, timezone

from app.analytics.engine import TrackPoint, VisitDraft, TravelDraft, segment_points
from app.analytics.presentation import apply_presentation_rules

HOME_LAT, HOME_LON = 42.2800, -83.7400


class PresentationTests(unittest.TestCase):
    def test_short_nearby_visit_merges_into_home(self) -> None:
        """GPS drift visit under 5 min within 50 m merges into the main stay."""
        visits = [
            VisitDraft(
                "2026-08-07T08:00:00Z",
                "2026-08-07T20:00:00Z",
                HOME_LAT,
                HOME_LON,
                [],
            ),
            VisitDraft(
                "2026-08-07T12:45:00Z",
                "2026-08-07T12:45:00Z",
                HOME_LAT + 0.0002,
                HOME_LON,
                [],
            ),
        ]
        travels = [
            TravelDraft("2026-08-07T12:35:00Z", "2026-08-07T12:44:00Z", 3000.0, []),
            TravelDraft("2026-08-07T12:46:00Z", "2026-08-07T12:50:00Z", 100.0, []),
        ]
        out_visits, out_travels = apply_presentation_rules(visits, travels)
        self.assertEqual(len(out_visits), 1)
        self.assertGreaterEqual(out_visits[0].duration_sec, 3600)

    def test_traffic_light_absorbed_into_travel(self) -> None:
        """Brief stop between two travel legs is not a separate place."""
        visits = [
            VisitDraft(
                "2026-08-07T12:02:00Z",
                "2026-08-07T12:03:00Z",
                HOME_LAT + 0.01,
                HOME_LON,
                [],
            ),
        ]
        travels = [
            TravelDraft("2026-08-07T12:00:00Z", "2026-08-07T12:01:30Z", 800.0, []),
            TravelDraft("2026-08-07T12:03:30Z", "2026-08-07T12:05:00Z", 900.0, []),
        ]
        out_visits, out_travels = apply_presentation_rules(visits, travels)
        self.assertEqual(len(out_visits), 0)
        self.assertEqual(len(out_travels), 1)

    def test_real_stop_over_five_minutes_kept(self) -> None:
        visits = [
            VisitDraft(
                "2026-08-07T12:00:00Z",
                "2026-08-07T12:10:00Z",
                HOME_LAT + 0.05,
                HOME_LON,
                [],
            ),
        ]
        out_visits, _ = apply_presentation_rules(visits, [])
        self.assertEqual(len(out_visits), 1)
        self.assertGreaterEqual(out_visits[0].duration_sec, 300)

    def test_short_travel_between_same_place_collapses(self) -> None:
        visits = [
            VisitDraft("2026-08-07T08:00:00Z", "2026-08-07T12:00:00Z", HOME_LAT, HOME_LON, []),
            VisitDraft("2026-08-07T12:05:00Z", "2026-08-07T18:00:00Z", HOME_LAT, HOME_LON, []),
        ]
        travels = [
            TravelDraft("2026-08-07T12:00:00Z", "2026-08-07T12:05:00Z", 8.0, []),
        ]
        out_visits, out_travels = apply_presentation_rules(visits, travels)
        self.assertEqual(len(out_visits), 1)
        self.assertEqual(len(out_travels), 0)


if __name__ == "__main__":
    unittest.main()
