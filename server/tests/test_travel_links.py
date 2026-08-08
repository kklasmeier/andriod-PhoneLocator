"""Tests for linking travel segments to adjacent visits."""

import unittest

from app.analytics.travel_links import match_adjacent_visit_ids


class TravelLinkTests(unittest.TestCase):
    def test_matches_visits_before_and_after_travel(self) -> None:
        visits = [
            {"id": 1, "started_at": "2026-08-01T10:00:00Z", "ended_at": "2026-08-01T11:00:00Z"},
            {"id": 2, "started_at": "2026-08-01T12:00:00Z", "ended_at": "2026-08-01T15:00:00Z"},
        ]
        from_id, to_id = match_adjacent_visit_ids(
            "2026-08-01T11:00:00Z",
            "2026-08-01T12:00:00Z",
            visits,
        )
        self.assertEqual(from_id, 1)
        self.assertEqual(to_id, 2)

    def test_returns_none_for_origin_when_travel_starts_before_any_visit(self) -> None:
        visits = [
            {"id": 1, "started_at": "2026-08-01T12:00:00Z", "ended_at": "2026-08-01T15:00:00Z"},
        ]
        from_id, to_id = match_adjacent_visit_ids(
            "2026-08-01T10:00:00Z",
            "2026-08-01T11:00:00Z",
            visits,
        )
        self.assertIsNone(from_id)
        self.assertEqual(to_id, 1)

    def test_returns_none_for_destination_when_travel_ends_after_all_visits(self) -> None:
        visits = [
            {"id": 1, "started_at": "2026-08-01T10:00:00Z", "ended_at": "2026-08-01T11:00:00Z"},
        ]
        from_id, to_id = match_adjacent_visit_ids(
            "2026-08-01T12:00:00Z",
            "2026-08-01T13:00:00Z",
            visits,
        )
        self.assertEqual(from_id, 1)
        self.assertIsNone(to_id)


if __name__ == "__main__":
    unittest.main()
