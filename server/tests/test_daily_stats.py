"""Daily stats rollups and trends API tests."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-daily"
os.environ["PHONE_LOCATOR_TIMEZONE"] = "America/Detroit"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "test.db")

from app import database  # noqa: E402
from app.main import app  # noqa: E402


class DailyStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-daily"}
        self.device_id = f"daily-phone-{uuid.uuid4()}"
        self.point = {
            "client_point_id": "ds-001",
            "latitude": 42.1,
            "longitude": -83.1,
            "recorded_at": "2026-07-26T10:00:00Z",
        }

    def _upload(self, point_id: str, lat: float, lon: float, recorded_at: str) -> None:
        payload = {
            "device_id": self.device_id,
            "points": [
                {
                    **self.point,
                    "client_point_id": point_id,
                    "latitude": lat,
                    "longitude": lon,
                    "recorded_at": recorded_at,
                }
            ],
        }
        response = self.client.post(
            "/api/v1/location/batch",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def _upload_stationary_day(self, prefix: str, day: str, hour: int = 10) -> None:
        for i, minute in enumerate([0, 3, 6, 9, 12, 15]):
            self._upload(
                f"{prefix}-{i}",
                42.1001,
                -83.1001,
                f"{day}T{hour + (minute // 60):02d}:{minute % 60:02d}:00Z",
            )

    def test_daily_stats_rebuilds_per_local_day(self) -> None:
        self._upload_stationary_day("d1", "2026-07-26")
        self._upload_stationary_day("d2", "2026-07-27")

        response = self.client.get(
            f"/api/v1/stats/trends?device_id={self.device_id}&from=2026-07-26&to=2026-07-27",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["granularity"], "day")
        self.assertEqual(len(body["buckets"]), 2)
        self.assertEqual(body["buckets"][0]["bucket"], "2026-07-26")
        self.assertGreater(body["buckets"][0]["point_count"], 0)
        self.assertGreater(body["buckets"][0]["stationary_duration_sec"], 0)

        cached_at = database.get_daily_stats_point_at(self.device_id)
        self.assertIsNotNone(cached_at)

    def test_daily_stats_self_heals_after_new_point(self) -> None:
        self._upload_stationary_day("heal1", "2026-07-26")
        first = self.client.get(
            f"/api/v1/stats/trends?device_id={self.device_id}&from=2026-07-26&to=2026-07-26",
            headers=self.headers,
        )
        self.assertEqual(first.json()["buckets"][0]["point_count"], 6)

        self._upload("heal-extra", 42.1001, -83.1001, "2026-07-26T18:00:00Z")
        second = self.client.get(
            f"/api/v1/stats/trends?device_id={self.device_id}&from=2026-07-26&to=2026-07-26",
            headers=self.headers,
        )
        self.assertEqual(second.json()["buckets"][0]["point_count"], 7)

    def test_trends_week_granularity(self) -> None:
        self._upload_stationary_day("w1", "2026-07-20")
        self._upload_stationary_day("w2", "2026-07-27")

        response = self.client.get(
            f"/api/v1/stats/trends?device_id={self.device_id}"
            f"&from=2026-07-20&to=2026-07-31&granularity=week",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["granularity"], "week")
        self.assertGreaterEqual(len(body["buckets"]), 2)
        self.assertIn("label", body["buckets"][0])
        self.assertIn("stationary_duration_sec", body["buckets"][0])


if __name__ == "__main__":
    unittest.main()
