"""Tests for paginated raw history queries."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / "test-history-page.db"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(_test_db)

import app.config as config  # noqa: E402

from app import database  # noqa: E402


class HistoryPaginationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_db = config.DATABASE_PATH
        config.DATABASE_PATH = _test_db
        if _test_db.exists():
            _test_db.unlink()
        database.init_db()
        self.device_id = "history-page-device"
        base = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)

        with database.get_connection() as conn:
            for idx in range(5):
                recorded_at = (base + timedelta(minutes=idx)).replace(microsecond=0)
                conn.execute(
                    """
                    INSERT INTO location_points (
                        device_id, client_point_id, latitude, longitude,
                        recorded_at, received_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        self.device_id,
                        f"hist-{idx}",
                        42.0 + idx * 0.001,
                        -83.0,
                        recorded_at.isoformat().replace("+00:00", "Z"),
                        recorded_at.isoformat().replace("+00:00", "Z"),
                    ),
                )
            conn.commit()

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._previous_db

    def test_desc_pagination_without_sampling(self) -> None:
        page1, total, sampled = database.get_history(
            self.device_id,
            limit=2,
            offset=0,
            order="desc",
            sample=False,
        )
        page2, _, _ = database.get_history(
            self.device_id,
            limit=2,
            offset=2,
            order="desc",
            sample=False,
        )

        self.assertFalse(sampled)
        self.assertEqual(total, 5)
        self.assertEqual([p.client_point_id for p in page1], ["hist-4", "hist-3"])
        self.assertEqual([p.client_point_id for p in page2], ["hist-2", "hist-1"])


if __name__ == "__main__":
    unittest.main()
