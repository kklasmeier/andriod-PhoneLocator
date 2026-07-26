"""Phase 1 API smoke tests."""

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

# Configure before importing app modules that read config at import time.
_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-phase1"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "test.db")

from app import database  # noqa: E402
from app.main import app  # noqa: E402


class Phase1ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-phase1"}
        self.point = {
            "client_point_id": "pt-001",
            "latitude": 42.123456,
            "longitude": -83.123456,
            "accuracy_m": 10.0,
            "battery_pct": 80,
            "battery_charging": False,
            "recorded_at": "2026-07-26T22:00:00Z",
        }

    def test_health_no_auth(self) -> None:
        response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_latest_requires_auth(self) -> None:
        response = self.client.get("/api/v1/location/latest?device_id=test-phone")
        self.assertEqual(response.status_code, 401)

    def test_batch_upload_and_dedupe(self) -> None:
        payload = {"device_id": "test-phone", "points": [self.point]}
        first = self.client.post(
            "/api/v1/location/batch",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json(), {"accepted": 1, "duplicates": 0, "errors": []})

        second = self.client.post(
            "/api/v1/location/batch",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json(), {"accepted": 0, "duplicates": 1, "errors": []})

    def test_latest_and_history(self) -> None:
        self.client.post(
            "/api/v1/location/batch",
            json={"device_id": "test-phone", "points": [self.point]},
            headers=self.headers,
        )

        latest = self.client.get(
            "/api/v1/location/latest?device_id=test-phone",
            headers=self.headers,
        )
        self.assertEqual(latest.status_code, 200)
        body = latest.json()
        self.assertEqual(body["device_id"], "test-phone")
        self.assertIsNotNone(body["point"])
        assert body["point"] is not None
        self.assertEqual(body["point"]["client_point_id"], "pt-001")
        self.assertTrue(body["point"]["received_at"])

        history = self.client.get(
            "/api/v1/location/history?device_id=test-phone",
            headers=self.headers,
        )
        self.assertEqual(history.status_code, 200)
        self.assertEqual(history.json()["count"], 1)


if __name__ == "__main__":
    unittest.main()
