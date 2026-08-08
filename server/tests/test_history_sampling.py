"""Tests for sampled location history across long periods."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / "test-history-sample.db"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(_test_db)

import app.config as config  # noqa: E402

from app import database  # noqa: E402


class HistorySamplingTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_db = config.DATABASE_PATH
        config.DATABASE_PATH = _test_db
        if _test_db.exists():
            _test_db.unlink()
        database.init_db()
        self.device_id = "history-sample-device"
        base = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

        with database.get_connection() as conn:
            for idx in range(120):
                recorded_at = (base + timedelta(hours=idx)).replace(microsecond=0)
                conn.execute(
                    """
                    INSERT INTO location_points (
                        device_id, client_point_id, latitude, longitude,
                        recorded_at, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.device_id,
                        f"pt-{idx:03d}",
                        41.0 + idx * 0.001,
                        -81.0,
                        recorded_at.isoformat().replace("+00:00", "Z"),
                        recorded_at.isoformat().replace("+00:00", "Z"),
                    ),
                )

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._previous_db

    def test_samples_evenly_across_range_when_over_limit(self) -> None:
        points, total_count, sampled = database.get_history(
            self.device_id,
            from_ts="2026-01-01T00:00:00Z",
            to_ts="2026-12-31T23:59:59Z",
            limit=20,
        )

        self.assertTrue(sampled)
        self.assertEqual(total_count, 120)
        self.assertLessEqual(len(points), 22)
        self.assertGreaterEqual(len(points), 18)
        self.assertEqual(points[0].client_point_id, "pt-000")
        self.assertEqual(points[-1].client_point_id, "pt-119")

    def test_returns_all_points_when_under_limit(self) -> None:
        points, total_count, sampled = database.get_history(
            self.device_id,
            from_ts="2026-01-01T00:00:00Z",
            to_ts="2026-12-31T23:59:59Z",
            limit=500,
        )

        self.assertFalse(sampled)
        self.assertEqual(total_count, 120)
        self.assertEqual(len(points), 120)


if __name__ == "__main__":
    unittest.main()
