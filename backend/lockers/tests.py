import hashlib
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth.models import Group
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from devices.models import Command, Device, RequestLog
from identity.models import CardUser
from lockers import state
from lockers.fee import compute_fee, duration_minutes
from lockers.models import Compartment, Event, FeeRule, Session
from payments.models import Payment

TOKEN = "0123456789abcdef0123456789abcdef"


class SessionConstraintTests(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.device = Device.objects.create(device_id="LOCKER01", token_hash="0" * 64)
        self.comp1 = Compartment.objects.create(
            device=self.device, number=1, status="FREE", status_changed_at=self.now
        )
        self.comp2 = Compartment.objects.create(
            device=self.device, number=2, status="FREE", status_changed_at=self.now
        )
        self.user1 = CardUser.objects.create(
            card_uid="A3F1C290", name="Nguoi 1", source="LOCAL", created_at=self.now
        )
        self.user2 = CardUser.objects.create(
            card_uid="B4E2D301", name="Nguoi 2", source="LOCAL", created_at=self.now
        )

    def make_session(self, user, comp, state):
        return Session.objects.create(
            user=user, compartment=comp, state=state, created_at=self.now
        )

    def test_two_occupied_same_user_fails(self):
        self.make_session(self.user1, self.comp1, "OCCUPIED")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_session(self.user1, self.comp2, "OCCUPIED")

    def test_closed_and_occupied_same_user_ok(self):
        self.make_session(self.user1, self.comp1, "CLOSED")
        self.make_session(self.user1, self.comp2, "OCCUPIED")
        self.assertEqual(Session.objects.filter(user=self.user1).count(), 2)

    def test_two_occupied_same_compartment_fails(self):
        self.make_session(self.user1, self.comp1, "OCCUPIED")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make_session(self.user2, self.comp1, "OCCUPIED")

    def test_closed_and_occupied_same_compartment_ok(self):
        self.make_session(self.user1, self.comp1, "CLOSED")
        self.make_session(self.user2, self.comp1, "OCCUPIED")
        self.assertEqual(Session.objects.filter(compartment=self.comp1).count(), 2)


class InitialDataTests(TestCase):
    def test_fee_rule_default(self):
        rule = FeeRule.objects.get(id=1)
        self.assertEqual(rule.free_min, 5)
        self.assertEqual(rule.block_min, 60)
        self.assertEqual(rule.block_fee, 2000)

    def test_groups_exist(self):
        self.assertTrue(Group.objects.filter(name="viewer").exists())
        self.assertTrue(Group.objects.filter(name="admin").exists())


# B4: fee.py va state.py


class FeeTests(TestCase):
    def setUp(self):
        self.rule = FeeRule(id=99, free_min=5, block_min=60, block_fee=2000)

    def test_duration_rounds_down(self):
        now = timezone.now()
        occupied_at = now - timedelta(minutes=95, seconds=59)
        self.assertEqual(duration_minutes(occupied_at, now), 95)

    def test_duration_negative_is_zero(self):
        now = timezone.now()
        self.assertEqual(duration_minutes(now + timedelta(seconds=5), now), 0)

    def test_fee_table(self):
        self.assertEqual(compute_fee(0, self.rule, "STUDENT"), 0)
        self.assertEqual(compute_fee(5, self.rule, "STUDENT"), 0)
        self.assertEqual(compute_fee(6, self.rule, "STUDENT"), 2000)
        self.assertEqual(compute_fee(65, self.rule, "PARKING"), 2000)
        self.assertEqual(compute_fee(66, self.rule, "STUDENT"), 4000)
        self.assertEqual(compute_fee(95, self.rule, "STUDENT"), 4000)

    def test_local_card_is_free(self):
        self.assertEqual(compute_fee(95, self.rule, "LOCAL"), 0)


class StateTestBase(TestCase):
    def setUp(self):
        self.now = timezone.now()
        self.long_ago = self.now - timedelta(hours=2)
        self.device = Device.objects.create(device_id="LOCKER01", token_hash="0" * 64)
        self.comp = Compartment.objects.create(
            device=self.device, number=1, status="FREE", status_changed_at=self.long_ago
        )
        self.comp2 = Compartment.objects.create(
            device=self.device, number=2, status="FREE", status_changed_at=self.long_ago
        )
        self.user = CardUser.objects.create(
            card_uid="A3F1C290",
            name="Sinh vien",
            source="STUDENT",
            external_id="B23DCCN924",
            created_at=self.long_ago,
        )
        self.rule = FeeRule.objects.get(id=1)

    def put(self, comp_status, session_state, unlock_ago_sec):
        # Dat ngan va phien vao trang thai cho truoc
        self.comp.status = comp_status
        self.comp.status_changed_at = self.now - timedelta(seconds=unlock_ago_sec)
        self.comp.last_unlock_at = self.now - timedelta(seconds=unlock_ago_sec)
        self.comp.door_closed = True
        self.comp.save()
        if session_state is None:
            return None
        session = Session.objects.create(
            user=self.user,
            compartment=self.comp,
            state=session_state,
            created_at=self.long_ago,
        )
        if session_state == "OCCUPIED" or session_state == "RELEASING":
            session.occupied_at = self.now - timedelta(minutes=95)
            session.save()
        session.compartment = self.comp
        return session

    def make_command(self, comp, created_ago_sec):
        return Command.objects.create(
            device=self.device,
            compartment=comp,
            type="OPEN",
            unlock_ms=800,
            reason="test",
            state="PENDING",
            created_at=self.now - timedelta(seconds=created_ago_sec),
        )

    def reload(self, session):
        self.comp.refresh_from_db()
        if session is not None:
            session.refresh_from_db()


class SessionTransitionTests(StateTestBase):
    # Quy chuan API 6.2

    def test_scan_creates_session(self):
        session = state.start_session(self.user, self.comp, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CREATED")
        self.assertEqual(session.payment_status, "NONE")
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(self.comp.last_unlock_at, self.now)
        self.assertEqual(self.comp.status_changed_at, self.now)

    def test_created_door_opened(self):
        session = self.put("OPEN", "CREATED", 5)
        state.on_door_opened(self.comp, session, self.now)
        self.reload(session)
        self.assertEqual(session.state, "OPEN")
        self.assertEqual(session.door_opened_at, self.now)
        self.assertEqual(self.comp.status, "OPEN")
        self.assertFalse(self.comp.door_closed)

    def test_created_wait_timeout_cancelled(self):
        session = self.put("OPEN", "CREATED", 31)
        state.run_time_checks(self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(session.closed_at, self.now)
        self.assertEqual(self.comp.status, "FREE")

    def test_created_within_wait_kept(self):
        session = self.put("OPEN", "CREATED", 29)
        state.run_time_checks(self.now)
        self.reload(session)
        self.assertEqual(session.state, "CREATED")
        self.assertEqual(self.comp.status, "OPEN")

    def test_created_boot_cancelled(self):
        session = self.put("OPEN", "CREATED", 5)
        state.on_boot(self.device, "1.0.3", self.now)
        self.reload(session)
        self.device.refresh_from_db()
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(self.comp.status, "FREE")
        self.assertEqual(self.device.firmware_version, "1.0.3")

    def test_open_closed_with_item(self):
        session = self.put("OPEN", "OPEN", 10)
        state.on_door_closed(self.comp, session, True, self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(session.occupied_at, self.now)
        self.assertEqual(self.comp.status, "OCCUPIED")
        self.assertTrue(self.comp.has_item)
        self.assertTrue(self.comp.door_closed)

    def test_open_closed_without_item(self):
        session = self.put("OPEN", "OPEN", 10)
        state.on_door_closed(self.comp, session, False, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(session.closed_at, self.now)
        self.assertEqual(self.comp.status, "FREE")

    def test_open_boot_cancelled(self):
        session = self.put("OPEN", "OPEN", 10)
        state.on_boot(self.device, "1.0.3", self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")

    def test_open_compartment_error_cancelled(self):
        session = self.put("OPEN", "OPEN", 10)
        state.on_lock_failed(self.comp, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(self.comp.status, "ERROR")

    def test_occupied_scan_releasing(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        session.door_opened_at = self.long_ago
        session.save()
        state.start_releasing(session, self.now)
        self.reload(session)
        self.assertEqual(session.state, "RELEASING")
        self.assertIsNone(session.door_opened_at)
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(self.comp.last_unlock_at, self.now)

    def test_occupied_manual_command_done(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        command = self.make_command(self.comp, 10)
        state.on_command_done(command, self.rule, self.now)
        self.reload(session)
        command.refresh_from_db()
        self.assertEqual(command.state, "DONE")
        self.assertEqual(command.acked_at, self.now)
        self.assertEqual(session.state, "RELEASING")
        self.assertEqual(session.duration_min, 95)
        self.assertEqual(session.fee, 4000)
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(self.comp.last_unlock_at, self.now)

    def test_releasing_closed_without_item(self):
        session = self.put("OPEN", "RELEASING", 10)
        state.on_door_closed(self.comp, session, False, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CLOSED")
        self.assertEqual(session.closed_at, self.now)
        self.assertEqual(self.comp.status, "FREE")

    def test_releasing_closed_with_item(self):
        session = self.put("OPEN", "RELEASING", 10)
        occupied_at = session.occupied_at
        state.on_door_closed(self.comp, session, True, self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(session.occupied_at, occupied_at)
        self.assertEqual(self.comp.status, "OCCUPIED")

    def test_releasing_wait_timeout(self):
        session = self.put("OPEN", "RELEASING", 31)
        state.run_time_checks(self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(self.comp.status, "OCCUPIED")

    def test_releasing_door_opened_not_timed_out(self):
        session = self.put("OPEN", "RELEASING", 31)
        session.door_opened_at = self.now - timedelta(seconds=20)
        session.save()
        state.run_time_checks(self.now)
        self.reload(session)
        self.assertEqual(session.state, "RELEASING")

    def test_releasing_boot_door_not_opened(self):
        session = self.put("OPEN", "RELEASING", 5)
        state.on_boot(self.device, "1.0.3", self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(self.comp.status, "OCCUPIED")

    def test_releasing_compartment_error_closed(self):
        session = self.put("OPEN", "RELEASING", 5)
        state.on_lock_failed(self.comp, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CLOSED")
        self.assertEqual(session.closed_at, self.now)
        self.assertEqual(self.comp.status, "ERROR")


class CompartmentTransitionTests(StateTestBase):
    # Quy chuan API 6.3

    def test_free_manual_command_done(self):
        command = self.make_command(self.comp, 10)
        state.on_command_done(command, self.rule, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(self.comp.last_unlock_at, self.now)

    def test_open_closed_with_item_no_session(self):
        self.put("OPEN", None, 10)
        state.on_door_closed(self.comp, None, True, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "ERROR")

    def test_open_closed_without_item_no_session(self):
        self.put("OPEN", None, 10)
        state.on_door_closed(self.comp, None, False, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "FREE")

    def test_open_over_10_minutes_error(self):
        session = self.put("OPEN", "OPEN", 601)
        session.door_opened_at = self.now - timedelta(seconds=590)
        session.save()
        state.run_time_checks(self.now)
        self.reload(session)
        self.assertEqual(self.comp.status, "ERROR")
        self.assertEqual(session.state, "CANCELLED")

    def test_open_under_10_minutes_kept(self):
        self.put("OPEN", None, 599)
        state.run_time_checks(self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "OPEN")

    def test_free_door_opened_without_command(self):
        state.on_door_opened(self.comp, None, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "ERROR")
        self.assertFalse(self.comp.door_closed)

    def test_occupied_door_opened_without_command(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        state.on_door_opened(self.comp, session, self.now)
        self.reload(session)
        self.assertEqual(self.comp.status, "ERROR")
        self.assertEqual(session.state, "OCCUPIED")

    def test_lock_failed_any_status(self):
        state.on_lock_failed(self.comp, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "ERROR")
        self.assertEqual(self.comp.status_changed_at, self.now)

    def test_reset_error_without_session(self):
        self.put("ERROR", None, 100)
        self.assertTrue(state.reset_compartment(self.comp, self.now))
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "FREE")

    def test_reset_error_with_running_session_refused(self):
        self.put("ERROR", "OCCUPIED", 100)
        self.assertFalse(state.reset_compartment(self.comp, self.now))
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "ERROR")

    def test_reset_not_error_refused(self):
        self.assertFalse(state.reset_compartment(self.comp, self.now))


class TimeCheckTests(StateTestBase):
    # Quy chuan API 6.4, cac moc khong nam o bang 6.2, 6.3

    def test_command_expires_after_5_minutes(self):
        old = self.make_command(self.comp, 301)
        fresh = self.make_command(self.comp2, 299)
        state.run_time_checks(self.now)
        old.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(old.state, "EXPIRED")
        self.assertEqual(fresh.state, "PENDING")

    def test_payment_expires(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        session.payment_status = "PENDING"
        session.save()
        payment = Payment.objects.create(
            session=session,
            pay_code="K7M2QX",
            source="STUDENT",
            amount=4000,
            state="PENDING",
            created_at=self.now - timedelta(seconds=121),
            expires_at=self.now - timedelta(seconds=1),
        )
        state.run_time_checks(self.now)
        payment.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(payment.state, "EXPIRED")
        self.assertEqual(session.payment_status, "NONE")

    def test_payment_not_yet_expired(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        payment = Payment.objects.create(
            session=session,
            pay_code="K7M2QX",
            source="STUDENT",
            amount=4000,
            state="PENDING",
            created_at=self.now,
            expires_at=self.now + timedelta(seconds=120),
        )
        state.run_time_checks(self.now)
        payment.refresh_from_db()
        self.assertEqual(payment.state, "PENDING")

    def test_request_log_cleanup(self):
        RequestLog.objects.create(
            device=self.device,
            request_id="LOCKER01-000001",
            endpoint="scan",
            response={},
            created_at=self.now - timedelta(seconds=601),
        )
        RequestLog.objects.create(
            device=self.device,
            request_id="LOCKER01-000002",
            endpoint="scan",
            response={},
            created_at=self.now - timedelta(seconds=599),
        )
        state.run_time_checks(self.now)
        ids = []
        for row in RequestLog.objects.all():
            ids.append(row.request_id)
        self.assertEqual(ids, ["LOCKER01-000002"])


class DecisionTests(StateTestBase):
    # Cac quyet dinh tam Q5, Q6, Q9, Q15, Q16

    def test_q5_error_compartment_command_done(self):
        session = self.put("ERROR", "OCCUPIED", 3600)
        command = self.make_command(self.comp, 10)
        state.on_command_done(command, self.rule, self.now)
        self.reload(session)
        self.assertEqual(session.state, "RELEASING")
        self.assertEqual(session.fee, 4000)
        self.assertEqual(self.comp.status, "ERROR")
        self.assertEqual(self.comp.last_unlock_at, self.now)

    def test_q5_error_releasing_closed_without_item(self):
        session = self.put("ERROR", "RELEASING", 10)
        state.on_door_closed(self.comp, session, False, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CLOSED")
        self.assertEqual(self.comp.status, "ERROR")

    def test_q5_error_releasing_closed_with_item(self):
        session = self.put("ERROR", "RELEASING", 10)
        state.on_door_closed(self.comp, session, True, self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(self.comp.status, "ERROR")

    def test_q6_free_door_opened_with_pending_command(self):
        self.make_command(self.comp, 10)
        state.on_door_opened(self.comp, None, self.now)
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "FREE")
        self.assertFalse(self.comp.door_closed)

    def test_q6_occupied_door_opened_with_pending_command(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        self.make_command(self.comp, 10)
        state.on_door_opened(self.comp, session, self.now)
        self.reload(session)
        self.assertEqual(self.comp.status, "OCCUPIED")
        self.assertEqual(session.state, "OCCUPIED")

    def test_q9_paid_session_kept_when_payment_expires(self):
        session = self.put("OCCUPIED", "OCCUPIED", 3600)
        session.payment_status = "PAID"
        session.save()
        Payment.objects.create(
            session=session,
            pay_code="K7M2QX",
            source="STUDENT",
            amount=4000,
            state="PENDING",
            created_at=self.now - timedelta(seconds=200),
            expires_at=self.now - timedelta(seconds=80),
        )
        state.run_time_checks(self.now)
        session.refresh_from_db()
        self.assertEqual(session.payment_status, "PAID")

    def test_q15_created_compartment_error_cancelled(self):
        session = self.put("OPEN", "CREATED", 5)
        state.on_lock_failed(self.comp, self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(self.comp.status, "ERROR")

    def test_q15_created_door_closed_like_open(self):
        session = self.put("OPEN", "CREATED", 5)
        state.on_door_closed(self.comp, session, True, self.now)
        self.reload(session)
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(session.occupied_at, self.now)
        self.assertEqual(self.comp.status, "OCCUPIED")

    def test_q16_boot_open_session_keeps_compartment_open(self):
        session = self.put("OPEN", "OPEN", 10)
        changed_at = self.comp.status_changed_at
        state.on_boot(self.device, "1.0.3", self.now)
        self.reload(session)
        self.assertEqual(session.state, "CANCELLED")
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(self.comp.status_changed_at, changed_at)

    def test_q16_boot_releasing_door_opened_kept(self):
        session = self.put("OPEN", "RELEASING", 10)
        session.door_opened_at = self.now - timedelta(seconds=5)
        session.save()
        state.on_boot(self.device, "1.0.3", self.now)
        self.reload(session)
        self.assertEqual(session.state, "RELEASING")
        self.assertEqual(self.comp.status, "OPEN")


# B5: /events va /events/batch


class EventApiBase(TestCase):
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
        self.user = CardUser.objects.create(
            card_uid="A3F1C290", name="Sinh vien", source="STUDENT",
            external_id="B23DCCN924", created_at=self.long_ago,
        )
        self.user2 = CardUser.objects.create(
            card_uid="B4E2D301", name="Nguoi 2", source="LOCAL", created_at=self.long_ago
        )

    def event(self, seq, event_type, session_id, compartment, has_item):
        return {
            "device_id": "LOCKER01",
            "request_id": "LOCKER01-%06d" % seq,
            "device_time": "2026-11-09T09:12:30+07:00",
            "event_type": event_type,
            "session_id": session_id,
            "compartment": compartment,
            "has_item": has_item,
            "firmware_version": "",
        }

    def post(self, path, body):
        return self.client.post(
            path,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION="Device " + TOKEN,
        )

    def send(self, body):
        resp = self.post("/api/v1/events", body)
        return resp, json.loads(resp.content)

    def send_batch(self, items):
        resp = self.post("/api/v1/events/batch", {"device_id": "LOCKER01", "events": items})
        return resp, json.loads(resp.content)


class EventsApiTests(EventApiBase):
    def test_deposit_flow(self):
        session = state.start_session(self.user, self.comp, self.now)

        resp, body = self.send(self.event(1, "DOOR_OPENED", session.id, 1, False))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            body["data"],
            {"session_state": "OPEN", "compartment_status": "OPEN", "unlock_ms": 0, "display": ""},
        )

        resp, body = self.send(self.event(2, "DOOR_CLOSED", session.id, 1, True))
        self.assertEqual(
            body["data"],
            {
                "session_state": "OCCUPIED",
                "compartment_status": "OCCUPIED",
                "unlock_ms": 0,
                "display": "Da khoa - Hen gap lai",
            },
        )
        session.refresh_from_db()
        self.assertEqual(session.state, "OCCUPIED")
        self.assertIsNotNone(session.occupied_at)
        self.assertEqual(Event.objects.filter(accepted=True).count(), 2)

    def test_same_request_id_same_response(self):
        session = state.start_session(self.user, self.comp, self.now)
        first = self.post("/api/v1/events", self.event(1, "DOOR_OPENED", session.id, 1, False))
        second = self.post("/api/v1/events", self.event(1, "DOOR_OPENED", session.id, 1, False))
        self.assertEqual(first.content, second.content)
        self.assertEqual(first.status_code, second.status_code)
        self.assertEqual(Event.objects.count(), 1)

    def test_q13_event_known_but_request_log_gone(self):
        session = state.start_session(self.user, self.comp, self.now)
        self.send(self.event(1, "DOOR_OPENED", session.id, 1, False))
        self.send(self.event(2, "DOOR_CLOSED", session.id, 1, True))
        RequestLog.objects.all().delete()

        resp, body = self.send(self.event(2, "DOOR_CLOSED", session.id, 1, True))
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["display"], "")
        self.assertEqual(body["data"]["session_state"], "OCCUPIED")
        self.assertEqual(Event.objects.count(), 2)

    def test_q3_session_id_zero_uses_running_session(self):
        session = state.start_session(self.user, self.comp, self.now)
        resp, body = self.send(self.event(1, "DOOR_OPENED", 0, 1, False))
        self.assertTrue(body["success"])
        session.refresh_from_db()
        self.assertEqual(session.state, "OPEN")
        self.assertEqual(Event.objects.get().session_id, session.id)

    def test_q4_cancelled_session_on_free_compartment(self):
        session = state.start_session(self.user, self.comp, self.now)
        session.state = "CANCELLED"
        session.save()
        self.comp.status = "FREE"
        self.comp.save()

        resp, body = self.send(self.event(1, "DOOR_OPENED", session.id, 1, False))
        self.assertEqual(body["error_code"], "SESSION_NOT_FOUND")
        self.comp.refresh_from_db()
        self.assertEqual(self.comp.status, "ERROR")
        event = Event.objects.get()
        self.assertFalse(event.accepted)
        self.assertEqual(event.error_code, "SESSION_NOT_FOUND")

    def test_q4_other_running_session_only_logged(self):
        old = state.start_session(self.user2, self.comp, self.now)
        old.state = "CANCELLED"
        old.save()
        session = state.start_session(self.user, self.comp, self.now)

        resp, body = self.send(self.event(1, "DOOR_CLOSED", old.id, 1, False))
        self.assertEqual(body["error_code"], "SESSION_NOT_FOUND")
        session.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(session.state, "CREATED")
        self.assertEqual(self.comp.status, "OPEN")
        self.assertEqual(Event.objects.get().accepted, False)

    def test_boot_event(self):
        item = self.event(1, "BOOT", 0, 0, False)
        item["firmware_version"] = "1.0.3"
        resp, body = self.send(item)
        self.assertEqual(
            body["data"],
            {"session_state": "", "compartment_status": "", "unlock_ms": 0, "display": ""},
        )
        self.device.refresh_from_db()
        self.assertEqual(self.device.firmware_version, "1.0.3")

    def test_item_in_only_logged(self):
        resp, body = self.send(self.event(1, "ITEM_IN", 0, 1, False))
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["compartment_status"], "FREE")
        self.assertEqual(Event.objects.get().event_type, "ITEM_IN")

    def test_invalid_event_type(self):
        resp, body = self.send(self.event(1, "DOOR_BROKEN", 0, 1, False))
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
        self.assertEqual(Event.objects.count(), 0)

    def test_invalid_compartment_is_recorded(self):
        resp, body = self.send(self.event(1, "DOOR_OPENED", 0, 3, False))
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
        event = Event.objects.get()
        self.assertFalse(event.accepted)
        self.assertEqual(event.compartment_number, 3)

    def test_wrong_types(self):
        item = self.event(1, "DOOR_CLOSED", 0, 1, False)
        item["has_item"] = 1
        self.assertEqual(self.send(item)[1]["error_code"], "INVALID_PAYLOAD")
        item = self.event(1, "DOOR_CLOSED", 0, 1, False)
        item["session_id"] = True
        self.assertEqual(self.send(item)[1]["error_code"], "INVALID_PAYLOAD")
        item = self.event(1, "DOOR_CLOSED", 0, 1, False)
        del item["firmware_version"]
        self.assertEqual(self.send(item)[1]["error_code"], "INVALID_PAYLOAD")
        item = self.event(1, "DOOR_CLOSED", 0, 1, False)
        item["device_time"] = "2026-11-09T09:12:30"
        self.assertEqual(self.send(item)[1]["error_code"], "INVALID_PAYLOAD")
        item = self.event(1, "DOOR_CLOSED", 0, 1, False)
        item["request_id"] = "LOCKER01-12"
        self.assertEqual(self.send(item)[1]["error_code"], "INVALID_PAYLOAD")

    def test_q12_device_id_mismatch(self):
        item = self.event(1, "DOOR_OPENED", 0, 1, False)
        item["device_id"] = "LOCKER02"
        resp, body = self.send(item)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(body["error_code"], "DEVICE_UNAUTHORIZED")

    def test_wrong_token(self):
        resp = self.client.post(
            "/api/v1/events",
            data=json.dumps(self.event(1, "DOOR_OPENED", 0, 1, False)),
            content_type="application/json",
            HTTP_AUTHORIZATION="Device " + "x" * 32,
        )
        self.assertEqual(json.loads(resp.content)["error_code"], "DEVICE_UNAUTHORIZED")

    def test_q23_wrong_method(self):
        resp = self.client.get("/api/v1/events", HTTP_AUTHORIZATION="Device " + TOKEN)
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(json.loads(resp.content)["error_code"], "INVALID_PAYLOAD")


class EventsBatchApiTests(EventApiBase):
    def test_reverse_order_processed_by_request_id(self):
        session = state.start_session(self.user, self.comp, self.now)
        items = [
            self.event(3, "DOOR_CLOSED", session.id, 1, True),
            self.event(2, "DOOR_OPENED", session.id, 1, False),
        ]
        resp, body = self.send_batch(items)
        results = body["data"]["results"]
        self.assertEqual(results[0], {"request_id": "LOCKER01-000003", "accepted": True, "error_code": ""})
        self.assertEqual(results[1], {"request_id": "LOCKER01-000002", "accepted": True, "error_code": ""})
        session.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(self.comp.status, "OCCUPIED")

    def test_send_twice(self):
        session = state.start_session(self.user, self.comp, self.now)
        items = [
            self.event(2, "DOOR_OPENED", session.id, 1, False),
            self.event(3, "DOOR_CLOSED", session.id, 1, True),
        ]
        self.send_batch(items)
        resp, body = self.send_batch(items)
        for result in body["data"]["results"]:
            self.assertTrue(result["accepted"])
        session.refresh_from_db()
        self.assertEqual(session.state, "OCCUPIED")
        self.assertEqual(Event.objects.count(), 2)

    def test_bad_element_does_not_block_others(self):
        session = state.start_session(self.user, self.comp, self.now)
        items = [
            self.event(2, "DOOR_OPENED", session.id, 1, False),
            self.event(3, "DOOR_OPENED", 0, 5, False),
            {"request_id": "LOCKER01-000004"},
            self.event(5, "DOOR_CLOSED", session.id, 1, True),
        ]
        resp, body = self.send_batch(items)
        results = body["data"]["results"]
        self.assertTrue(results[0]["accepted"])
        self.assertEqual(results[1]["error_code"], "INVALID_PAYLOAD")
        self.assertEqual(results[2], {"request_id": "LOCKER01-000004", "accepted": False, "error_code": "INVALID_PAYLOAD"})
        self.assertTrue(results[3]["accepted"])
        session.refresh_from_db()
        self.assertEqual(session.state, "OCCUPIED")

    def test_exception_in_element(self):
        boot = self.event(3, "BOOT", 0, 0, False)
        boot["firmware_version"] = "1.0.4"
        items = [self.event(2, "LOCK_FAILED", 0, 1, False), boot]
        with patch("lockers.state.on_lock_failed", side_effect=RuntimeError("loi")):
            resp, body = self.send_batch(items)
        results = body["data"]["results"]
        self.assertEqual(results[0]["error_code"], "SERVER_ERROR")
        self.assertFalse(results[0]["accepted"])
        self.assertTrue(results[1]["accepted"])
        self.assertEqual(Event.objects.count(), 1)
        self.device.refresh_from_db()
        self.assertEqual(self.device.firmware_version, "1.0.4")

    def test_empty_or_too_many(self):
        self.assertEqual(self.send_batch([])[1]["error_code"], "INVALID_PAYLOAD")
        items = []
        for seq in range(1, 22):
            items.append(self.event(seq, "ITEM_IN", 0, 1, False))
        self.assertEqual(self.send_batch(items)[1]["error_code"], "INVALID_PAYLOAD")

    def test_response_20_items_fits_buffer(self):
        long_id = "LOCKERABCDEFGH01"
        self.device.device_id = long_id
        self.device.save()
        items = []
        for seq in range(1, 21):
            item = self.event(seq, "DOOR_TIMEOUT", 999999, 1, False)
            item["device_id"] = long_id
            item["request_id"] = long_id + "-%06d" % seq
            items.append(item)
        resp = self.post("/api/v1/events/batch", {"device_id": long_id, "events": items})
        results = json.loads(resp.content)["data"]["results"]
        self.assertEqual(len(results), 20)
        self.assertEqual(results[0]["error_code"], "SESSION_NOT_FOUND")
        self.assertLessEqual(len(resp.content), 2048)


# B6: /scan khong thu phi


class ScanApiTests(EventApiBase):
    def scan(self, card_uid, seq):
        body = {
            "device_id": "LOCKER01",
            "card_uid": card_uid,
            "request_id": "LOCKER01-%06d" % seq,
            "device_time": "2026-11-09T09:12:30+07:00",
        }
        resp = self.post("/api/v1/scan", body)
        return resp, json.loads(resp.content)

    def occupy(self, user, comp, minutes, unlock_ago_sec):
        comp.status = "OCCUPIED"
        comp.has_item = True
        comp.last_unlock_at = timezone.now() - timedelta(seconds=unlock_ago_sec)
        comp.save()
        return Session.objects.create(
            user=user,
            compartment=comp,
            state="OCCUPIED",
            created_at=self.long_ago,
            occupied_at=timezone.now() - timedelta(minutes=minutes, seconds=10),
        )

    def test_deposit_smallest_compartment(self):
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(resp.status_code, 200)
        session = Session.objects.get()
        self.assertEqual(
            body["data"],
            {
                "action": "DEPOSIT",
                "session_id": session.id,
                "compartment": 1,
                "unlock_ms": 800,
                "timeout_sec": 30,
                "display": "Ngan 1 - Moi bo do vao",
                "duration_min": 0,
                "fee": 0,
                "qr": "",
                "pay_timeout_sec": 0,
            },
        )
        self.comp.refresh_from_db()
        self.assertEqual(session.state, "CREATED")
        self.assertEqual(self.comp.status, "OPEN")
        self.assertIsNotNone(self.comp.last_unlock_at)

    def test_existing_user_no_external_call(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            self.scan("A3F1C290", 1)
        self.assertEqual(get.call_count, 0)
        self.assertEqual(post.call_count, 0)

    def test_unknown_card_both_sources_fail(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            get.side_effect = requests.Timeout()
            post.return_value = MagicMock(status_code=404)
            resp, body = self.scan("C0FFEE01", 1)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(body["error_code"], "CARD_NOT_FOUND")
        self.assertFalse(CardUser.objects.filter(card_uid="C0FFEE01").exists())

    def test_new_card_from_source1(self):
        with patch("identity.adapters.requests.get") as get:
            get.return_value = MagicMock(status_code=200)
            get.return_value.json.return_value = {
                "student_id": "B23DCCN999", "name": "Tran Van A", "status": "active",
            }
            resp, body = self.scan("C0FFEE01", 1)
        self.assertEqual(body["data"]["action"], "DEPOSIT")
        user = CardUser.objects.get(card_uid="C0FFEE01")
        self.assertEqual(user.source, "STUDENT")
        self.assertEqual(user.external_id, "B23DCCN999")
        self.assertFalse(user.blocked)

    def test_inactive_card_blocked(self):
        with patch("identity.adapters.requests.get") as get:
            get.return_value = MagicMock(status_code=200)
            get.return_value.json.return_value = {
                "student_id": "B23DCCN999", "name": "A", "status": "inactive",
            }
            resp, body = self.scan("C0FFEE01", 1)
        self.assertEqual(body["error_code"], "CARD_BLOCKED")
        self.assertTrue(CardUser.objects.get(card_uid="C0FFEE01").blocked)
        self.assertEqual(Session.objects.count(), 0)

    def test_no_free_compartment(self):
        self.occupy(self.user2, self.comp, 10, 3600)
        self.comp2.status = "ERROR"
        self.comp2.save()
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["error_code"], "NO_FREE_COMPARTMENT")

    def test_q1_free_but_not_rested(self):
        self.occupy(self.user2, self.comp, 10, 3600)
        self.comp2.last_unlock_at = timezone.now() - timedelta(seconds=10)
        self.comp2.save()
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(body["error_code"], "TOO_SOON")

    def test_skip_not_rested_compartment(self):
        self.comp.last_unlock_at = timezone.now() - timedelta(seconds=10)
        self.comp.save()
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["data"]["compartment"], 2)

    def test_rescan_while_created(self):
        self.scan("A3F1C290", 1)
        resp, body = self.scan("A3F1C290", 2)
        self.assertEqual(body["error_code"], "SESSION_CONFLICT")
        self.assertEqual(Session.objects.count(), 1)

    def test_pickup_too_soon(self):
        self.occupy(self.user, self.comp, 0, 10)
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["error_code"], "TOO_SOON")

    def test_pickup_compartment_error(self):
        self.occupy(self.user, self.comp, 10, 3600)
        self.comp.status = "ERROR"
        self.comp.save()
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["error_code"], "COMPARTMENT_ERROR")

    def test_same_request_id(self):
        first = self.scan("A3F1C290", 1)
        second = self.scan("A3F1C290", 1)
        self.assertEqual(first[0].content, second[0].content)
        self.assertEqual(Session.objects.count(), 1)

    def test_same_request_id_error_replayed(self):
        with patch("identity.adapters.requests.get") as get, patch(
            "identity.adapters.requests.post"
        ) as post:
            get.return_value = MagicMock(status_code=404)
            post.return_value = MagicMock(status_code=404)
            first = self.scan("C0FFEE01", 1)
            second = self.scan("C0FFEE01", 1)
        self.assertEqual(get.call_count, 1)
        self.assertEqual(first[0].content, second[0].content)

    def test_local_card_95_minutes_free(self):
        session = self.occupy(self.user2, self.comp, 95, 3600)
        resp, body = self.scan("B4E2D301", 1)
        data = body["data"]
        self.assertEqual(data["action"], "PICKUP")
        self.assertEqual(data["fee"], 0)
        self.assertEqual(data["duration_min"], 95)
        self.assertEqual(data["display"], "Ngan 1 - Moi lay do")
        self.assertEqual(data["unlock_ms"], 800)
        session.refresh_from_db()
        self.comp.refresh_from_db()
        self.assertEqual(session.state, "RELEASING")
        self.assertEqual(session.fee, 0)
        self.assertEqual(self.comp.status, "OPEN")

    def test_free_minutes_pickup(self):
        self.occupy(self.user, self.comp, 3, 3600)
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["data"]["action"], "PICKUP")
        self.assertEqual(body["data"]["duration_min"], 3)
        self.assertEqual(body["data"]["fee"], 0)

    def test_paid_session_keeps_fee(self):
        session = self.occupy(self.user, self.comp, 200, 3600)
        session.payment_status = "PAID"
        session.duration_min = 95
        session.fee = 4000
        session.save()
        resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["data"]["action"], "PICKUP")
        self.assertEqual(body["data"]["fee"], 4000)
        self.assertEqual(body["data"]["duration_min"], 95)

    def test_fee_needed_external_down(self):
        session = self.occupy(self.user, self.comp, 95, 3600)
        with patch("payments.charges.requests.post") as post:
            post.side_effect = requests.ConnectionError()
            resp, body = self.scan("A3F1C290", 1)
        self.assertEqual(body["error_code"], "PAYMENT_UNAVAILABLE")
        session.refresh_from_db()
        self.assertEqual(session.state, "OCCUPIED")

    def test_bad_card_uid(self):
        resp, body = self.scan("a3f1c290", 1)
        self.assertEqual(body["error_code"], "INVALID_PAYLOAD")
