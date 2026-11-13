# Adapter tra dinh danh o hai he thong ngoai, theo tai lieu He thong ngoai mo phong.
# Moi loi (timeout, mat ket noi, status khac 200, JSON hong) deu tra None,
# khong gui lai (Quy chuan API 4.1, 4.2).
import hashlib
import hmac

import requests
from django.conf import settings


def lookup_source1(card_uid):
    url = settings.SOURCE1_URL.rstrip("/") + "/students/" + card_uid
    try:
        resp = requests.get(url, timeout=settings.EXTERNAL_TIMEOUT_SEC)
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    if type(data) is not dict:
        return None
    student_id = data.get("student_id")
    name = data.get("name")
    status = data.get("status")
    if type(student_id) is not str or student_id == "" or len(student_id) > 16:
        return None
    if type(name) is not str or len(name) > 100:
        return None
    if status != "active" and status != "inactive":
        return None
    return {
        "source": "STUDENT",
        "external_id": student_id,
        "name": name,
        "active": status == "active",
    }


def lookup_source2(card_uid, now):
    ts = int(now.timestamp())
    message = card_uid + str(ts)
    signature = hmac.new(
        settings.SOURCE2_HMAC_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    url = settings.SOURCE2_URL.rstrip("/") + "/verify"
    try:
        resp = requests.post(
            url,
            json={"uid": card_uid, "ts": ts},
            headers={"X-Signature": signature},
            timeout=settings.EXTERNAL_TIMEOUT_SEC,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
    except Exception:
        return None

    if type(data) is not dict:
        return None
    member_id = data.get("member_id")
    name = data.get("name")
    active = data.get("active")
    if type(member_id) is not str or member_id == "" or len(member_id) > 16:
        return None
    if type(name) is not str or len(name) > 100:
        return None
    if type(active) is not bool:
        return None
    return {
        "source": "PARKING",
        "external_id": member_id,
        "name": name,
        "active": active,
    }


def lookup(card_uid, now):
    info = lookup_source1(card_uid)
    if info is not None:
        return info
    return lookup_source2(card_uid, now)
