"""Late points repair only the affected aggregates and never remove raw points."""

import os
import tempfile
import unittest
from pathlib import Path

_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "aggregate-sync.db")
os.environ["PHONE_LOCATOR_TIMEZONE"] = "America/Detroit"

import app.config as config  # noqa: E402
from app import database  # noqa: E402
from app.analytics.service import recompute_device  # noqa: E402
from app.models import LocationPointIn  # noqa: E402


class AggregateSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(config.DATABASE_PATH) + suffix)
            if path.exists():
                path.unlink()
        database.init_db()
        self.device_id = "aggregate-sync-phone"

    def _point(self, point_id: str, recorded_at: str, lat: float, lon: float) -> LocationPointIn:
        return LocationPointIn(
            client_point_id=point_id,
            latitude=lat,
            longitude=lon,
            recorded_at=recorded_at,
        )

    def _upload_stationary(self, prefix: str, day: str, lat: float, lon: float) -> None:
        points = [
            self._point(f"{prefix}-{minute}", f"{day}T{10 + minute // 60:02d}:{minute % 60:02d}:00Z", lat, lon)
            for minute in (0, 3, 6, 9, 12, 15)
        ]
        accepted, duplicates, errors = database.insert_points(self.device_id, points)
        self.assertEqual(errors, [])
        self.assertEqual(duplicates, 0)
        self.assertEqual(accepted, len(points))

    def _point_count(self, day: str) -> int:
        rows = database.get_daily_stats_range(self.device_id, day, day)
        return int(rows[0]["point_count"]) if rows else 0

    def test_late_point_updates_that_day_and_keeps_raw_history(self) -> None:
        self._upload_stationary("day1", "2026-07-26", 42.10, -83.10)
        self._upload_stationary("day3", "2026-07-28", 42.50, -83.50)
        self.assertEqual(database.count_location_points(self.device_id), 12)
        self.assertEqual(self._point_count("2026-07-26"), 6)
        self.assertEqual(self._point_count("2026-07-28"), 6)
        self.assertEqual(database.list_dirty_days(self.device_id), [])

        places = database.get_places(self.device_id)
        self.assertGreaterEqual(len(places), 1)
        renamed = database.update_place_name(places[0]["id"], self.device_id, "Home")
        self.assertIsNotNone(renamed)

        accepted, duplicates, errors = database.insert_points(
            self.device_id,
            [self._point("late-day1", "2026-07-26T18:00:00Z", 42.10, -83.10)],
        )
        self.assertEqual((accepted, duplicates, errors), (1, 0, []))
        self.assertEqual(database.count_location_points(self.device_id), 13)
        self.assertEqual(self._point_count("2026-07-26"), 7)
        self.assertEqual(self._point_count("2026-07-28"), 6)
        self.assertEqual(database.list_dirty_days(self.device_id), [])
        self.assertEqual(database.get_heatmap_summary(self.device_id)["total_points"], 13)
        self.assertTrue(any(place["name"] == "Home" for place in database.get_places(self.device_id)))

        recompute_device(self.device_id)
        self.assertEqual(database.count_location_points(self.device_id), 13)
        self.assertEqual(self._point_count("2026-07-26"), 7)
        self.assertEqual(self._point_count("2026-07-28"), 6)

    def test_duplicate_point_does_not_change_aggregates(self) -> None:
        point = self._point("once", "2026-07-26T15:00:00Z", 42.2, -83.2)
        database.insert_points(self.device_id, [point])
        database.insert_points(self.device_id, [point])

        self.assertEqual(database.count_location_points(self.device_id), 1)
        self.assertEqual(database.get_heatmap_summary(self.device_id)["total_points"], 1)
        self.assertEqual(self._point_count("2026-07-26"), 1)


if __name__ == "__main__":
    unittest.main()
