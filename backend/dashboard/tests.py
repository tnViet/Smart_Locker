import hashlib
import json
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.utils import timezone

from dashboard.auth import make_token
from devices.models import Command, Device
from identity.models import CardUser
from lockers.models import Compartment, Event, Session

DEVICE_TOKEN = "0123456789abcdef0123456789abcdef"


class DashboardBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.long_ago = self.now - timedelta(hours=3)
        self.admin = User.objects.create_user("admin", password="admin-pass")
        self.admin.groups.add(Group.objects.get(name="admin"))
        self.viewer = User.objects.create_user("viewer", password="viewer-pass")
        self.viewer.groups.add(Group.objects.get(name="viewer"))
        self.admin_token = make_token(self.admin, self.now)
        self.viewer_token = make_token(self.viewer, self.now)

        self.device = Device.objects.create(
            device_id="LOCKER01",
            token_hash=hashlib.sha256(DEVICE_TOKEN.encode("ascii")).hexdigest(),
        )
        self.comp1 = Compartment.objects.create(
            device=self.device, number=1, status="FREE",
            status_changed_at=self.long_ago, last_unlock_at=self.long_ago,
        )
        self.comp2 = Compartment.objects.create(
            device=self.device, number=2, status="FREE",
            status_changed_at=self.long_ago, last_unlock_at=self.long_ago,
        )
        self.card = CardUser.objects.create(
            card_uid="A3F1C290", name="Trần Ngọc Việt", source="STUDENT",
            external_id="B23DCCN924", created_at=self.long_ago,
        )

    def call(self, method, path, token, body):
        headers = {}
        if token is not None:
            headers["HTTP_AUTHORIZATION"] = "Bearer " + token
        if method == "GET":
            resp = self.client.get(path, **headers)
        else:
            data = ""
            if body is not None:
                data = json.dumps(body)
            resp = self.client.generic(
                method, path, data=data, content_type="application/json", **headers
            )
        return resp, json.loads(resp.content)

    def occupy(self, comp, minutes):
        comp.status = "OCCUPIED"
        comp.has_item = True
        comp.save()
        return Session.objects.create(
            user=self.card, compartment=comp, state="OCCUPIED",
            created_at=self.now - timedelta(minutes=minutes, seconds=30),
            occupied_at=self.now - timedelta(minutes=minutes, seconds=10),
        )


class AuthTests(DashboardBase):
    def test_login_ok(self):
        resp, body = self.call("POST", "/api/v1/auth/login", None,
                               {"username": "admin", "password": "admin-pass"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(body["data"]["role"], "admin")
        self.assertEqual(body["data"]["expires_in"], 28800)
        payload = jwt.decode(body["data"]["access_token"], settings.JWT_SECRET, algorithms=["HS256"])
        self.assertEqual(payload["sub"], str(self.admin.id))

        resp, body = self.call("POST", "/api/v1/auth/login", None,
                               {"username": "viewer", "password": "viewer-pass"})
        self.assertEqual(body["data"]["role"], "viewer")

    def test_login_wrong_password(self):
        resp, body = self.call("POST", "/api/v1/auth/login", None,
                               {"username": "admin", "password": "sai"})
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(body["error_code"], "UNAUTHORIZED")

    def test_expired_token(self):
        old_token = make_token(self.admin, self.now - timedelta(hours=9))
        resp, body = self.call("GET", "/api/v1/compartments", old_token, None)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(body["error_code"], "UNAUTHORIZED")

    def test_bad_or_missing_token(self):
        resp, body = self.call("GET", "/api/v1/compartments", "abc.def.ghi", None)
        self.assertEqual(resp.status_code, 401)
        resp, body = self.call("GET", "/api/v1/compartments", None, None)
        self.assertEqual(resp.status_code, 401)

    def test_viewer_can_read(self):
        for path in [
            "/api/v1/compartments",
            "/api/v1/sessions",
            "/api/v1/users",
            "/api/v1/stats/overview",
            "/api/v1/stats/revenue?from=2026-11-01&to=2026-11-09",
            "/api/v1/devices",
            "/api/v1/fee-rules",
        ]:
            resp, body = self.call("GET", path, self.viewer_token, None)
            self.assertEqual(resp.status_code, 200, path)

    def test_viewer_forbidden_on_admin_apis(self):
        session = self.occupy(self.comp1, 10)
        calls = [
            ("POST", "/api/v1/sessions/%d/pay" % session.id, None),
            ("POST", "/api/v1/users", {"card_uid": "C0FFEE01", "name": "A"}),
            ("PATCH", "/api/v1/users/%d" % self.card.id, {"blocked": True}),
            ("POST", "/api/v1/admin/open", {"device_id": "LOCKER01", "compartment": 2, "reason": "x"}),
            ("POST", "/api/v1/admin/reset", {"device_id": "LOCKER01", "compartment": 2}),
            ("PATCH", "/api/v1/fee-rules", {"block_fee": 1}),
        ]
        for method, path, body in calls:
            resp, data = self.call(method, path, self.viewer_token, body)
            self.assertEqual(resp.status_code, 403, path)
            self.assertEqual(data["error_code"], "FORBIDDEN", path)
        session.refresh_from_db()
        self.assertEqual(session.payment_status, "NONE")
        self.assertEqual(Command.objects.count(), 0)

    def test_wrong_method(self):
        resp, body = self.call("POST", "/api/v1/compartments", self.admin_token, {})
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")


class SessionListTests(DashboardBase):
    def test_pagination_and_filters(self):
        other = CardUser.objects.create(
            card_uid="B4E2D301", name="Khach", source="LOCAL", created_at=self.long_ago
        )
        for i in range(25):
            Session.objects.create(
                user=other, compartment=self.comp1, state="CLOSED",
                created_at=self.now - timedelta(seconds=i),
            )
        for i in range(3):
            Session.objects.create(
                user=other, compartment=self.comp1, state="CANCELLED",
                created_at=self.now - timedelta(days=2, seconds=i),
            )
        occupied = self.occupy(self.comp2, 1)

        today = timezone.localdate(self.now).isoformat()
        resp, body = self.call(
            "GET", "/api/v1/sessions?page=3&page_size=10&date=" + today, self.viewer_token, None
        )
        data = body["data"]
        self.assertEqual(data["page"], 3)
        self.assertEqual(data["page_size"], 10)
        self.assertEqual(data["count"], 26)
        self.assertEqual(len(data["results"]), 6)

        resp, body = self.call("GET", "/api/v1/sessions", self.viewer_token, None)
        self.assertEqual(body["data"]["count"], 29)
        self.assertEqual(body["data"]["page_size"], 20)
        self.assertEqual(len(body["data"]["results"]), 20)

        resp, body = self.call("GET", "/api/v1/sessions?state=OCCUPIED", self.viewer_token, None)
        self.assertEqual(body["data"]["count"], 1)
        row = body["data"]["results"][0]
        self.assertEqual(row["id"], occupied.id)
        self.assertEqual(row["user_name"], "Trần Ngọc Việt")
        self.assertEqual(row["card_uid"], "A3F1C290")
        self.assertEqual(row["compartment"], 2)
        self.assertTrue(row["created_at"].endswith("+07:00"))
        self.assertIsNone(row["closed_at"])

        resp, body = self.call(
            "GET", "/api/v1/sessions?user_id=%d" % other.id, self.viewer_token, None
        )
        self.assertEqual(body["data"]["count"], 28)

    def test_bad_params(self):
        for query in ["page=0", "page_size=abc", "date=2026-13-01", "state=DONE"]:
            resp, body = self.call("GET", "/api/v1/sessions?" + query, self.viewer_token, None)
            self.assertEqual(body["error_code"], "INVALID_PAYLOAD", query)

    def test_detail_with_events(self):
        session = self.occupy(self.comp1, 10)
        Event.objects.create(
            device=self.device, request_id="LOCKER01-000001", event_type="DOOR_CLOSED",
            session=session, compartment_number=1, has_item=True,
            device_time=self.now, received_at=self.now, accepted=True, error_code="",
        )
        resp, body = self.call("GET", "/api/v1/sessions/%d" % session.id, self.viewer_token, None)
        self.assertEqual(body["data"]["id"], session.id)
        self.assertEqual(len(body["data"]["events"]), 1)
        self.assertEqual(body["data"]["events"][0]["event_type"], "DOOR_CLOSED")

        resp, body = self.call("GET", "/api/v1/sessions/999999", self.viewer_token, None)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(body["error_code"], "NOT_FOUND")


class AdminActionTests(DashboardBase):
    def scan(self, seq):
        resp = self.client.post(
            "/api/v1/scan",
            data=json.dumps({
                "device_id": "LOCKER01", "card_uid": "A3F1C290",
                "request_id": "LOCKER01-%06d" % seq,
                "device_time": "2026-11-09T09:12:30+07:00",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION="Device " + DEVICE_TOKEN,
        )
        return json.loads(resp.content)

    def heartbeat(self):
        resp = self.client.post(
            "/api/v1/heartbeat",
            data=json.dumps({
                "device_id": "LOCKER01", "uptime_sec": 10, "rssi": -60,
                "free_heap": 100000, "pending_count": 0,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION="Device " + DEVICE_TOKEN,
        )
        return json.loads(resp.content)

    def test_admin_open_then_heartbeat(self):
        resp, body = self.call("POST", "/api/v1/admin/open", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 2, "reason": "Khach quen the"})
        command = Command.objects.get()
        self.assertEqual(body["data"], {"command_id": command.id})
        self.assertEqual(command.unlock_ms, 800)
        self.assertEqual(command.created_by, self.admin)
        self.assertEqual(command.state, "PENDING")

        data = self.heartbeat()["data"]
        self.assertEqual(data["pending_commands"], [
            {"command_id": command.id, "type": "OPEN", "compartment": 2, "unlock_ms": 800},
        ])

    def test_admin_open_too_soon(self):
        self.comp1.last_unlock_at = timezone.now() - timedelta(seconds=30)
        self.comp1.save()
        resp, body = self.call("POST", "/api/v1/admin/open", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 1, "reason": "x"})
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(body["error_code"], "TOO_SOON")
        self.assertEqual(Command.objects.count(), 0)

    def test_admin_open_on_open_compartment(self):
        self.comp1.status = "OPEN"
        self.comp1.save()
        resp, body = self.call("POST", "/api/v1/admin/open", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 1, "reason": "x"})
        self.assertEqual(body["error_code"], "SESSION_CONFLICT")

    def test_admin_open_unknown(self):
        resp, body = self.call("POST", "/api/v1/admin/open", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 9, "reason": "x"})
        self.assertEqual(body["error_code"], "NOT_FOUND")

    def test_admin_reset(self):
        session = self.occupy(self.comp1, 10)
        self.comp1.status = "ERROR"
        self.comp1.save()
        resp, body = self.call("POST", "/api/v1/admin/reset", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 1})
        self.assertEqual(body["error_code"], "COMPARTMENT_ERROR")

        session.state = "CLOSED"
        session.closed_at = timezone.now()
        session.save()
        resp, body = self.call("POST", "/api/v1/admin/reset", self.admin_token,
                               {"device_id": "LOCKER01", "compartment": 1})
        self.assertEqual(body["data"], {"number": 1, "status": "FREE"})
        self.comp1.refresh_from_db()
        self.assertEqual(self.comp1.status, "FREE")

    def test_mark_paid_then_scan_pickup(self):
        session = self.occupy(self.comp1, 95)
        resp, body = self.call("POST", "/api/v1/sessions/%d/pay" % session.id, self.admin_token, None)
        self.assertEqual(body["data"], {"id": session.id, "payment_status": "PAID"})

        data = self.scan(1)["data"]
        self.assertEqual(data["action"], "PICKUP")
        self.assertEqual(data["compartment"], 1)
        session.refresh_from_db()
        self.assertEqual(session.state, "RELEASING")

    def test_mark_paid_needs_occupied(self):
        session = self.occupy(self.comp1, 95)
        session.state = "CLOSED"
        session.save()
        resp, body = self.call("POST", "/api/v1/sessions/%d/pay" % session.id, self.admin_token, None)
        self.assertEqual(body["error_code"], "SESSION_CONFLICT")

    def test_fee_rules_update_changes_current_fee(self):
        self.occupy(self.comp1, 95)
        resp, body = self.call("GET", "/api/v1/compartments", self.viewer_token, None)
        self.assertEqual(body["data"][0]["session"]["current_fee"], 4000)
        self.assertEqual(body["data"][0]["session"]["duration_min"], 95)
        self.assertIsNone(body["data"][1]["session"])

        resp, body = self.call("PATCH", "/api/v1/fee-rules", self.admin_token, {"block_fee": 3000})
        self.assertEqual(body["data"]["block_fee"], 3000)
        self.assertEqual(body["data"]["free_min"], 5)
        self.assertEqual(body["data"]["updated_by"], "admin")

        resp, body = self.call("GET", "/api/v1/compartments", self.viewer_token, None)
        self.assertEqual(body["data"][0]["session"]["current_fee"], 6000)

    def test_fee_rules_bad_values(self):
        for change in [{}, {"block_min": 0}, {"free_min": -1}, {"block_fee": "2000"}]:
            resp, body = self.call("PATCH", "/api/v1/fee-rules", self.admin_token, change)
            self.assertEqual(body["error_code"], "INVALID_PAYLOAD", change)


class UserAndStatsTests(DashboardBase):
    def test_users_create_and_block(self):
        resp, body = self.call("POST", "/api/v1/users", self.admin_token,
                               {"card_uid": "C0FFEE01", "name": "Nguyễn Văn B"})
        data = body["data"]
        self.assertEqual(data["source"], "LOCAL")
        self.assertIsNone(data["external_id"])
        self.assertFalse(data["blocked"])

        resp, body = self.call("POST", "/api/v1/users", self.admin_token,
                               {"card_uid": "C0FFEE01", "name": "Trung"})
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")

        resp, body = self.call("PATCH", "/api/v1/users/%d" % data["id"], self.admin_token,
                               {"blocked": True})
        self.assertTrue(body["data"]["blocked"])

        resp, body = self.call("GET", "/api/v1/users?page_size=1&page=2", self.viewer_token, None)
        self.assertEqual(body["data"]["count"], 2)
        self.assertEqual(body["data"]["results"][0]["card_uid"], "C0FFEE01")

    def test_stats_overview(self):
        session = self.occupy(self.comp1, 95)
        # Tao luc nay de chac chan nam trong hom nay, ke ca khi chay luc gan nua dem
        session.created_at = timezone.now()
        session.state = "CLOSED"
        session.payment_status = "PAID"
        session.fee = 4000
        session.closed_at = timezone.now()
        session.save()
        resp, body = self.call("GET", "/api/v1/stats/overview", self.viewer_token, None)
        data = body["data"]
        self.assertEqual(data["sessions_today"], 1)
        self.assertEqual(data["revenue_today"], 4000)
        self.assertEqual(data["occupancy_rate"], 0.5)

    def test_stats_revenue(self):
        session = self.occupy(self.comp1, 95)
        session.state = "CLOSED"
        session.payment_status = "PAID"
        session.fee = 4000
        session.closed_at = timezone.now()
        session.save()
        today = timezone.localdate()
        start = today - timedelta(days=2)
        resp, body = self.call(
            "GET",
            "/api/v1/stats/revenue?from=%s&to=%s" % (start.isoformat(), today.isoformat()),
            self.viewer_token,
            None,
        )
        data = body["data"]
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0], {"date": start.isoformat(), "revenue": 0, "sessions": 0})
        self.assertEqual(data[2]["revenue"], 4000)

        resp, body = self.call("GET", "/api/v1/stats/revenue?from=2026-11-09", self.viewer_token, None)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")

    def test_devices_online(self):
        self.device.last_heartbeat_at = timezone.now() - timedelta(seconds=30)
        self.device.last_rssi = -58
        self.device.save()
        Device.objects.create(device_id="LOCKER02", token_hash="1" * 64)
        resp, body = self.call("GET", "/api/v1/devices", self.viewer_token, None)
        data = body["data"]
        self.assertTrue(data[0]["online"])
        self.assertEqual(data[0]["rssi"], -58)
        self.assertFalse(data[1]["online"])
        self.assertIsNone(data[1]["last_heartbeat_at"])
