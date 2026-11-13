# May trang thai cua ngan va phien, Quy chuan API chuong 6.
# Moi ham chi sua va save() doi tuong, khong mo transaction, khong tra HTTP.
from datetime import timedelta

from django.conf import settings

from devices.models import Command, RequestLog
from lockers.fee import compute_fee, duration_minutes
from lockers.models import RUNNING_STATES, Compartment, Session
from payments.models import Payment


def set_compartment(comp, status, now):
    # Chi doi status_changed_at khi trang thai thuc su doi, de giu dung moc 10 phut
    if comp.status != status:
        comp.status = status
        comp.status_changed_at = now
    comp.save()


def running_session(comp):
    session = Session.objects.filter(
        compartment=comp, state__in=RUNNING_STATES
    ).first()
    if session is not None:
        # Dung chung mot doi tuong ngan de khong ghi de lan nhau khi save()
        session.compartment = comp
    return session


def compartment_error(comp, now):
    set_compartment(comp, "ERROR", now)
    session = running_session(comp)
    if session is None:
        return
    if session.state == "CREATED" or session.state == "OPEN":
        session.state = "CANCELLED"
        session.closed_at = now
        session.save()
    elif session.state == "RELEASING":
        session.state = "CLOSED"
        session.closed_at = now
        session.save()
    # Phien OCCUPIED giu nguyen, quan ly xu ly bang mo thu cong


def run_time_checks(now):
    wait_limit = now - timedelta(seconds=settings.WAIT_OPEN_SEC)

    # 1. Phien CREATED qua han cho cua mo: huy, ngan ve FREE
    sessions = Session.objects.filter(state="CREATED").select_related("compartment")
    for session in sessions:
        comp = session.compartment
        start = comp.last_unlock_at
        if start is None:
            start = session.created_at
        if start < wait_limit:
            session.state = "CANCELLED"
            session.closed_at = now
            session.save()
            if comp.status == "OPEN":
                set_compartment(comp, "FREE", now)

    # 2. Phien RELEASING qua han cho cua mo: ve OCCUPIED, ngan ve OCCUPIED
    sessions = Session.objects.filter(
        state="RELEASING", door_opened_at__isnull=True
    ).select_related("compartment")
    for session in sessions:
        comp = session.compartment
        start = comp.last_unlock_at
        if start is None:
            start = session.created_at
        if start < wait_limit:
            session.state = "OCCUPIED"
            session.save()
            if comp.status == "OPEN":
                set_compartment(comp, "OCCUPIED", now)

    # 3. Ngan OPEN qua 10 phut: chuyen ERROR
    open_limit = now - timedelta(seconds=settings.OPEN_MAX_SEC)
    comps = Compartment.objects.filter(status="OPEN", status_changed_at__lt=open_limit)
    for comp in comps:
        compartment_error(comp, now)

    # 4. Lenh PENDING qua han: EXPIRED
    command_limit = now - timedelta(seconds=settings.COMMAND_TTL_SEC)
    Command.objects.filter(state="PENDING", created_at__lt=command_limit).update(
        state="EXPIRED"
    )

    # 5. Khoan thu PENDING qua han: EXPIRED, payment_status cua phien ve NONE (Q9)
    payments = Payment.objects.filter(
        state="PENDING", expires_at__lte=now
    ).select_related("session")
    for payment in payments:
        payment.state = "EXPIRED"
        payment.save()
        session = payment.session
        if session.payment_status == "PENDING":
            session.payment_status = "NONE"
            session.save()

    # 6. Dong request_log cu hon 10 phut: xoa
    log_limit = now - timedelta(seconds=settings.REQUEST_LOG_TTL_SEC)
    RequestLog.objects.filter(created_at__lt=log_limit).delete()


def start_session(user, comp, now):
    session = Session.objects.create(
        user=user,
        compartment=comp,
        state="CREATED",
        created_at=now,
        payment_status="NONE",
    )
    comp.last_unlock_at = now
    set_compartment(comp, "OPEN", now)
    return session


def start_releasing(session, now):
    session.state = "RELEASING"
    session.door_opened_at = None
    session.save()
    comp = session.compartment
    comp.last_unlock_at = now
    if comp.status == "OCCUPIED":
        set_compartment(comp, "OPEN", now)
    else:
        # Ngan ERROR giu nguyen ERROR (Q5)
        comp.save()


def on_door_opened(comp, session, now):
    comp.door_closed = False

    if session is not None:
        if session.state == "CREATED":
            session.state = "OPEN"
            session.door_opened_at = now
            session.save()
        elif session.state == "RELEASING":
            session.door_opened_at = now
            session.save()

    if comp.status == "FREE" or comp.status == "OCCUPIED":
        has_command = Command.objects.filter(
            compartment=comp, type="OPEN", state="PENDING"
        ).exists()
        if has_command:
            # Q6: lenh mo thu cong dang cho ack, khong coi la mo bat thuong
            comp.save()
        else:
            compartment_error(comp, now)
        return

    comp.save()


def on_door_closed(comp, session, has_item, now):
    comp.door_closed = True
    comp.has_item = has_item

    if comp.status == "OPEN":
        if session is None:
            if has_item:
                compartment_error(comp, now)
            else:
                set_compartment(comp, "FREE", now)
            return

        if session.state == "OPEN" or session.state == "CREATED":
            # Q15: phien CREATED xu ly nhu phien OPEN
            if has_item:
                session.state = "OCCUPIED"
                if session.occupied_at is None:
                    session.occupied_at = now
                session.save()
                set_compartment(comp, "OCCUPIED", now)
            else:
                session.state = "CANCELLED"
                session.closed_at = now
                session.save()
                set_compartment(comp, "FREE", now)
            return

        if session.state == "RELEASING":
            if has_item:
                session.state = "OCCUPIED"
                session.save()
                set_compartment(comp, "OCCUPIED", now)
            else:
                session.state = "CLOSED"
                session.closed_at = now
                session.save()
                set_compartment(comp, "FREE", now)
            return

        comp.save()
        return

    if comp.status == "ERROR" and session is not None and session.state == "RELEASING":
        # Q5: doi phien nhu tren, ngan giu ERROR cho toi khi reset
        if has_item:
            session.state = "OCCUPIED"
        else:
            session.state = "CLOSED"
            session.closed_at = now
        session.save()

    # Ngan FREE, OCCUPIED, ERROR: khong doi trang thai ngan
    comp.save()


def on_lock_failed(comp, now):
    compartment_error(comp, now)


def on_boot(device, firmware_version, now):
    device.firmware_version = firmware_version
    device.save()

    comps = Compartment.objects.filter(device=device).order_by("number")
    for comp in comps:
        session = running_session(comp)
        if session is None:
            continue
        if session.state == "CREATED":
            session.state = "CANCELLED"
            session.closed_at = now
            session.save()
            if comp.status == "OPEN":
                set_compartment(comp, "FREE", now)
        elif session.state == "OPEN":
            # Q16: ngan giu OPEN, cho su kien cua sau /sync hoac moc 10 phut
            session.state = "CANCELLED"
            session.closed_at = now
            session.save()
        elif session.state == "RELEASING" and session.door_opened_at is None:
            session.state = "OCCUPIED"
            session.save()
            if comp.status == "OPEN":
                set_compartment(comp, "OCCUPIED", now)


def on_command_done(command, rule, now):
    command.state = "DONE"
    command.acked_at = now
    command.save()

    comp = command.compartment
    # Q7: last_unlock_at cua lenh thu cong ghi luc ack DONE
    comp.last_unlock_at = now

    if comp.status == "FREE":
        set_compartment(comp, "OPEN", now)
        return

    session = running_session(comp)
    if (
        session is not None
        and session.state == "OCCUPIED"
        and (comp.status == "OCCUPIED" or comp.status == "ERROR")
    ):
        session.duration_min = duration_minutes(session.occupied_at, now)
        session.fee = compute_fee(session.duration_min, rule, session.user.source)
        session.save()
        start_releasing(session, now)
        return

    comp.save()


def reset_compartment(comp, now):
    if comp.status != "ERROR":
        return False
    if running_session(comp) is not None:
        return False
    set_compartment(comp, "FREE", now)
    return True
