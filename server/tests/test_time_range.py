"""Tests for strict calendar time-range filtering."""

import os
import tempfile
import unittest
from pathlib import Path

_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / "test-time-range.db"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(_test_db)

import app.config as config  # noqa: E402

from app import database  # noqa: E402


class TimeRangeFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_db = config.DATABASE_PATH
        config.DATABASE_PATH = _test_db
        if _test_db.exists():
            _test_db.unlink()
        database.init_db()
        self.device_id = "range-test-device"

        with database.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO visits (
                    device_id, place_id, started_at, ended_at, duration_sec,
                    center_lat, center_lon
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.device_id,
                    1,
                    "2026-07-31T22:00:00Z",
                    "2026-08-01T02:00:00Z",
                    4 * 3600,
                    42.0,
                    -83.0,
                ),
            )
            conn.execute(
                """
                INSERT INTO visits (
                    device_id, place_id, started_at, ended_at, duration_sec,
                    center_lat, center_lon
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.device_id,
                    2,
                    "2026-08-01T10:00:00Z",
                    "2026-08-01T12:00:00Z",
                    2 * 3600,
                    42.1,
                    -83.1,
                ),
            )

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._previous_db

    def test_filters_by_started_at_not_overlap(self) -> None:
        august_visits = database.get_visits(
            self.device_id,
            from_iso="2026-08-01T00:00:00Z",
            to_iso="2026-08-31T23:59:59Z",
        )
        self.assertEqual(len(august_visits), 1)
        self.assertEqual(august_visits[0]["place_id"], 2)

        july_visits = database.get_visits(
            self.device_id,
            from_iso="2026-07-01T00:00:00Z",
            to_iso="2026-07-31T23:59:59Z",
        )
        self.assertEqual(len(july_visits), 1)
        self.assertEqual(july_visits[0]["place_id"], 1)


if __name__ == "__main__":
    unittest.main()
