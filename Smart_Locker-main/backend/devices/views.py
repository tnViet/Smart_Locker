import json
import re
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.common import fail, find_logged, get_device, ok, read_body
from devices.models import Command, RequestLog
from lockers import state
from lockers.models import Compartment, FeeRule

UINT32_MAX = 4294967295


def pending_commands(device, now):
    # Toi da 1 lenh PENDING cu nhat con han, ngan da nghi du 60 giay (Q7)
    ttl_limit = now - timedelta(seconds=settings.COMMAND_TTL_SEC)
    rest_limit = now - timedelta(seconds=settings.LOCK_REST_SEC)
    commands = (
        Command.objects.filter(device=device, state="PENDING", created_at__gte=ttl_limit)
        .select_related("compartment")
        .order_by("created_at", "id")
    )
    for command in commands:
        last_unlock_at = command.compartment.last_unlock_at
        if last_unlock_at is None or last_unlock_at <= rest_limit:
            return [
                {
                    "command_id": command.id,
                    "type": command.type,
                    "compartment": command.compartment.number,
                    "unlock_ms": command.unlock_ms,
                }
            ]
    return []


def heartbeat(request):
    if request.method != "POST":
        return fail("INVALID_PAYLOAD")
    device = get_device(request)
    if device is None:
        return fail("DEVICE_UNAUTHORIZED")
    body = read_body(request, 256)
    if body is None:
        return fail("INVALID_PAYLOAD")

    device_id = body.get("device_id")
    if type(device_id) is not str or len(device_id) > 16:
        return fail("INVALID_PAYLOAD")
    uptime_sec = body.get("uptime_sec")
    if type(uptime_sec) is not int or uptime_sec < 0 or uptime_sec > UINT32_MAX:
        return fail("INVALID_PAYLOAD")
    rssi = body.get("rssi")
    if type(rssi) is not int or rssi < -32768 or rssi > 32767:
        return fail("INVALID_PAYLOAD")
    free_heap = body.get("free_heap")
    if type(free_heap) is not int or free_heap < 0 or free_heap > UINT32_MAX:
        return fail("INVALID_PAYLOAD")
    pending_count = body.get("pending_count")
    if type(pending_count) is not int or pending_count < 0 or pending_count > 65535:
        return fail("INVALID_PAYLOAD")
    # Q12
    if device_id != device.device_id:
        return fail("DEVICE_UNAUTHORIZED")

    now = timezone.now()
    with transaction.atomic():
        state.run_time_checks(now)
        device.last_heartbeat_at = now
        device.last_rssi = rssi
        device.last_free_heap = free_heap
        device.last_pending_count = pending_count
        device.save()
        commands = pending_commands(device, now)
    return ok({"pending_commands": commands})


def sync(request):
    if request.method != "GET":
        return fail("INVALID_PAYLOAD")
    device = get_device(request)
    if device is None:
        return fail("DEVICE_UNAUTHORIZED")
    device_id = request.GET.get("device_id")
    if device_id is None or len(device_id) > 16:
        return fail("INVALID_PAYLOAD")
    # Q12
    if device_id != device.device_id:
        return fail("DEVICE_UNAUTHORIZED")

    now = timezone.now()
    compartments = []
    for comp in Compartment.objects.filter(device=device).order_by("number"):
        session = state.running_session(comp)
        session_id = 0
        if session is not None:
            session_id = session.id
        compartments.append(
            {
                "number": comp.number,
                "status": comp.status,
                "door_closed": comp.door_closed,
                "session_id": session_id,
            }
        )

    data = {
        "server_time": timezone.localtime(now).isoformat(timespec="seconds"),
        "compartments": compartments,
        "pending_commands": pending_commands(device, now),
    }
    return ok(data)


def command_ack(request, command_id):
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
        ("result", 8),
    ]:
        value = body.get(name)
        if type(value) is not str or len(value) > max_len:
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
    result = body["result"]
    if result != "DONE" and result != "FAILED" and result != "REJECTED":
        return fail("INVALID_PAYLOAD")

    now = timezone.now()
    with transaction.atomic():
        # Q20
        comps = {}
        for comp in Compartment.objects.select_for_update().filter(device=device):
            comps[comp.id] = comp

        logged = find_logged(device, body["request_id"])
        if logged is not None:
            if logged["success"]:
                return ok(logged["data"])
            return fail(logged["error_code"])

        command = Command.objects.filter(id=command_id, device=device).first()
        if command is None:
            # Q17
            response = fail("INVALID_PAYLOAD")
        elif command.state == "PENDING" or command.state == "EXPIRED":
            # Q17: lenh EXPIRED nhan DONE van doi trang thai nhu lenh PENDING
            if result == "DONE":
                command.compartment = comps[command.compartment_id]
                rule = FeeRule.objects.get(id=1)
                state.on_command_done(command, rule, now)
            else:
                command.state = result
                command.acked_at = now
                command.save()
            response = ok({})
        else:
            # Lenh da DONE, FAILED, REJECTED: thanh cong, khong lam gi
            response = ok({})

        RequestLog.objects.create(
            device=device,
            request_id=body["request_id"],
            endpoint="commands/ack",
            response=json.loads(response.content),
            created_at=now,
        )
    return response
