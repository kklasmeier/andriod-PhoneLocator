"""Optional live-API smoke tests against a running server (e.g. piSensors).

Set environment variables before running:
  PHONE_LOCATOR_TEST_URL=http://192.168.1.26:8000/locator
  PHONE_LOCATOR_API_TOKEN=<token from /etc/phone-locator/phone-locator.env>

Run via:  scripts/test.ps1 -Integration
"""

import os
import unittest
import uuid
from datetime import datetime, timezone

import httpx

TEST_URL = os.environ.get("PHONE_LOCATOR_TEST_URL", "").rstrip("/")
TEST_TOKEN = os.environ.get("PHONE_LOCATOR_API_TOKEN", "").strip()
DEVICE_ID = "integration-test-device"


def _skip_reason() -> str:
    missing = []
    if not TEST_URL:
        missing.append("PHONE_LOCATOR_TEST_URL")
    if not TEST_TOKEN:
        missing.append("PHONE_LOCATOR_API_TOKEN")
    return f"Set {', '.join(missing)} to run integration tests"


@unittest.skipUnless(TEST_URL and TEST_TOKEN, _skip_reason())
class IntegrationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = httpx.Client(
            base_url=TEST_URL,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
            timeout=10.0,
        )
        self.point_id = f"integration-{uuid.uuid4()}"

    def tearDown(self) -> None:
        self.client.close()

    def test_health_no_auth(self) -> None:
        response = httpx.get(f"{TEST_URL}/api/v1/health", timeout=10.0)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_batch_upload_and_latest(self) -> None:
        recorded_at = (
            datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        )
        payload = {
            "device_id": DEVICE_ID,
            "points": [
                {
                    "client_point_id": self.point_id,
                    "latitude": 42.123456,
                    "longitude": -83.123456,
                    "accuracy_m": 15.0,
                    "recorded_at": recorded_at,
                }
            ],
        }
        upload = self.client.post("/api/v1/location/batch", json=payload)
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertEqual(upload.json()["accepted"], 1)

        latest = self.client.get("/api/v1/location/latest", params={"device_id": DEVICE_ID})
        self.assertEqual(latest.status_code, 200, latest.text)
        body = latest.json()
        self.assertEqual(body["point"]["client_point_id"], self.point_id)


if __name__ == "__main__":
    unittest.main()
