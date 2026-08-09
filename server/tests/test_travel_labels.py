"""Tests for travel route labeling."""

import unittest

from app.analytics.travel_labels import enrich_travel_segment, is_local_loop_travel


class TravelLabelTests(unittest.TestCase):
    def test_round_trip_label(self) -> None:
        row = enrich_travel_segment(
            {"distance_m": 15000.0, "duration_sec": 1200},
            from_place_name="Home",
            to_place_name="Home",
            from_place_id=1,
            to_place_id=1,
        )
        self.assertEqual(row["route_kind"], "round_trip")
        self.assertEqual(row["route_label"], "Round trip from Home")

    def test_local_loop_label(self) -> None:
        row = enrich_travel_segment(
            {"distance_m": 117.0, "duration_sec": 360},
            from_place_name="Chili's",
            to_place_name="Chili's",
            from_place_id=2,
            to_place_id=2,
        )
        self.assertEqual(row["route_kind"], "local")
        self.assertIn("local", row["route_label"])

    def test_normal_trip_label(self) -> None:
        row = enrich_travel_segment(
            {"distance_m": 5000.0, "duration_sec": 600},
            from_place_name="Home",
            to_place_name="Work",
            from_place_id=1,
            to_place_id=3,
        )
        self.assertEqual(row["route_kind"], "trip")
        self.assertEqual(row["route_label"], "Home → Work")

    def test_is_local_loop_travel(self) -> None:
        self.assertTrue(is_local_loop_travel(from_place_id=1, to_place_id=1, distance_m=400))
        self.assertFalse(is_local_loop_travel(from_place_id=1, to_place_id=1, distance_m=5000))
        self.assertFalse(is_local_loop_travel(from_place_id=1, to_place_id=2, distance_m=100))


if __name__ == "__main__":
    unittest.main()
