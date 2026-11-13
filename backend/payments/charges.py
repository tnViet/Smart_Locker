# Tao khoan thu o he thong ngoai, theo tai lieu He thong ngoai mo phong muc Tao khoan thu
import hashlib
import hmac
import secrets

import requests
from django.conf import settings

from payments.models import Payment

PAY_CODE_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def new_pay_code():
    while True:
        code = ""
        for i in range(6):
            code = code + secrets.choice(PAY_CODE_CHARS)
        if not Payment.objects.filter(pay_code=code).exists():
            return code


def sign(secret, text):
    return hmac.new(
        secret.encode("utf-8"), text.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def create_charge(source, pay_code, external_id, amount, session_id, now):
    if source == "STUDENT":
        base_url = settings.SOURCE1_URL
    elif source == "PARKING":
        base_url = settings.SOURCE2_URL
    else:
        return False

    ts = int(now.timestamp())
    text = "%s|%s|%d|%d|%d" % (pay_code, external_id, amount, session_id, ts)
    body = {
        "pay_code": pay_code,
        "external_id": external_id,
        "amount": amount,
        "session_id": session_id,
        "expires_in": settings.PAY_TIMEOUT_SEC,
        "ts": ts,
        "signature": sign(settings.PAY_HMAC_SECRET, text),
    }
    try:
        resp = requests.post(
            base_url.rstrip("/") + "/charges",
            json=body,
            timeout=settings.EXTERNAL_TIMEOUT_SEC,
        )
        if resp.status_code != 200:
            return False
        data = resp.json()
    except Exception:
        return False
    if type(data) is not dict:
        return False
    return data.get("received") is True
