import hashlib
import json
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from datetime import timedelta

from django.test import RequestFactory, TestCase
from django.utils import timezone

from config.common import fail, get_device, ok, read_body, server_error
from devices.models import Command, Device
from identity.models import CardUser
from lockers.models import Compartment, Session

TOKEN = "0123456789abcdef0123456789abcdef"


class ResponseTests(TestCase):
    def test_ok_no_spaces(self):
        resp = ok({"a": 1, "b": [1, 2], "c": ""})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            resp.content, b'{"data":{"a":1,"b":[1,2],"c":""},"success":true}'
        )

    def test_fail_no_spaces_and_status(self):
        resp = fail("CARD_NOT_FOUND")
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(
            resp.content,
            b'{"error_code":"CARD_NOT_FOUND","message":"The khong hop le","success":false}',
        )

    def test_fail_status_codes(self):
        self.assertEqual(fail("TOO_SOON").status_code, 429)
        self.assertEqual(fail("DEVICE_UNAUTHORIZED").status_code, 401)
        self.assertEqual(fail("INVALID_PAYLOAD").status_code, 400)
        self.assertEqual(fail("SERVER_ERROR").status_code, 500)

    def test_unknown_path_returns_invalid_payload(self):
        resp = self.client.get("/api/v1/khong-co")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)["error_code"], "INVALID_PAYLOAD")

    def test_server_error_handler(self):
        resp = server_error(RequestFactory().get("/"))
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(json.loads(resp.content)["error_code"], "SERVER_ERROR")


class GetDeviceTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.device = Device.objects.create(
            device_id="LOCKER01",
            token_hash=hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
        )

    def test_correct_token(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Device " + TOKEN)
        self.assertEqual(get_device(request), self.device)

    def test_wrong_token(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Device " + "x" * 32)
        self.assertIsNone(get_device(request))

    def test_missing_header(self):
        request = self.factory.get("/")
        self.assertIsNone(get_device(request))

    def test_wrong_prefix(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Bearer " + TOKEN)
        self.assertIsNone(get_device(request))

    def test_empty_token(self):
        request = self.factory.get("/", HTTP_AUTHORIZATION="Device ")
        self.assertIsNone(get_device(request))


class ReadBodyTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def post(self, raw):
        return self.factory.post("/", data=raw, content_type="application/json")

    def test_valid_object(self):
        request = self.post(b'{"device_id":"LOCKER01"}')
        self.assertEqual(read_body(request, 256), {"device_id": "LOCKER01"})

    def test_too_large(self):
        raw = b'{"x":"' + b"a" * 300 + b'"}'
        self.assertIsNone(read_body(self.post(raw), 256))

    def test_exactly_max_size_ok(self):
        raw = b'{"x":"' + b"a" * 248 + b'"}'
        self.assertEqual(len(raw), 256)
        self.assertIsNotNone(read_body(self.post(raw), 256))

    def test_broken_json(self):
        self.assertIsNone(read_body(self.post(b'{"x":'), 256))

    def test_json_array(self):
        self.assertIsNone(read_body(self.post(b'[{"x":1}]'), 256))

    def test_not_utf8(self):
        self.assertIsNone(read_body(self.post(b'{"x":"\xff"}'), 256))

    def test_empty_body(self):
        self.assertIsNone(read_body(self.post(b""), 256))


class CreateDeviceTests(TestCase):
    def test_create_device(self):
        out = StringIO()
        call_command("create_device", "LOCKER01", stdout=out)
        token = out.getvalue().strip()

        self.assertEqual(Device.objects.count(), 1)
        device = Device.objects.get(device_id="LOCKER01")
        self.assertEqual(len(device.token_hash), 64)
        self.assertEqual(len(token), 32)
        self.assertEqual(
            device.token_hash, hashlib.sha256(token.encode("ascii")).hexdigest()
        )

        comps = Compartment.objects.filter(device=device).order_by("number")
        self.assertEqual(comps.count(), 2)
        numbers = []
        for comp in comps:
            numbers.append(comp.number)
            self.assertEqual(comp.status, "FREE")
            self.assertTrue(comp.door_closed)
            self.assertFalse(comp.has_item)
            self.assertIsNone(comp.last_unlock_at)
        self.assertEqual(numbers, [1, 2])

    def test_duplicate_device_rejected(self):
        call_command("create_device", "LOCKER01", stdout=StringIO())
        with self.assertRaises(CommandError):
            call_command("create_device", "LOCKER01", stdout=StringIO())
        self.assertEqual(Device.objects.count(), 1)


# B5: /heartbeat, /sync, /commands/{id}/ack


class DeviceApiBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.long_ago = self.now - timedelta(hours=2)
        self.device = Device.objects.create(
            device_id="LOCKER01",
            token_hash=hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
        )
        self.comp = Compartment.objects.create(
            device=self.device, number=1, status="FREE", status_changed_at=self.long_ago
        )
        self.comp2 = Compartment.objects.create(
            device=self.device, number=2, status="FREE", status_changed_at=self.long_ago
        )
        self.seq = 0

    def post(self, path, body):
        resp = self.client.post(
            path,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION="Device " + TOKEN,
        )
        return resp, json.loads(resp.content)

    def heartbeat(self):
        body = {
            "device_id": "LOCKER01",
            "uptime_sec": 36120,
            "rssi": -58,
            "free_heap": 142000,
            "pending_count": 3,
        }
        return self.post("/api/v1/heartbeat", body)

    def ack(self, command_id, result, seq):
        body = {
            "device_id": "LOCKER01",
            "request_id": "LOCKER01-%06d" % seq,
            "device_time": "2026-11-09T09:30:12+07:00",
            "result": result,
        }
        return self.post("/api/v1/commands/%d/ack" % command_id, body)

    def make_command(self, comp, created_ago_sec):
        return Command.objects.create(
            device=self.device,
            compartment=comp,
            type="OPEN",
            unlock_ms=800,
            reason="test",
            state="PENDING",
            created_at=timezone.now() - timedelta(seconds=created_ago_sec),
        )


class HeartbeatTests(DeviceApiBase):
    def test_updates_device(self):
        resp, body = self.heartbeat()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["data"], {"pending_commands": []})
        self.device.refresh_from_db()
        self.assertIsNotNone(self.device.last_heartbeat_at)
        self.assertEqual(self.device.last_rssi, -58)
        self.assertEqual(self.device.last_free_heap, 142000)
        self.assertEqual(self.device.last_pending_count, 3)

    def test_wrong_types(self):
        body = {
            "device_id": "LOCKER01",
            "uptime_sec": "36120",
            "rssi": -58,
            "free_heap": 142000,
            "pending_count": 0,
        }
        resp, data = self.post("/api/v1/heartbeat", body)
        self.assertEqual(data["error_code"], "INVALID_PAYLOAD")

    def test_runs_time_checks(self):
        command = self.make_command(self.comp, 301)
        self.heartbeat()
        command.refresh_from_db()
        self.assertEqual(command.state, "EXPIRED")


class ManualCommandTests(DeviceApiBase):
    def test_manual_open_flow(self):
        command = self.make_command(self.comp, 10)

        resp, body = self.heartbeat()
        self.assertEqual(
            body["data"]["pending_commands"],
            [{"command_id": command.id, "type": "OPEN", "compartment": 1, "unlock_ms": 800}],
        )

        first = self.ack(command.id, "DONE", 50)
        self.assertEqual(first[1], {"success": True, "data": {}})
        command.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(command.state, "DONE")
        self.assertIsNotNone(command.acked_at)
        self.assertEqual(self.comp.status, "OPEN")
        self.assertIsNotNone(self.comp.last_unlock_at)

        # Gui lai cung request_id: phan hoi y het
        again = self.ack(command.id, "DONE", 50)
        self.assertEqual(first[0].content, again[0].content)

        # Heartbeat sau khong con lenh
        self.assertEqual(self.heartbeat()[1]["data"]["pending_commands"], [])

    def test_occupied_manual_open_releasing(self):
        user = CardUser.objects.create(
            card_uid="A3F1C290", name="SV", source="STUDENT",
            external_id="B23DCCN924", created_at=self.long_ago,
        )
        self.comp.status = "OCCUPIED"
        self.comp.save()
        session = Session.objects.create(
            user=user, compartment=self.comp, state="OCCUPIED",
            created_at=self.long_ago, occupied_at=self.now - timedelta(minutes=95),
        )
        command = self.make_command(self.comp, 10)
        self.ack(command.id, "DONE", 51)
        session.refresh_from_db()
        self.assertEqual(session.state, "RELEASING")
        self.assertEqual(session.fee, 4000)

    def test_command_older_than_5_minutes_not_returned(self):
        self.make_command(self.comp, 301)
        resp = self.client.get(
            "/api/v1/sync?device_id=LOCKER01", HTTP_AUTHORIZATION="Device " + TOKEN
        )
        self.assertEqual(json.loads(resp.content)["data"]["pending_commands"], [])
        self.assertEqual(self.heartbeat()[1]["data"]["pending_commands"], [])

    def test_q7_compartment_not_rested(self):
        self.comp.last_unlock_at = timezone.now() - timedelta(seconds=30)
        self.comp.save()
        self.make_command(self.comp, 10)
        self.assertEqual(self.heartbeat()[1]["data"]["pending_commands"], [])

    def test_only_oldest_command(self):
        first = self.make_command(self.comp, 20)
        self.make_command(self.comp2, 10)
        commands = self.heartbeat()[1]["data"]["pending_commands"]
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0]["command_id"], first.id)

    def test_ack_failed(self):
        command = self.make_command(self.comp, 10)
        resp, body = self.ack(command.id, "FAILED", 52)
        self.assertTrue(body["success"])
        command.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(command.state, "FAILED")
        self.assertIsNotNone(command.acked_at)
        self.assertEqual(self.comp.status, "FREE")

    def test_q17_expired_command_done_still_applies(self):
        command = self.make_command(self.comp, 10)
        command.state = "EXPIRED"
        command.save()
        self.ack(command.id, "DONE", 53)
        command.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(command.state, "DONE")
        self.assertEqual(self.comp.status, "OPEN")

    def test_q17_done_command_ignored(self):
        command = self.make_command(self.comp, 10)
        command.state = "REJECTED"
        command.save()
        resp, body = self.ack(command.id, "DONE", 54)
        self.assertEqual(body, {"success": True, "data": {}})
        command.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(command.state, "REJECTED")
        self.assertEqual(self.comp.status, "FREE")

    def test_q17_unknown_command(self):
        resp, body = self.ack(99999, "DONE", 55)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")

    def test_q17_command_of_other_device(self):
        other = Device.objects.create(device_id="LOCKER02", token_hash="1" * 64)
        other_comp = Compartment.objects.create(
            device=other, number=1, status="FREE", status_changed_at=self.long_ago
        )
        command = Command.objects.create(
            device=other, compartment=other_comp, type="OPEN", unlock_ms=800,
            state="PENDING", created_at=timezone.now(),
        )
        resp, body = self.ack(command.id, "DONE", 56)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
        command.refresh_from_db()
        self.assertEqual(command.state, "PENDING")

    def test_invalid_result(self):
        command = self.make_command(self.comp, 10)
        resp, body = self.ack(command.id, "OK", 57)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")


class SyncTests(DeviceApiBase):
    def test_sync(self):
        user = CardUser.objects.create(
            card_uid="A3F1C290", name="SV", source="STUDENT", created_at=self.long_ago
        )
        self.comp2.status = "OCCUPIED"
        self.comp2.save()
        session = Session.objects.create(
            user=user, compartment=self.comp2, state="OCCUPIED", created_at=self.long_ago
        )
        resp = self.client.get(
            "/api/v1/sync?device_id=LOCKER01", HTTP_AUTHORIZATION="Device " + TOKEN
        )
        data = json.loads(resp.content)["data"]
        self.assertTrue(data["server_time"].endswith("+07:00"))
        self.assertEqual(len(data["server_time"]), 25)
        self.assertEqual(
            data["compartments"],
            [
                {"number": 1, "status": "FREE", "door_closed": True, "session_id": 0},
                {"number": 2, "status": "OCCUPIED", "door_closed": True, "session_id": session.id},
            ],
        )
        self.assertEqual(data["pending_commands"], [])

    def test_sync_does_not_run_time_checks(self):
        command = self.make_command(self.comp, 301)
        self.client.get("/api/v1/sync?device_id=LOCKER01", HTTP_AUTHORIZATION="Device " + TOKEN)
        command.refresh_from_db()
        self.assertEqual(command.state, "PENDING")

    def test_sync_device_mismatch(self):
        resp = self.client.get(
            "/api/v1/sync?device_id=LOCKER02", HTTP_AUTHORIZATION="Device " + TOKEN
        )
        self.assertEqual(json.loads(resp.content)["error_code"], "DEVICE_UNAUTHORIZED")

    def test_sync_wrong_method(self):
        resp, body = self.post("/api/v1/sync?device_id=LOCKER01", {})
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
