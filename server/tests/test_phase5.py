"""Phase 5 analytics tests."""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

_test_dir = tempfile.mkdtemp()
_phase5_db = Path(_test_dir) / "test.db"
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-phase1"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(_phase5_db)
os.environ["PHONE_LOCATOR_TIMEZONE"] = "America/Detroit"

import app.config as config  # noqa: E402

from app import database  # noqa: E402
from app.analytics.engine import segment_points, TrackPoint  # noqa: E402
from app.main import app  # noqa: E402

HOME_LAT, HOME_LON = 42.2800, -83.7400
WORK_LAT, WORK_LON = 42.2900, -83.7300


def _point(
    device_id: str,
    idx: int,
    lat: float,
    lon: float,
    speed_mps: float = 0.0,
    base: datetime | None = None,
) -> dict:
    if base is None:
        base = datetime(2026, 8, 7, 12, 0, tzinfo=timezone.utc)
    recorded_at = (base + timedelta(minutes=idx * 10)).replace(microsecond=0)
    return {
        "client_point_id": f"{device_id}-pt-{idx:03d}",
        "latitude": lat,
        "longitude": lon,
        "accuracy_m": 8.0,
        "speed_mps": speed_mps,
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
    }


class Phase5EngineTests(unittest.TestCase):
    def test_segment_home_travel_work(self) -> None:
        points = [
            TrackPoint("2026-08-07T12:00:00Z", HOME_LAT, HOME_LON, 0.0),
            TrackPoint("2026-08-07T12:10:00Z", HOME_LAT, HOME_LON, 0.0),
            TrackPoint("2026-08-07T12:20:00Z", HOME_LAT + 0.001, HOME_LON, 5.0),
            TrackPoint("2026-08-07T12:30:00Z", HOME_LAT + 0.003, HOME_LON, 8.0),
            TrackPoint("2026-08-07T12:40:00Z", WORK_LAT, WORK_LON, 0.0),
            TrackPoint("2026-08-07T12:50:00Z", WORK_LAT, WORK_LON, 0.0),
        ]
        visits, travels = segment_points(points)
        self.assertEqual(len(visits), 2)
        self.assertEqual(len(travels), 1)
        self.assertGreater(travels[0].distance_m, 100)
        self.assertGreater(visits[0].duration_sec, 0)
        self.assertGreaterEqual(visits[1].duration_sec, 0)


class Phase5ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_db = config.DATABASE_PATH
        config.DATABASE_PATH = _phase5_db
        if _phase5_db.exists():
            _phase5_db.unlink()
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-phase1"}
        self.device_id = "phase5-phone"

        payload_points = [
            _point(self.device_id, 0, HOME_LAT, HOME_LON, 0.0),
            _point(self.device_id, 1, HOME_LAT, HOME_LON, 0.0),
            _point(self.device_id, 2, HOME_LAT + 0.002, HOME_LON, 6.0),
            _point(self.device_id, 3, HOME_LAT + 0.004, HOME_LON, 7.0),
            _point(self.device_id, 4, WORK_LAT, WORK_LON, 0.0),
            _point(self.device_id, 5, WORK_LAT, WORK_LON, 0.0),
        ]
        response = self.client.post(
            "/api/v1/location/batch",
            json={"device_id": self.device_id, "points": payload_points},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)

    def tearDown(self) -> None:
        config.DATABASE_PATH = self._previous_db

    def test_analytics_requires_auth(self) -> None:
        response = self.client.get(f"/api/v1/places?device_id={self.device_id}")
        self.assertEqual(response.status_code, 401)

    def test_places_visits_travel_and_summary(self) -> None:
        places = self.client.get(
            f"/api/v1/places?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(places.status_code, 200)
        places_body = places.json()
        self.assertGreaterEqual(places_body["count"], 1)

        visits = self.client.get(
            f"/api/v1/visits?device_id={self.device_id}"
            "&from=2026-08-07T00:00:00Z&to=2026-08-08T00:00:00Z",
            headers=self.headers,
        )
        self.assertEqual(visits.status_code, 200)
        visits_body = visits.json()
        self.assertGreater(visits_body["count"], 0)
        kinds = {item["kind"] for item in visits_body["items"]}
        self.assertIn("visit", kinds)
        self.assertIn("travel", kinds)

        travel = self.client.get(
            f"/api/v1/travel?device_id={self.device_id}"
            "&from=2026-08-07T00:00:00Z&to=2026-08-08T00:00:00Z",
            headers=self.headers,
        )
        self.assertEqual(travel.status_code, 200)
        self.assertGreater(travel.json()["count"], 0)

        with patch(
            "app.analytics.service.resolve_period",
            return_value=("2026-08-07T00:00:00Z", "2026-08-08T00:00:00Z"),
        ):
            summary = self.client.get(
                f"/api/v1/stats/summary?device_id={self.device_id}&period=today",
                headers=self.headers,
            )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["device_id"], self.device_id)
        self.assertEqual(body["period"], "today")
        self.assertGreaterEqual(body["places_count"], 1)
        self.assertGreater(body["travel_duration_sec"], 0)
        self.assertGreater(body["stationary_duration_sec"], 0)
        self.assertIn("week_teaser", body)

    def test_rename_place(self) -> None:
        places = self.client.get(
            f"/api/v1/places?device_id={self.device_id}",
            headers=self.headers,
        ).json()
        place_id = places["places"][0]["id"]
        renamed = self.client.put(
            f"/api/v1/places/{place_id}?device_id={self.device_id}",
            json={"name": "Home"},
            headers=self.headers,
        )
        self.assertEqual(renamed.status_code, 200)
        self.assertEqual(renamed.json()["name"], "Home")

        from app.analytics import service as analytics_service

        analytics_service.recompute_device(self.device_id)
        places_after = self.client.get(
            f"/api/v1/places?device_id={self.device_id}",
            headers=self.headers,
        ).json()
        names = [p["name"] for p in places_after["places"]]
        self.assertIn("Home", names)


if __name__ == "__main__":
    unittest.main()
