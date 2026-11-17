import re
from datetime import date, timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from config.common import fail, ok, read_body
from dashboard.auth import check_token, make_token, role_of
from devices.models import Command, Device
from identity.models import CardUser
from lockers import state
from lockers.fee import compute_fee, duration_minutes
from lockers.models import RUNNING_STATES, Compartment, Event, FeeRule, Session

SESSION_STATES = ["CREATED", "OPEN", "OCCUPIED", "RELEASING", "CLOSED", "CANCELLED"]
# Phu luc A: online khi co heartbeat trong 90 giay gan nhat
ONLINE_SEC = 90
MAX_BODY = 4096
MAX_PAGE_SIZE = 100


def iso(value):
    # Gio Viet Nam +07:00, khong co phan le giay. null giu nguyen
    if value is None:
        return None
    return timezone.localtime(value).isoformat(timespec="seconds")


def page_params(request):
    # Tra (page, page_size), hoac (None, None) khi tham so sai. API 3.2
    try:
        page = int(request.GET.get("page", "1"))
        page_size = int(request.GET.get("page_size", "20"))
    except ValueError:
        return None, None
    if page < 1 or page_size < 1 or page_size > MAX_PAGE_SIZE:
        return None, None
    return page, page_size


def session_row(session):
    return {
        "id": session.id,
        "user_id": session.user_id,
        "user_name": session.user.name,
        "card_uid": session.user.card_uid,
        "compartment": session.compartment.number,
        "state": session.state,
        "created_at": iso(session.created_at),
        "occupied_at": iso(session.occupied_at),
        "closed_at": iso(session.closed_at),
        "duration_min": session.duration_min,
        "fee": session.fee,
        "payment_status": session.payment_status,
    }


def user_row(user):
    return {
        "id": user.id,
        "card_uid": user.card_uid,
        "name": user.name,
        "source": user.source,
        "external_id": user.external_id,
        "blocked": user.blocked,
        "created_at": iso(user.created_at),
    }


def fee_rule_data(rule):
    updated_by = None
    if rule.updated_by is not None:
        updated_by = rule.updated_by.username
    return {
        "free_min": rule.free_min,
        "block_min": rule.block_min,
        "block_fee": rule.block_fee,
        "updated_at": iso(rule.updated_at),
        "updated_by": updated_by,
    }


def login(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    body = read_body(request, MAX_BODY)
    if body is None:
        return fail("INVALID_PAYLOAD")
    username = body.get("username")
    password = body.get("password")
    if type(username) is not str or type(password) is not str:
        return fail("INVALID_PAYLOAD")

    user = authenticate(username=username, password=password)
    if user is None:
        return fail("UNAUTHORIZED")
    role = role_of(user)
    if role == "":
        return fail("FORBIDDEN")
    now = timezone.now()
    return ok(
        {
            "access_token": make_token(user, now),
            "expires_in": settings.JWT_TTL_SEC,
            "role": role,
        }
    )


def compartments(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)

    now = timezone.now()
    with transaction.atomic():
        state.run_time_checks(now)

    rule = FeeRule.objects.get(id=1)
    data = []
    for comp in Compartment.objects.select_related("device").order_by("device__device_id", "number"):
        session_data = None
        session = (
            Session.objects.filter(compartment=comp, state__in=RUNNING_STATES)
            .select_related("user")
            .first()
        )
        if session is not None:
            duration_min = 0
            current_fee = 0
            if session.occupied_at is not None:
                duration_min = duration_minutes(session.occupied_at, now)
                current_fee = compute_fee(duration_min, rule, session.user.source)
            session_data = {
                "id": session.id,
                "user_name": session.user.name,
                "started_at": iso(session.occupied_at),
                "duration_min": duration_min,
                "current_fee": current_fee,
            }
        data.append(
            {
                "number": comp.number,
                "status": comp.status,
                "has_item": comp.has_item,
                "door_closed": comp.door_closed,
                "session": session_data,
            }
        )
    return ok(data)


def sessions(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)
    page, page_size = page_params(request)
    if page is None:
        return fail("INVALID_PAYLOAD")

    query = Session.objects.select_related("user", "compartment")
    date_text = request.GET.get("date")
    if date_text is not None:
        try:
            day = date.fromisoformat(date_text)
        except ValueError:
            return fail("INVALID_PAYLOAD")
        query = query.filter(created_at__date=day)
    state_text = request.GET.get("state")
    if state_text is not None:
        if state_text not in SESSION_STATES:
            return fail("INVALID_PAYLOAD")
        query = query.filter(state=state_text)
    user_text = request.GET.get("user_id")
    if user_text is not None:
        try:
            user_id = int(user_text)
        except ValueError:
            return fail("INVALID_PAYLOAD")
        query = query.filter(user_id=user_id)

    count = query.count()
    start = (page - 1) * page_size
    results = []
    for session in query.order_by("-created_at", "-id")[start:start + page_size]:
        results.append(session_row(session))
    return ok({"count": count, "page": page, "page_size": page_size, "results": results})


def session_detail(request, session_id):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)

    session = Session.objects.select_related("user", "compartment").filter(id=session_id).first()
    if session is None:
        return fail("NOT_FOUND")
    data = session_row(session)
    events = []
    for event in Event.objects.filter(session=session).order_by("received_at", "id"):
        events.append(
            {
                "id": event.id,
                "event_type": event.event_type,
                "has_item": event.has_item,
                "device_time": iso(event.device_time),
                "received_at": iso(event.received_at),
                "accepted": event.accepted,
                "error_code": event.error_code,
            }
        )
    data["events"] = events
    return ok(data)


def session_pay(request, session_id):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, True)
    if error_code != "":
        return fail(error_code)

    with transaction.atomic():
        session = Session.objects.select_for_update().filter(id=session_id).first()
        if session is None:
            return fail("NOT_FOUND")
        if session.state != "OCCUPIED":
            return fail("SESSION_CONFLICT")
        # Chi doi payment_status, khong tao dong payments (BE 2)
        session.payment_status = "PAID"
        session.save()
    return ok({"id": session.id, "payment_status": session.payment_status})


def users(request):
    if request.method == "GET":
        user, role, error_code = check_token(request, False)
        if error_code != "":
            return fail(error_code)
        page, page_size = page_params(request)
        if page is None:
            return fail("INVALID_PAYLOAD")
        query = CardUser.objects.all()
        count = query.count()
        start = (page - 1) * page_size
        results = []
        for card_user in query.order_by("id")[start:start + page_size]:
            results.append(user_row(card_user))
        return ok({"count": count, "page": page, "page_size": page_size, "results": results})

    if request.method == "POST":
        user, role, error_code = check_token(request, True)
        if error_code != "":
            return fail(error_code)
        body = read_body(request, MAX_BODY)
        if body is None:
            return fail("INVALID_PAYLOAD")
        card_uid = body.get("card_uid")
        name = body.get("name")
        if type(card_uid) is not str or re.fullmatch(r"[0-9A-F]{8}", card_uid) is None:
            return fail("INVALID_PAYLOAD")
        if type(name) is not str or name.strip() == "" or len(name) > 100:
            return fail("INVALID_PAYLOAD")
        try:
            with transaction.atomic():
                card_user = CardUser.objects.create(
                    card_uid=card_uid,
                    name=name.strip(),
                    source="LOCAL",
                    external_id=None,
                    blocked=False,
                    created_at=timezone.now(),
                )
        except IntegrityError:
            # Trung card_uid
            return fail("INVALID_PAYLOAD")
        return ok(user_row(card_user))

    return fail("INVALID_PAYLOAD")


def user_update(request, user_id):
    if request.method != "PATCH":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, True)
    if error_code != "":
        return fail(error_code)
    body = read_body(request, MAX_BODY)
    if body is None:
        return fail("INVALID_PAYLOAD")
    blocked = body.get("blocked")
    if type(blocked) is not bool:
        return fail("INVALID_PAYLOAD")

    card_user = CardUser.objects.filter(id=user_id).first()
    if card_user is None:
        return fail("NOT_FOUND")
    card_user.blocked = blocked
    card_user.save()
    return ok(user_row(card_user))


def stats_overview(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)

    today = timezone.localdate()
    sessions_today = Session.objects.filter(created_at__date=today).count()
    revenue = Session.objects.filter(
        payment_status="PAID", closed_at__date=today
    ).aggregate(total=Sum("fee"))["total"]
    if revenue is None:
        revenue = 0
    total = Compartment.objects.count()
    busy = Compartment.objects.exclude(status="FREE").count()
    occupancy_rate = 0
    if total > 0:
        occupancy_rate = busy / total
    return ok(
        {
            "sessions_today": sessions_today,
            "revenue_today": revenue,
            "occupancy_rate": occupancy_rate,
        }
    )


def stats_revenue(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)
    try:
        date_from = date.fromisoformat(request.GET.get("from", ""))
        date_to = date.fromisoformat(request.GET.get("to", ""))
    except ValueError:
        return fail("INVALID_PAYLOAD")
    if date_to < date_from or (date_to - date_from).days > 366:
        return fail("INVALID_PAYLOAD")

    revenue_by_day = {}
    rows = (
        Session.objects.filter(
            payment_status="PAID", closed_at__date__gte=date_from, closed_at__date__lte=date_to
        )
        .annotate(day=TruncDate("closed_at"))
        .values("day")
        .annotate(total=Sum("fee"))
    )
    for row in rows:
        revenue_by_day[row["day"]] = row["total"] or 0

    sessions_by_day = {}
    rows = (
        Session.objects.filter(created_at__date__gte=date_from, created_at__date__lte=date_to)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
    )
    for row in rows:
        sessions_by_day[row["day"]] = row["total"]

    data = []
    day = date_from
    while day <= date_to:
        data.append(
            {
                "date": day.isoformat(),
                "revenue": revenue_by_day.get(day, 0),
                "sessions": sessions_by_day.get(day, 0),
            }
        )
        day = day + timedelta(days=1)
    return ok(data)


def devices(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, False)
    if error_code != "":
        return fail(error_code)

    online_limit = timezone.now() - timedelta(seconds=ONLINE_SEC)
    data = []
    for device in Device.objects.order_by("device_id"):
        online = device.last_heartbeat_at is not None and device.last_heartbeat_at >= online_limit
        data.append(
            {
                "device_id": device.device_id,
                "firmware_version": device.firmware_version,
                "last_heartbeat_at": iso(device.last_heartbeat_at),
                "rssi": device.last_rssi,
                "free_heap": device.last_free_heap,
                "pending_count": device.last_pending_count,
                "online": online,
            }
        )
    return ok(data)


def admin_open(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, True)
    if error_code != "":
        return fail(error_code)
    body = read_body(request, MAX_BODY)
    if body is None:
        return fail("INVALID_PAYLOAD")
    device_id = body.get("device_id")
    number = body.get("compartment")
    reason = body.get("reason")
    if type(device_id) is not str or type(number) is not int or type(reason) is not str:
        return fail("INVALID_PAYLOAD")

    device = Device.objects.filter(device_id=device_id).first()
    if device is None:
        return fail("NOT_FOUND")
    now = timezone.now()
    with transaction.atomic():
        # Q20
        comp = None
        for item in Compartment.objects.select_for_update().filter(device=device):
            if item.number == number:
                comp = item
        if comp is None:
            return fail("NOT_FOUND")
        if comp.status == "OPEN":
            return fail("SESSION_CONFLICT")
        rest_limit = now - timedelta(seconds=settings.LOCK_REST_SEC)
        if comp.last_unlock_at is not None and comp.last_unlock_at > rest_limit:
            return fail("TOO_SOON")
        command = Command.objects.create(
            device=device,
            compartment=comp,
            type="OPEN",
            unlock_ms=settings.UNLOCK_MS,
            reason=reason,
            created_by=user,
            state="PENDING",
            created_at=now,
        )
    return ok({"command_id": command.id})


def admin_reset(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    user, role, error_code = check_token(request, True)
    if error_code != "":
        return fail(error_code)
    body = read_body(request, MAX_BODY)
    if body is None:
        return fail("INVALID_PAYLOAD")
    device_id = body.get("device_id")
    number = body.get("compartment")
    if type(device_id) is not str or type(number) is not int:
        return fail("INVALID_PAYLOAD")

    device = Device.objects.filter(device_id=device_id).first()
    if device is None:
        return fail("NOT_FOUND")
    now = timezone.now()
    with transaction.atomic():
        # Q20
        comp = None
        for item in Compartment.objects.select_for_update().filter(device=device):
            if item.number == number:
                comp = item
        if comp is None:
            return fail("NOT_FOUND")
        if not state.reset_compartment(comp, now):
            return fail("COMPARTMENT_ERROR")
    return ok({"number": comp.number, "status": comp.status})


def fee_rules(request):
    if request.method == "GET":
        user, role, error_code = check_token(request, False)
        if error_code != "":
            return fail(error_code)
        rule = FeeRule.objects.select_related("updated_by").get(id=1)
        return ok(fee_rule_data(rule))

    if request.method == "PATCH":
        user, role, error_code = check_token(request, True)
        if error_code != "":
            return fail(error_code)
        body = read_body(request, MAX_BODY)
        if body is None:
            return fail("INVALID_PAYLOAD")

        changes = {}
        for name, min_value in [("free_min", 0), ("block_min", 1), ("block_fee", 0)]:
            if name in body:
                value = body[name]
                if type(value) is not int or value < min_value or value > 2147483647:
                    return fail("INVALID_PAYLOAD")
                changes[name] = value
        if len(changes) == 0:
            return fail("INVALID_PAYLOAD")

        with transaction.atomic():
            rule = FeeRule.objects.select_for_update().get(id=1)
            for name in changes:
                setattr(rule, name, changes[name])
            rule.updated_at = timezone.now()
            rule.updated_by = user
            rule.save()
        return ok(fee_rule_data(rule))

    return fail("INVALID_PAYLOAD")
