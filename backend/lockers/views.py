import json
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.common import fail, find_logged, get_device, ok, read_body
from devices.models import RequestLog
from identity import adapters
from identity.models import CardUser
from lockers import state
from lockers.fee import compute_fee, duration_minutes
from lockers.models import RUNNING_STATES, Compartment, Event, FeeRule, Session
from payments.charges import create_charge, new_pay_code
from payments.models import Payment

# Quy chuan API 2.2
EVENT_TYPES = [
    "DOOR_OPENED",
    "DOOR_CLOSED",
    "ITEM_IN",
    "ITEM_OUT",
    "DOOR_TIMEOUT",
    "LOCK_FAILED",
    "BOOT",
    "CARD_READ_FAIL",
]
# Loai su kien co cot compartment o bang API 2.2
COMPARTMENT_EVENTS = [
    "DOOR_OPENED",
    "DOOR_CLOSED",
    "ITEM_IN",
    "ITEM_OUT",
    "DOOR_TIMEOUT",
    "LOCK_FAILED",
]
# Loai su kien co cot session_id o bang API 2.2
SESSION_EVENTS = ["DOOR_OPENED", "DOOR_CLOSED", "DOOR_TIMEOUT", "LOCK_FAILED"]

UINT32_MAX = 4294967295
DISPLAY_LOCKED = "Da khoa - Hen gap lai"


def check_event(device, item):
    # Kiem tra mot goi su kien theo Dinh dang goi tin muc 2.2.
    # Tra "" khi hop le, nguoc lai tra error_code.
    if type(item) is not dict:
        return "INVALID_PAYLOAD"

    for name, max_len in [
        ("device_id", 16),
        ("request_id", 23),
        ("device_time", 25),
        ("event_type", 16),
        ("firmware_version", 12),
    ]:
        value = item.get(name)
        if type(value) is not str or len(value) > max_len:
            return "INVALID_PAYLOAD"

    session_id = item.get("session_id")
    if type(session_id) is not int or session_id < 0 or session_id > UINT32_MAX:
        return "INVALID_PAYLOAD"
    compartment = item.get("compartment")
    if type(compartment) is not int or compartment < 0 or compartment > 255:
        return "INVALID_PAYLOAD"
    if type(item.get("has_item")) is not bool:
        return "INVALID_PAYLOAD"

    # Q12
    if item["device_id"] != device.device_id:
        return "DEVICE_UNAUTHORIZED"

    if re.fullmatch(re.escape(device.device_id) + r"-[0-9]{6}", item["request_id"]) is None:
        return "INVALID_PAYLOAD"

    try:
        device_time = datetime.fromisoformat(item["device_time"])
    except ValueError:
        return "INVALID_PAYLOAD"
    if device_time.tzinfo is None:
        return "INVALID_PAYLOAD"

    if item["event_type"] not in EVENT_TYPES:
        return "INVALID_PAYLOAD"
    return ""


def handle_event(device, comps, item, now):
    # Xu ly mot su kien da qua check_event. comps la dict so ngan sang Compartment
    # da khoa. Tra (error_code, data), error_code rong khi thanh cong.
    request_id = item["request_id"]
    event_type = item["event_type"]
    number = item["compartment"]

    # Q13: su kien da nhan tu truoc
    old = Event.objects.filter(device=device, request_id=request_id).first()
    if old is not None:
        session_state = ""
        if old.session_id is not None:
            session_state = Session.objects.get(id=old.session_id).state
        compartment_status = ""
        if old.compartment_number in comps:
            compartment_status = comps[old.compartment_number].status
        data = {
            "session_state": session_state,
            "compartment_status": compartment_status,
            "unlock_ms": 0,
            "display": "",
        }
        return "", data

    error_code = ""
    comp = None
    session = None
    linked_session = None
    display = ""

    if event_type in COMPARTMENT_EVENTS:
        if number not in comps:
            error_code = "INVALID_PAYLOAD"
        else:
            comp = comps[number]

    if comp is not None:
        running = state.running_session(comp)
        session_id = 0
        if event_type in SESSION_EVENTS:
            session_id = item["session_id"]

        apply_event = True
        if session_id == 0 or (running is not None and running.id == session_id):
            # Q3
            session = running
            linked_session = running
        else:
            # Q4
            error_code = "SESSION_NOT_FOUND"
            linked_session = Session.objects.filter(
                id=session_id, compartment__device=device
            ).first()
            if running is not None:
                # Ngan dang co phien khac: chi ghi log
                apply_event = False
                session = running

        if apply_event:
            if event_type == "DOOR_OPENED":
                state.on_door_opened(comp, session, now)
            elif event_type == "DOOR_CLOSED":
                old_state = ""
                if session is not None:
                    old_state = session.state
                state.on_door_closed(comp, session, item["has_item"], now)
                if session is not None:
                    session.refresh_from_db()
                    if (old_state == "OPEN" or old_state == "CREATED") and session.state == "OCCUPIED":
                        display = DISPLAY_LOCKED
            elif event_type == "LOCK_FAILED":
                state.on_lock_failed(comp, now)
            # ITEM_IN, ITEM_OUT, DOOR_TIMEOUT chi ghi log

        if session is not None:
            session.refresh_from_db()

    elif error_code == "" and event_type == "BOOT":
        state.on_boot(device, item["firmware_version"], now)
    # CARD_READ_FAIL chi ghi log

    compartment_number = None
    if number != 0:
        compartment_number = number
    Event.objects.create(
        device=device,
        request_id=request_id,
        event_type=event_type,
        session=linked_session,
        compartment_number=compartment_number,
        has_item=item["has_item"],
        device_time=datetime.fromisoformat(item["device_time"]),
        received_at=now,
        accepted=(error_code == ""),
        error_code=error_code,
    )

    session_state = ""
    if session is not None:
        session_state = session.state
    compartment_status = ""
    if comp is not None:
        compartment_status = comp.status
    data = {
        "session_state": session_state,
        "compartment_status": compartment_status,
        "unlock_ms": 0,
        "display": display,
    }
    return error_code, data


def events(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    device = get_device(request)
    if device is None:
        return fail("DEVICE_UNAUTHORIZED")
    body = read_body(request, 512)
    if body is None:
        return fail("INVALID_PAYLOAD")
    error_code = check_event(device, body)
    if error_code != "":
        return fail(error_code)

    now = timezone.now()
    with transaction.atomic():
        # Q20
        comps = {}
        for comp in Compartment.objects.select_for_update().filter(device=device).order_by("number"):
            comps[comp.number] = comp

        logged = find_logged(device, body["request_id"])
        if logged is not None:
            if logged["success"]:
                return ok(logged["data"])
            return fail(logged["error_code"])

        error_code, data = handle_event(device, comps, body, now)
        if error_code == "":
            response = ok(data)
        else:
            response = fail(error_code)

        RequestLog.objects.create(
            device=device,
            request_id=body["request_id"],
            endpoint="events",
            response=json.loads(response.content),
            created_at=now,
        )
    return response


def events_batch(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    device = get_device(request)
    if device is None:
        return fail("DEVICE_UNAUTHORIZED")
    body = read_body(request, 8192)
    if body is None:
        return fail("INVALID_PAYLOAD")
    if type(body.get("device_id")) is not str:
        return fail("INVALID_PAYLOAD")
    if body["device_id"] != device.device_id:
        return fail("DEVICE_UNAUTHORIZED")
    items = body.get("events")
    if type(items) is not list or len(items) == 0 or len(items) > 20:
        return fail("INVALID_PAYLOAD")

    # Ket qua giu dung thu tu trong mang, xu ly theo so dem trong request_id
    results = []
    order = []
    index = 0
    for item in items:
        request_id = ""
        if type(item) is dict and type(item.get("request_id")) is str:
            request_id = item["request_id"]
        error_code = check_event(device, item)
        results.append({"request_id": request_id, "accepted": False, "error_code": error_code})
        if error_code == "":
            order.append((int(request_id[-6:]), index))
        index = index + 1
    order.sort()

    now = timezone.now()
    with transaction.atomic():
        # Q20
        comps = {}
        for comp in Compartment.objects.select_for_update().filter(device=device).order_by("number"):
            comps[comp.number] = comp

        for seq, index in order:
            # Doc lai sau moi phan tu vi phan tu truoc co the da doi hoac bi hoan tac
            device.refresh_from_db()
            for comp in comps.values():
                comp.refresh_from_db()
            result = results[index]
            try:
                with transaction.atomic():
                    error_code, data = handle_event(device, comps, items[index], now)
            except Exception:
                error_code = "SERVER_ERROR"
            result["accepted"] = error_code == ""
            result["error_code"] = error_code

    return ok({"results": results})


def scan(request):
    # 1. Token, kich thuoc, kieu truong
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
        ("card_uid", 8),
        ("request_id", 23),
        ("device_time", 25),
    ]:
        value = body.get(name)
        if type(value) is not str or len(value) > max_len:
            return fail("INVALID_PAYLOAD")
    # Q12
    if body["device_id"] != device.device_id:
        return fail("DEVICE_UNAUTHORIZED")
    if re.fullmatch(r"[0-9A-F]{8}", body["card_uid"]) is None:
        return fail("INVALID_PAYLOAD")
    if re.fullmatch(re.escape(device.device_id) + r"-[0-9]{6}", body["request_id"]) is None:
        return fail("INVALID_PAYLOAD")
    try:
        device_time = datetime.fromisoformat(body["device_time"])
    except ValueError:
        return fail("INVALID_PAYLOAD")
    if device_time.tzinfo is None:
        return fail("INVALID_PAYLOAD")

    card_uid = body["card_uid"]
    request_id = body["request_id"]
    now = timezone.now()

    # 2. Cac moc thoi gian, transaction rieng
    with transaction.atomic():
        state.run_time_checks(now)

    # 3. Q10
    logged = find_logged(device, request_id)
    if logged is not None:
        if logged["success"]:
            return ok(logged["data"])
        return fail(logged["error_code"])

    # 4. Tra the, chua co thi hoi he thong ngoai, ngoai transaction
    info = None
    if not CardUser.objects.filter(card_uid=card_uid).exists():
        info = adapters.lookup(card_uid, now)

    # 5. Chuan bi khoan thu, ngoai transaction (B7)
    prepared = None
    user = CardUser.objects.filter(card_uid=card_uid).first()
    if user is not None and not user.blocked:
        session = (
            Session.objects.filter(user=user, state="OCCUPIED")
            .select_related("compartment")
            .first()
        )
        if session is not None and session.payment_status != "PAID":
            comp = session.compartment
            rest_limit = now - timedelta(seconds=settings.LOCK_REST_SEC)
            rested = comp.last_unlock_at is None or comp.last_unlock_at <= rest_limit
            if comp.device_id == device.id and comp.status != "ERROR" and rested:
                rule = FeeRule.objects.get(id=1)
                duration_min = duration_minutes(session.occupied_at, now)
                fee = compute_fee(duration_min, rule, user.source)
                if fee > 0:
                    old_payment = (
                        Payment.objects.filter(
                            session=session, state="PENDING", expires_at__gt=now
                        )
                        .order_by("-created_at")
                        .first()
                    )
                    if old_payment is not None:
                        prepared = {
                            "session_id": session.id,
                            "payment_id": old_payment.id,
                            "pay_code": old_payment.pay_code,
                            "charged": True,
                        }
                    else:
                        pay_code = new_pay_code()
                        charged = create_charge(
                            user.source, pay_code, user.external_id, fee, session.id, now
                        )
                        prepared = {
                            "session_id": session.id,
                            "payment_id": None,
                            "pay_code": pay_code,
                            "charged": charged,
                        }

    # 6. Quyet dinh trong transaction
    with transaction.atomic():
        log = RequestLog.objects.create(
            device=device,
            request_id=request_id,
            endpoint="scan",
            response={},
            created_at=now,
        )
        # Q20
        comps = {}
        comps_by_id = {}
        for comp in Compartment.objects.select_for_update().filter(device=device).order_by("number"):
            comps[comp.number] = comp
            comps_by_id[comp.id] = comp

        response = None
        user = CardUser.objects.filter(card_uid=card_uid).first()
        if user is None:
            if info is None:
                response = fail("CARD_NOT_FOUND")
            else:
                user = CardUser.objects.create(
                    card_uid=card_uid,
                    name=info["name"],
                    source=info["source"],
                    external_id=info["external_id"],
                    blocked=not info["active"],
                    created_at=now,
                )

        if response is None and user.blocked:
            response = fail("CARD_BLOCKED")

        if response is None:
            session = Session.objects.filter(user=user, state__in=RUNNING_STATES).first()
            rest_limit = now - timedelta(seconds=settings.LOCK_REST_SEC)

            if session is None:
                # Cap ngan FREE so nho nhat da nghi du 60 giay (BE 1.4, Q1)
                has_free = False
                chosen = None
                for number in sorted(comps.keys()):
                    comp = comps[number]
                    if comp.status != "FREE":
                        continue
                    has_free = True
                    if comp.last_unlock_at is None or comp.last_unlock_at <= rest_limit:
                        chosen = comp
                        break
                if chosen is None and not has_free:
                    response = fail("NO_FREE_COMPARTMENT")
                elif chosen is None:
                    response = fail("TOO_SOON")
                else:
                    session = state.start_session(user, chosen, now)
                    response = ok(
                        {
                            "action": "DEPOSIT",
                            "session_id": session.id,
                            "compartment": chosen.number,
                            "unlock_ms": settings.UNLOCK_MS,
                            "timeout_sec": settings.DOOR_TIMEOUT_SEC,
                            "display": "Ngan %d - Moi bo do vao" % chosen.number,
                            "duration_min": 0,
                            "fee": 0,
                            "qr": "",
                            "pay_timeout_sec": 0,
                        }
                    )

            elif session.state != "OCCUPIED":
                response = fail("SESSION_CONFLICT")

            elif session.compartment_id not in comps_by_id:
                # Phien nam o tu khac, tu nay khong mo duoc
                response = fail("SESSION_CONFLICT")

            else:
                comp = comps_by_id[session.compartment_id]
                session.compartment = comp
                if comp.status == "ERROR":
                    response = fail("COMPARTMENT_ERROR")
                elif comp.last_unlock_at is not None and comp.last_unlock_at > rest_limit:
                    response = fail("TOO_SOON")
                else:
                    rule = FeeRule.objects.get(id=1)
                    pickup = False
                    if session.payment_status == "PAID":
                        # Giu nguyen phi da luu. Phien danh dau thu tay chua co phi thi chot luc nay
                        if session.duration_min is None or session.fee is None:
                            session.duration_min = duration_minutes(session.occupied_at, now)
                            session.fee = compute_fee(session.duration_min, rule, user.source)
                            session.save()
                        pickup = True
                    else:
                        duration_min = duration_minutes(session.occupied_at, now)
                        fee = compute_fee(duration_min, rule, user.source)
                        if fee == 0:
                            session.duration_min = duration_min
                            session.fee = fee
                            session.save()
                            pickup = True
                        elif prepared is None or prepared["session_id"] != session.id:
                            # Buoc 5 chua chuan bi ma buoc 6 lai can: trang thai doi giua
                            # chung. Tra SERVER_ERROR de firmware gui lai.
                            raise RuntimeError("scan: khoan thu chua duoc chuan bi")
                        elif not prepared["charged"]:
                            # He thong ngoai loi, phien giu nguyen
                            response = fail("PAYMENT_UNAVAILABLE")
                        else:
                            if prepared["payment_id"] is not None:
                                # Dung lai khoan thu PENDING con han (Q2)
                                payment = Payment.objects.filter(
                                    id=prepared["payment_id"], state="PENDING", expires_at__gt=now
                                ).first()
                                if payment is None:
                                    raise RuntimeError("scan: khoan thu cu da het han")
                                pay_timeout_sec = int((payment.expires_at - now).total_seconds())
                                if pay_timeout_sec < 1:
                                    pay_timeout_sec = 1
                                if session.duration_min is not None:
                                    duration_min = session.duration_min
                            else:
                                payment = Payment.objects.create(
                                    session=session,
                                    pay_code=prepared["pay_code"],
                                    source=user.source,
                                    amount=fee,
                                    state="PENDING",
                                    created_at=now,
                                    expires_at=now + timedelta(seconds=settings.PAY_TIMEOUT_SEC),
                                )
                                session.payment_status = "PENDING"
                                session.duration_min = duration_min
                                session.fee = fee
                                session.save()
                                pay_timeout_sec = settings.PAY_TIMEOUT_SEC

                            # qr theo BE 1.4
                            if payment.source == "STUDENT":
                                pay_url = settings.SOURCE1_PAY_URL
                            else:
                                pay_url = settings.SOURCE2_PAY_URL
                            response = ok(
                                {
                                    "action": "PAYMENT",
                                    "session_id": session.id,
                                    "compartment": comp.number,
                                    "unlock_ms": 0,
                                    "timeout_sec": 0,
                                    "display": "",
                                    "duration_min": duration_min,
                                    "fee": payment.amount,
                                    "qr": pay_url.rstrip("/") + "/P/" + payment.pay_code,
                                    "pay_timeout_sec": pay_timeout_sec,
                                }
                            )

                    if pickup:
                        state.start_releasing(session, now)
                        response = ok(
                            {
                                "action": "PICKUP",
                                "session_id": session.id,
                                "compartment": comp.number,
                                "unlock_ms": settings.UNLOCK_MS,
                                "timeout_sec": settings.DOOR_TIMEOUT_SEC,
                                "display": "Ngan %d - Moi lay do" % comp.number,
                                "duration_min": session.duration_min,
                                "fee": session.fee,
                                "qr": "",
                                "pay_timeout_sec": 0,
                            }
                        )

        # 7. Luu phan hoi, ke ca phan hoi loi
        log.response = json.loads(response.content)
        log.save()
    return response
