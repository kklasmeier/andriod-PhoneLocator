"""Lifetime stats cache and self-healing tests."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-lifetime"
os.environ["PHONE_LOCATOR_TIMEZONE"] = "America/Detroit"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "test.db")

from app import database  # noqa: E402
from app.main import app  # noqa: E402


class LifetimeStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-lifetime"}
        self.device_id = f"lifetime-phone-{uuid.uuid4()}"
        self.point = {
            "client_point_id": "lt-001",
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

    def test_lifetime_stats_after_upload(self) -> None:
        for i, minute in enumerate([0, 3, 6, 9, 12, 15]):
            self._upload(
                f"lt-home-{i}",
                42.1001,
                -83.1001,
                f"2026-07-26T10:{minute:02d}:00Z",
            )
        for i, minute in enumerate([0, 3, 6, 9, 12]):
            self._upload(
                f"lt-away-{i}",
                42.2,
                -83.2,
                f"2026-07-26T12:{minute:02d}:00Z",
            )

        response = self.client.get(
            f"/api/v1/stats/lifetime?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_id"], self.device_id)
        self.assertEqual(body["point_count"], 11)
        self.assertGreater(body["stationary_duration_sec"], 0)

        cached, cached_at = database.get_cached_lifetime_stats(self.device_id)
        self.assertIsNotNone(cached)
        self.assertIsNotNone(cached_at)
        self.assertEqual(cached["point_count"], 11)

    def test_lifetime_cache_rebuilds_after_new_point(self) -> None:
        self._upload("lt-a", 42.1, -83.1, "2026-07-26T10:00:00Z")
        first = self.client.get(
            f"/api/v1/stats/lifetime?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(first.json()["point_count"], 1)

        self._upload("lt-b", 42.2, -83.2, "2026-07-26T11:00:00Z")
        second = self.client.get(
            f"/api/v1/stats/lifetime?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(second.json()["point_count"], 2)

    def test_reports_includes_lifetime_only(self) -> None:
        self._upload("lt-r1", 42.1, -83.1, "2026-07-26T10:00:00Z")
        response = self.client.get(
            f"/api/v1/stats/reports?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_id"], self.device_id)
        self.assertIn("lifetime", body)
        self.assertEqual(body["lifetime"]["point_count"], 1)
        self.assertIn("lifetime_travel", body)
        self.assertIn("trip_count", body["lifetime_travel"])
        self.assertIn("frequent_routes", body["lifetime_travel"])
        self.assertNotIn("summary", body)
        self.assertNotIn("period_travel", body)

    def test_lifetime_tracking_day_counts(self) -> None:
        self._upload("d1", 42.1, -83.1, "2026-07-20T14:00:00Z")
        self._upload("d2", 42.1, -83.1, "2026-07-22T14:00:00Z")

        response = self.client.get(
            f"/api/v1/stats/lifetime?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["calendar_days"], 3)
        self.assertEqual(body["days_with_data"], 2)
        self.assertEqual(body["days_without_data"], 1)
        self.assertIn("travel_distance_m", body)


if __name__ == "__main__":
    unittest.main()
