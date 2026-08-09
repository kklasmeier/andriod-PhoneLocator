"""Device command queue tests (ring phone)."""

import os
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

_test_dir = tempfile.mkdtemp()
os.environ["PHONE_LOCATOR_API_TOKEN"] = "test-token-commands"
os.environ["PHONE_LOCATOR_DATABASE_PATH"] = str(Path(_test_dir) / "test.db")

from app import database  # noqa: E402
from app.main import app  # noqa: E402


class DeviceCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        database.init_db()
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer test-token-commands"}
        self.device_id = f"test-phone-{uuid.uuid4()}"

    def test_create_and_poll_ring_command(self) -> None:
        created = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring", "duration_sec": 60},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        body = created.json()
        self.assertEqual(body["status"], "pending")
        self.assertEqual(body["type"], "ring")
        self.assertEqual(body["duration_sec"], 60)
        command_id = body["id"]

        polled = self.client.get(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}",
            headers=self.headers,
        )
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(polled.json()["status"], "pending")

    def test_rate_limit(self) -> None:
        first = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring"},
            headers=self.headers,
        )
        self.assertEqual(first.status_code, 200)

        second = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring"},
            headers=self.headers,
        )
        self.assertEqual(second.status_code, 429)

    def test_pending_claim_start_stop_and_ack(self) -> None:
        created = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring", "duration_sec": 120},
            headers=self.headers,
        )
        command_id = created.json()["id"]

        pending = self.client.get(
            f"/api/v1/devices/{self.device_id}/commands/pending",
            headers=self.headers,
        )
        self.assertEqual(pending.status_code, 200)
        commands = pending.json()["commands"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["id"], command_id)
        self.assertEqual(commands[0]["duration_sec"], 120)

        status = self.client.get(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}",
            headers=self.headers,
        )
        self.assertEqual(status.json()["status"], "delivered")

        started = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}/start",
            headers=self.headers,
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "ringing")
        self.assertIsNotNone(started.json()["ring_started_at"])

        stop_req = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}/stop",
            headers=self.headers,
        )
        self.assertEqual(stop_req.status_code, 200)
        self.assertTrue(stop_req.json()["stop_requested"])

        polled = self.client.get(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}",
            headers=self.headers,
        )
        self.assertTrue(polled.json()["stop_requested"])

        acked = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}/ack",
            json={
                "latitude": 42.1,
                "longitude": -83.2,
                "message": "stopped from web",
                "stopped_by": "web",
            },
            headers=self.headers,
        )
        self.assertEqual(acked.status_code, 200)
        ack_body = acked.json()
        self.assertEqual(ack_body["status"], "stopped")
        self.assertEqual(ack_body["stopped_by"], "web")
        self.assertEqual(ack_body["ack_latitude"], 42.1)

    def test_ack_completed(self) -> None:
        created = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring"},
            headers=self.headers,
        )
        command_id = created.json()["id"]
        self.client.get(
            f"/api/v1/devices/{self.device_id}/commands/pending",
            headers=self.headers,
        )
        self.client.post(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}/start",
            headers=self.headers,
        )
        acked = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands/{command_id}/ack",
            json={"message": "duration elapsed", "stopped_by": "completed"},
            headers=self.headers,
        )
        self.assertEqual(acked.json()["status"], "completed")

    def test_batch_upload_returns_pending_commands(self) -> None:
        created = self.client.post(
            f"/api/v1/devices/{self.device_id}/commands",
            json={"type": "ring", "duration_sec": 90},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 200)
        command_id = created.json()["id"]

        point = {
            "client_point_id": "cmd-pt-001",
            "latitude": 42.0,
            "longitude": -83.0,
            "recorded_at": "2026-07-26T22:00:00Z",
        }
        batch = self.client.post(
            "/api/v1/location/batch",
            json={"device_id": self.device_id, "points": [point]},
            headers=self.headers,
        )
        self.assertEqual(batch.status_code, 200)
        batch_body = batch.json()
        self.assertEqual(batch_body["accepted"], 1)
        self.assertEqual(len(batch_body["commands"]), 1)
        self.assertEqual(batch_body["commands"][0]["id"], command_id)
        self.assertEqual(batch_body["commands"][0]["duration_sec"], 90)


if __name__ == "__main__":
    unittest.main()
