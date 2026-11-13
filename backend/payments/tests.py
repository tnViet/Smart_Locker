import hashlib
import json
import re
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase, override_settings
from django.utils import timezone

from devices.models import Device
from identity.models import CardUser
from lockers.models import Compartment, Session
from payments import charges
from payments.models import Payment

TOKEN = "0123456789abcdef0123456789abcdef"

TEST_SETTINGS = {
    "SOURCE1_URL": "http://source1:9001",
    "SOURCE2_URL": "http://source2:9002",
    "SOURCE1_PAY_URL": "HTTP://192.168.1.10:9001",
    "SOURCE2_PAY_URL": "HTTP://192.168.1.10:9002",
    "PAY_HMAC_SECRET": "demo-pay-456",
}


def charge_ok():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"received": True, "duplicate": False}
    return resp


@override_settings(**TEST_SETTINGS)
class ChargeTests(TestCase):
    def test_sign_create_charge_example(self):
        self.assertEqual(
            charges.sign("demo-pay-456", "K7M2QX|B23DCCN924|4000|128|1794190500"),
            "b799a43b68a13af64d6e7e7bbef2b5747848d17a36c21444b18e1f729ec33346",
        )

    def test_sign_callback_example(self):
        self.assertEqual(
            charges.sign("demo-pay-456", "K7M2QX|4000|1794190570"),
            "2656f7718d84c5408b6294b025790e59ceeb01ceebc1062bdefd3570668be9b2",
        )

    def test_create_charge_body(self):
        now = datetime.fromtimestamp(1794190500, tz=dt_timezone.utc)
        with patch("payments.charges.requests.post") as post:
            post.return_value = charge_ok()
            result = charges.create_charge("STUDENT", "K7M2QX", "B23DCCN924", 4000, 128, now)
        self.assertTrue(result)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://source1:9001/charges")
        self.assertEqual(kwargs["timeout"], 1)
        self.assertEqual(
            kwargs["json"],
            {
                "pay_code": "K7M2QX",
                "external_id": "B23DCCN924",
                "amount": 4000,
                "session_id": 128,
                "expires_in": 120,
                "ts": 1794190500,
                "signature": "b799a43b68a13af64d6e7e7bbef2b5747848d17a36c21444b18e1f729ec33346",
            },
        )

    def test_create_charge_parking_uses_source2(self):
        with patch("payments.charges.requests.post") as post:
            post.return_value = charge_ok()
            charges.create_charge("PARKING", "K7M2QX", "PK-0099", 4000, 1, timezone.now())
        self.assertEqual(post.call_args[0][0], "http://source2:9002/charges")

    def test_create_charge_failures(self):
        now = timezone.now()
        with patch("payments.charges.requests.post") as post:
            post.side_effect = requests.Timeout()
            self.assertFalse(charges.create_charge("STUDENT", "A", "B", 1, 1, now))
            post.side_effect = None
            post.return_value = MagicMock(status_code=500)
            self.assertFalse(charges.create_charge("STUDENT", "A", "B", 1, 1, now))
            resp = MagicMock(status_code=200)
            resp.json.return_value = {"received": False}
            post.return_value = resp
            self.assertFalse(charges.create_charge("STUDENT", "A", "B", 1, 1, now))
            resp = MagicMock(status_code=200)
            resp.json.side_effect = ValueError("hong")
            post.return_value = resp
            self.assertFalse(charges.create_charge("STUDENT", "A", "B", 1, 1, now))

    def test_new_pay_code_format_and_unique(self):
        code = charges.new_pay_code()
        self.assertIsNotNone(re.fullmatch(r"[A-Z0-9]{6}", code))

    def test_new_pay_code_retries_on_collision(self):
        device = Device.objects.create(device_id="LOCKER01", token_hash="0" * 64)
        comp = Compartment.objects.create(
            device=device, number=1, status="FREE", status_changed_at=timezone.now()
        )
        user = CardUser.objects.create(
            card_uid="A3F1C290", name="A", source="LOCAL", created_at=timezone.now()
        )
        session = Session.objects.create(
            user=user, compartment=comp, state="CLOSED", created_at=timezone.now()
        )
        Payment.objects.create(
            session=session, pay_code="AAAAAA", source="STUDENT", amount=1,
            state="EXPIRED", created_at=timezone.now(), expires_at=timezone.now(),
        )
        values = ["A", "A", "A", "A", "A", "A", "B", "B", "B", "B", "B", "B"]
        with patch("payments.charges.secrets.choice", side_effect=values):
            self.assertEqual(charges.new_pay_code(), "BBBBBB")


@override_settings(**TEST_SETTINGS)
class PaymentFlowTests(TestCase):
    def setUp(self):
        self.long_ago = timezone.now() - timedelta(hours=3)
        self.device = Device.objects.create(
            device_id="LOCKER01",
            token_hash=hashlib.sha256(TOKEN.encode("ascii")).hexdigest(),
        )
        self.comp = Compartment.objects.create(
            device=self.device, number=2, status="OCCUPIED", has_item=True,
            status_changed_at=self.long_ago, last_unlock_at=self.long_ago,
        )
        Compartment.objects.create(
            device=self.device, number=1, status="FREE", status_changed_at=self.long_ago
        )
        self.user = CardUser.objects.create(
            card_uid="A3F1C290", name="Sinh vien", source="STUDENT",
            external_id="B23DCCN924", created_at=self.long_ago,
        )
        self.session = Session.objects.create(
            user=self.user, compartment=self.comp, state="OCCUPIED",
            created_at=self.long_ago,
            occupied_at=timezone.now() - timedelta(minutes=95, seconds=10),
        )
        self.seq = 0

    def next_request_id(self):
        self.seq = self.seq + 1
        return "LOCKER01-%06d" % self.seq

    def post(self, path, body, with_token):
        headers = {}
        if with_token:
            headers["HTTP_AUTHORIZATION"] = "Device " + TOKEN
        resp = self.client.post(
            path, data=json.dumps(body), content_type="application/json", **headers
        )
        return resp, json.loads(resp.content)

    def scan(self):
        return self.post("/api/v1/scan", {
            "device_id": "LOCKER01",
            "card_uid": "A3F1C290",
            "request_id": self.next_request_id(),
            "device_time": "2026-11-09T09:12:30+07:00",
        }, True)

    def check(self, session_id):
        return self.post("/api/v1/payment/check", {
            "device_id": "LOCKER01",
            "request_id": self.next_request_id(),
            "device_time": "2026-11-09T09:16:12+07:00",
            "session_id": session_id,
        }, True)

    def callback(self, pay_code, amount):
        ts = int(timezone.now().timestamp())
        signature = charges.sign("demo-pay-456", "%s|%d|%d" % (pay_code, amount, ts))
        return self.post("/api/v1/payments/callback", {
            "pay_code": pay_code, "amount": amount, "ts": ts, "signature": signature,
        }, False)

    def event(self, event_type, has_item):
        return self.post("/api/v1/events", {
            "device_id": "LOCKER01",
            "request_id": self.next_request_id(),
            "device_time": "2026-11-09T09:20:00+07:00",
            "event_type": event_type,
            "session_id": self.session.id,
            "compartment": 2,
            "has_item": has_item,
            "firmware_version": "",
        }, True)

    def scan_with_charge(self):
        with patch("payments.charges.requests.post") as post:
            post.return_value = charge_ok()
            resp, body = self.scan()
        return post, body

    def test_full_flow(self):
        post, body = self.scan_with_charge()
        data = body["data"]
        self.assertEqual(data["action"], "PAYMENT")
        self.assertEqual(data["fee"], 4000)
        self.assertEqual(data["duration_min"], 95)
        self.assertEqual(data["unlock_ms"], 0)
        self.assertEqual(data["timeout_sec"], 0)
        self.assertEqual(data["display"], "")
        self.assertEqual(data["pay_timeout_sec"], 120)
        self.assertEqual(data["compartment"], 2)
        self.assertTrue(data["qr"].startswith("HTTP://192.168.1.10:9001/P/"))
        self.assertLessEqual(len(data["qr"]), 47)
        self.assertEqual(post.call_count, 1)

        payment = Payment.objects.get()
        self.assertEqual(payment.state, "PENDING")
        self.assertEqual(payment.amount, 4000)
        self.assertEqual(payment.source, "STUDENT")
        self.session.refresh_from_db()
        self.assertEqual(self.session.payment_status, "PENDING")
        self.assertEqual(self.session.fee, 4000)

        resp, body = self.check(self.session.id)
        self.assertEqual(body["data"], {
            "paid": False, "compartment": 2, "unlock_ms": 0, "timeout_sec": 0, "display": "",
        })

        resp, body = self.callback(payment.pay_code, 4000)
        self.assertEqual(body["data"], {"session_id": self.session.id, "duplicate": False})
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, "OCCUPIED")
        self.assertEqual(self.session.payment_status, "PAID")

        resp, body = self.check(self.session.id)
        self.assertEqual(body["data"], {
            "paid": True, "compartment": 2, "unlock_ms": 800, "timeout_sec": 30,
            "display": "Da thanh toan - Moi lay do",
        })
        self.session.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(self.session.state, "RELEASING")
        self.assertEqual(self.comp.status, "OPEN")

    def test_rescan_reuses_charge(self):
        post, first = self.scan_with_charge()
        post2, second = self.scan_with_charge()
        self.assertEqual(post2.call_count, 0)
        self.assertEqual(first["data"]["qr"], second["data"]["qr"])
        self.assertEqual(second["data"]["fee"], 4000)
        self.assertEqual(second["data"]["duration_min"], 95)
        self.assertGreaterEqual(second["data"]["pay_timeout_sec"], 1)
        self.assertLessEqual(second["data"]["pay_timeout_sec"], 120)
        self.assertEqual(Payment.objects.count(), 1)

    def test_expired_charge(self):
        post, first = self.scan_with_charge()
        payment = Payment.objects.get()
        payment.created_at = timezone.now() - timedelta(seconds=130)
        payment.expires_at = timezone.now() - timedelta(seconds=10)
        payment.save()

        resp, body = self.callback(payment.pay_code, 4000)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(body["error_code"], "PAYMENT_NOT_FOUND")

        post, second = self.scan_with_charge()
        self.assertEqual(post.call_count, 1)
        self.assertNotEqual(first["data"]["qr"], second["data"]["qr"])
        payment.refresh_from_db()
        self.assertEqual(payment.state, "EXPIRED")
        self.assertEqual(Payment.objects.filter(state="PENDING").count(), 1)

        # Callback cua khoan thu da EXPIRED
        resp, body = self.callback(payment.pay_code, 4000)
        self.assertEqual(body["error_code"], "PAYMENT_NOT_FOUND")

    def test_external_timeout(self):
        with patch("payments.charges.requests.post") as post:
            post.side_effect = requests.Timeout()
            resp, body = self.scan()
        self.assertEqual(resp.status_code, 503)
        self.assertEqual(body["error_code"], "PAYMENT_UNAVAILABLE")
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, "OCCUPIED")
        self.assertEqual(self.session.payment_status, "NONE")
        self.assertEqual(Payment.objects.count(), 0)

    def test_callback_twice(self):
        self.scan_with_charge()
        payment = Payment.objects.get()
        self.callback(payment.pay_code, 4000)
        resp, body = self.callback(payment.pay_code, 4000)
        self.assertEqual(body["data"], {"session_id": self.session.id, "duplicate": True})

    def test_paid_reopen_close_rescan_pickup(self):
        self.scan_with_charge()
        payment = Payment.objects.get()
        self.callback(payment.pay_code, 4000)
        self.check(self.session.id)
        self.event("DOOR_OPENED", True)
        resp, body = self.event("DOOR_CLOSED", True)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, "OCCUPIED")

        # Cho qua 60 giay nghi khoa
        self.comp.refresh_from_db()
        self.comp.last_unlock_at = timezone.now() - timedelta(seconds=61)
        self.comp.save()

        post, body = self.scan_with_charge()
        self.assertEqual(post.call_count, 0)
        self.assertEqual(body["data"]["action"], "PICKUP")
        self.assertEqual(body["data"]["fee"], 4000)
        self.assertEqual(Payment.objects.count(), 1)

    def test_q9_admin_paid_old_charge_expires(self):
        self.scan_with_charge()
        payment = Payment.objects.get()
        self.session.refresh_from_db()
        self.session.payment_status = "PAID"
        self.session.save()
        payment.expires_at = timezone.now() - timedelta(seconds=1)
        payment.save()

        post, body = self.scan_with_charge()
        payment.refresh_from_db()
        self.session.refresh_from_db()
        self.assertEqual(payment.state, "EXPIRED")
        self.assertEqual(self.session.payment_status, "PAID")
        self.assertEqual(body["data"]["action"], "PICKUP")
        self.assertEqual(post.call_count, 0)

    def test_check_releasing_door_not_opened_resends_unlock(self):
        self.session.payment_status = "PAID"
        self.session.save()
        self.check(self.session.id)
        self.comp.refresh_from_db()
        unlock_at = self.comp.last_unlock_at
        resp, body = self.check(self.session.id)
        self.assertTrue(body["data"]["paid"])
        self.assertEqual(body["data"]["unlock_ms"], 800)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.last_unlock_at, unlock_at)

    def test_q18_releasing_door_opened(self):
        self.session.payment_status = "PAID"
        self.session.save()
        self.check(self.session.id)
        self.event("DOOR_OPENED", True)
        resp, body = self.check(self.session.id)
        self.assertEqual(body["data"], {
            "paid": True, "compartment": 2, "unlock_ms": 0, "timeout_sec": 0, "display": "",
        })

    def test_q18_paid_compartment_error(self):
        self.session.payment_status = "PAID"
        self.session.save()
        self.comp.status = "ERROR"
        self.comp.save()
        resp, body = self.check(self.session.id)
        self.assertEqual(body["error_code"], "COMPARTMENT_ERROR")

    def test_check_session_not_found(self):
        resp, body = self.check(999999)
        self.assertEqual(body["error_code"], "SESSION_NOT_FOUND")
        self.session.state = "CLOSED"
        self.session.save()
        resp, body = self.check(self.session.id)
        self.assertEqual(body["error_code"], "SESSION_NOT_FOUND")

    def test_callback_bad_signature_and_ts(self):
        self.scan_with_charge()
        payment = Payment.objects.get()
        ts = int(timezone.now().timestamp())
        resp, body = self.post("/api/v1/payments/callback", {
            "pay_code": payment.pay_code, "amount": 4000, "ts": ts, "signature": "0" * 64,
        }, False)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(body["error_code"], "INVALID_SIGNATURE")

        old_ts = ts - 301
        signature = charges.sign("demo-pay-456", "%s|%d|%d" % (payment.pay_code, 4000, old_ts))
        resp, body = self.post("/api/v1/payments/callback", {
            "pay_code": payment.pay_code, "amount": 4000, "ts": old_ts, "signature": signature,
        }, False)
        self.assertEqual(body["error_code"], "INVALID_SIGNATURE")

    def test_callback_wrong_amount_and_unknown_code(self):
        self.scan_with_charge()
        payment = Payment.objects.get()
        resp, body = self.callback(payment.pay_code, 2000)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
        resp, body = self.callback("ZZZZZZ", 4000)
        self.assertEqual(body["error_code"], "PAYMENT_NOT_FOUND")

    def test_callback_missing_field(self):
        resp, body = self.post("/api/v1/payments/callback", {"pay_code": "K7M2QX"}, False)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
