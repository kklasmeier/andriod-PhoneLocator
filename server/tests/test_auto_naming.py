"""Tests for reverse geocode label formatting and auto-naming planner."""

import unittest

from app.analytics.auto_naming import plan_auto_naming
from app.analytics.geocode import format_geocode_label


class GeocodeLabelTests(unittest.TestCase):
    def test_poi_preferred(self) -> None:
        label = format_geocode_label(
            {
                "name": "Meijer",
                "class": "shop",
                "address": {"road": "Main Street", "city": "Ann Arbor"},
            }
        )
        self.assertEqual(label, "Meijer")

    def test_street_and_city_fallback(self) -> None:
        label = format_geocode_label(
            {
                "class": "building",
                "address": {"road": "Oak Street", "city": "Ann Arbor"},
            }
        )
        self.assertEqual(label, "Oak Street, Ann Arbor")

    def test_road_only(self) -> None:
        label = format_geocode_label({"address": {"road": "Oak Street"}})
        self.assertEqual(label, "Oak Street")


class AutoNamingPlanTests(unittest.TestCase):
    def test_groups_and_inherits_near_named_place(self) -> None:
        places = [
            {
                "id": 1,
                "name": "Home",
                "center_lat": 42.0,
                "center_lon": -83.0,
                "visit_count": 10,
            },
            {
                "id": 2,
                "name": None,
                "center_lat": 42.0001,
                "center_lon": -83.0001,
                "visit_count": 5,
            },
            {
                "id": 3,
                "name": None,
                "center_lat": 41.0,
                "center_lon": -82.0,
                "visit_count": 2,
            },
        ]
        visits = [
            {"place_id": 2, "duration_sec": 600},
            {"place_id": 3, "duration_sec": 600},
        ]
        plan = plan_auto_naming(places, visits)
        self.assertEqual(len(plan["inherit_groups"]), 1)
        self.assertEqual(plan["inherit_groups"][0]["name"], "Home")
        self.assertEqual(plan["inherit_groups"][0]["place_ids"], [2])
        self.assertEqual(plan["geocode_queries_needed"], 1)

    def test_qualifies_on_total_visit_time(self) -> None:
        places = [
            {
                "id": 10,
                "name": None,
                "center_lat": 41.0,
                "center_lon": -82.0,
                "visit_count": 3,
            }
        ]
        visits = [
            {"place_id": 10, "duration_sec": 120},
            {"place_id": 10, "duration_sec": 120},
            {"place_id": 10, "duration_sec": 120},
        ]
        plan = plan_auto_naming(places, visits)
        self.assertEqual(plan["geocode_queries_needed"], 1)


if __name__ == "__main__":
    unittest.main()
