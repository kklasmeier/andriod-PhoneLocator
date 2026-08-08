"""Dashboard today view with week teaser."""

import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

_test_dir = tempfile.mkdtemp()
_test_db = Path(_test_dir) / "test-dashboard.db"
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-dashboard"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(_test_db)
os.environ["PHONE_LOCATOR_TIMEZONE"] = "America/Detroit"

from fastapi.testclient import TestClient  # noqa: E402

import app.config as config  # noqa: E402

from app import database  # noqa: E402
from app.main import app  # noqa: E402


class DashboardTodayTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_db = config.DATABASE_PATH
        config.DATABASE_PATH = _test_db
        if _test_db.exists():
            _test_db.unlink()
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-dashboard"}
        self.device_id = "dashboard-phone"
        now = datetime.now(timezone.utc).replace(microsecond=0)
        now_iso = now.isoformat().replace("+00:00", "Z")
        response = self.client.post(
            "/api/v1/location/batch",
            json={
                "device_id": self.device_id,
                "points": [
                    {
                        "client_point_id": "dash-pt-1",
                        "latitude": 42.28,
                        "longitude": -83.74,
                        "recorded_at": now_iso,
                    }
                ],
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.now_iso = now_iso

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._previous_db

    def test_dashboard_today_with_week_teaser(self) -> None:
        from_local = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        response = self.client.get(
            "/api/v1/stats/dashboard",
            params={
                "device_id": self.device_id,
                "from": from_local,
                "to": self.now_iso,
                "include_week_teaser": True,
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertIn("from", body)
        self.assertIn("summary", body)
        self.assertIn("week_teaser", body["summary"])


if __name__ == "__main__":
    unittest.main()
