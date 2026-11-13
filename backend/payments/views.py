import hmac
import json
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.common import fail, find_logged, get_device, ok, read_body
from devices.models import RequestLog
from lockers import state
from lockers.models import Compartment, Session
from payments.charges import sign
from payments.models import Payment

UINT32_MAX = 4294967295
DISPLAY_PAID = "Da thanh toan - Moi lay do"


def payment_check(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    device = get_device(request)
    if device is None:
        return fail("DEVICE_UNAUTHORIZED")
    body = read_body(request, 256)
    if body is None:
        return fail("INVALID_PAYLOAD")
    for name, max_len in [
        ("device_id", 16),
        ("request_id", 23),
        ("device_time", 25),
    ]:
        value = body.get(name)
        if type(value) is not str or len(value) > max_len:
            return fail("INVALID_PAYLOAD")
    session_id = body.get("session_id")
    if type(session_id) is not int or session_id < 0 or session_id > UINT32_MAX:
        return fail("INVALID_PAYLOAD")
    # Q12
    if body["device_id"] != device.device_id:
        return fail("DEVICE_UNAUTHORIZED")
    if re.fullmatch(re.escape(device.device_id) + r"-[0-9]{6}", body["request_id"]) is None:
        return fail("INVALID_PAYLOAD")
    try:
        device_time = datetime.fromisoformat(body["device_time"])
    except ValueError:
        return fail("INVALID_PAYLOAD")
    if device_time.tzinfo is None:
        return fail("INVALID_PAYLOAD")

    now = timezone.now()
    with transaction.atomic():
        state.run_time_checks(now)

    with transaction.atomic():
        # Q20
        comps_by_id = {}
        for comp in Compartment.objects.select_for_update().filter(device=device):
            comps_by_id[comp.id] = comp

        logged = find_logged(device, body["request_id"])
        if logged is not None:
            if logged["success"]:
                return ok(logged["data"])
            return fail(logged["error_code"])

        not_paid = {
            "paid": False,
            "compartment": 0,
            "unlock_ms": 0,
            "timeout_sec": 0,
            "display": "",
        }
        session = Session.objects.filter(
            id=session_id,
            compartment__device=device,
            state__in=["OCCUPIED", "RELEASING"],
        ).first()
        if session is None:
            response = fail("SESSION_NOT_FOUND")
        else:
            comp = comps_by_id[session.compartment_id]
            session.compartment = comp
            not_paid["compartment"] = comp.number
            opened = {
                "paid": True,
                "compartment": comp.number,
                "unlock_ms": settings.UNLOCK_MS,
                "timeout_sec": settings.DOOR_TIMEOUT_SEC,
                "display": DISPLAY_PAID,
            }
            rest_limit = now - timedelta(seconds=settings.LOCK_REST_SEC)

            if session.state == "RELEASING":
                if session.door_opened_at is None:
                    # Phan hoi truoc co the bi mat: tra lai lenh mo, khong ghi lai last_unlock_at
                    response = ok(opened)
                else:
                    # Q18: cua da mo
                    response = ok(
                        {
                            "paid": True,
                            "compartment": comp.number,
                            "unlock_ms": 0,
                            "timeout_sec": 0,
                            "display": "",
                        }
                    )
            elif session.payment_status != "PAID":
                response = ok(not_paid)
            elif comp.status == "ERROR":
                # Q18
                response = fail("COMPARTMENT_ERROR")
            elif comp.last_unlock_at is not None and comp.last_unlock_at > rest_limit:
                # Ngan chua nghi du 60 giay: chua mo, firmware hoi lai sau 2 giay
                response = ok(not_paid)
            else:
                state.start_releasing(session, now)
                response = ok(opened)

        RequestLog.objects.create(
            device=device,
            request_id=body["request_id"],
            endpoint="payment/check",
            response=json.loads(response.content),
            created_at=now,
        )
    return response


def payments_callback(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    body = read_body(request, 512)
    if body is None:
        return fail("INVALID_PAYLOAD")

    # 1. Thieu truong, sai kieu
    pay_code = body.get("pay_code")
    amount = body.get("amount")
    ts = body.get("ts")
    signature = body.get("signature")
    if type(pay_code) is not str or len(pay_code) != 6:
        return fail("INVALID_PAYLOAD")
    if type(amount) is not int or amount < 0 or amount > UINT32_MAX:
        return fail("INVALID_PAYLOAD")
    if type(ts) is not int or ts < 0:
        return fail("INVALID_PAYLOAD")
    if type(signature) is not str or len(signature) != 64:
        return fail("INVALID_PAYLOAD")

    # 2. ts lech qua 300 giay hoac chu ky sai
    now = timezone.now()
    if abs(int(now.timestamp()) - ts) > 300:
        return fail("INVALID_SIGNATURE")
    expected = sign(settings.PAY_HMAC_SECRET, "%s|%d|%d" % (pay_code, amount, ts))
    if not hmac.compare_digest(expected, signature):
        return fail("INVALID_SIGNATURE")

    with transaction.atomic():
        payment = Payment.objects.select_for_update().filter(pay_code=pay_code).first()

        # 3. Khong co, da EXPIRED, hoac PENDING ma da qua han (Q19)
        if payment is None or payment.state == "EXPIRED":
            return fail("PAYMENT_NOT_FOUND")
        if payment.state == "PENDING" and payment.expires_at <= now:
            return fail("PAYMENT_NOT_FOUND")

        # 4. So tien khac
        if amount != payment.amount:
            return fail("INVALID_PAYLOAD")

        # 5. Da ghi nhan roi
        if payment.state == "PAID":
            return ok({"session_id": payment.session_id, "duplicate": True})

        # 6. Ghi nhan, khong doi state cua phien
        payment.state = "PAID"
        payment.paid_at = now
        payment.save()
        session = Session.objects.select_for_update().get(id=payment.session_id)
        session.payment_status = "PAID"
        session.save()
    return ok({"session_id": payment.session_id, "duplicate": False})
