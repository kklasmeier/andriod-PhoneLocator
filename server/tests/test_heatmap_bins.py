"""Heatmap grid bin tests."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-heatmap"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "test.db")

from app.analytics.heatmap_bins import CELL_SIZE_M, compute_heatmap_bins, point_to_grid  # noqa: E402
from app import database  # noqa: E402
from app.main import app  # noqa: E402


class HeatmapBinUnitTests(unittest.TestCase):
    def test_nearby_points_share_a_cell(self) -> None:
        points = [
            {"latitude": 42.1001, "longitude": -83.1001, "recorded_at": "2026-07-26T10:00:00Z"},
            {"latitude": 42.1002, "longitude": -83.1002, "recorded_at": "2026-07-26T10:03:00Z"},
        ]
        rows = compute_heatmap_bins(points)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["point_count"], 2)

    def test_distant_points_use_different_cells(self) -> None:
        glat1, glon1 = point_to_grid(42.1, -83.1)
        glat2, glon2 = point_to_grid(42.2, -83.2)
        self.assertNotEqual((glat1, glon1), (glat2, glon2))


class HeatmapApiTests(unittest.TestCase):
    def setUp(self) -> None:
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-heatmap"}
        self.device_id = f"heatmap-phone-{uuid.uuid4()}"

    def _upload(self, point_id: str, lat: float, lon: float, recorded_at: str) -> None:
        payload = {
            "device_id": self.device_id,
            "points": [
                {
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

    def test_heatmap_endpoint_returns_bins(self) -> None:
        for i in range(6):
            self._upload(
                f"hm-{i}",
                42.1001 + i * 0.00001,
                -83.1001 + i * 0.00001,
                f"2026-07-26T10:{i:02d}:00Z",
            )
        self._upload("hm-away", 42.2, -83.2, "2026-07-26T12:00:00Z")

        response = self.client.get(
            f"/api/v1/location/heatmap?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_id"], self.device_id)
        self.assertEqual(body["cell_size_m"], int(CELL_SIZE_M))
        self.assertGreaterEqual(body["bin_count"], 2)
        self.assertEqual(body["total_points"], 7)
        self.assertGreater(body["max_count"], 0)
        self.assertIn("center_lat", body["bins"][0])

        cached_at = database.get_heatmap_bins_point_at(self.device_id)
        self.assertIsNotNone(cached_at)

    def test_heatmap_self_heals_after_new_point(self) -> None:
        self._upload("hm-heal", 42.1, -83.1, "2026-07-26T10:00:00Z")
        first = self.client.get(
            f"/api/v1/location/heatmap?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(first.json()["total_points"], 1)

        self._upload("hm-heal-2", 42.2, -83.2, "2026-07-26T11:00:00Z")
        second = self.client.get(
            f"/api/v1/location/heatmap?device_id={self.device_id}",
            headers=self.headers,
        )
        self.assertEqual(second.json()["total_points"], 2)
        self.assertGreaterEqual(second.json()["bin_count"], 2)


if __name__ == "__main__":
    unittest.main()
