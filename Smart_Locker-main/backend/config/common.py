import hashlib
import json

from django.http import JsonResponse

from devices.models import Device, RequestLog

# Quy chuan API chuong 5
ERROR_HTTP = {
    "CARD_NOT_FOUND": 404,
    "CARD_BLOCKED": 403,
    "NO_FREE_COMPARTMENT": 409,
    "SESSION_NOT_FOUND": 404,
    "SESSION_CONFLICT": 409,
    "TOO_SOON": 429,
    "COMPARTMENT_ERROR": 409,
    "CARD_READ_FAIL": 503,
    "PAYMENT_UNAVAILABLE": 503,
    "DEVICE_UNAUTHORIZED": 401,
    "INVALID_PAYLOAD": 400,
    "SERVER_ERROR": 500,
    "PAYMENT_NOT_FOUND": 404,
    "INVALID_SIGNATURE": 401,
    # Rieng cho dashboard, Ke hoach backend Phu luc A
    "UNAUTHORIZED": 401,
    "FORBIDDEN": 403,
    "NOT_FOUND": 404,
}

# Ke hoach backend muc 3.3. ASCII, toi da 64 ky tu
ERROR_MESSAGE = {
    "CARD_NOT_FOUND": "The khong hop le",
    "CARD_BLOCKED": "The da bi khoa",
    "NO_FREE_COMPARTMENT": "Het ngan trong",
    "SESSION_NOT_FOUND": "Khong co phien phu hop",
    "SESSION_CONFLICT": "Phien dang mo cua",
    "TOO_SOON": "Vui long cho",
    "COMPARTMENT_ERROR": "Ngan dang loi",
    "PAYMENT_UNAVAILABLE": "Thu lai sau",
    "DEVICE_UNAUTHORIZED": "Token sai",
    "INVALID_PAYLOAD": "Goi tin sai",
    "SERVER_ERROR": "Loi may chu",
    "PAYMENT_NOT_FOUND": "Khong co khoan thu",
    "INVALID_SIGNATURE": "Chu ky sai",
    "UNAUTHORIZED": "Chua dang nhap hoac phien da het han",
    "FORBIDDEN": "Khong co quyen",
    "NOT_FOUND": "Khong tim thay",
}

# Khong co dau cach sau dau phay va dau hai cham (Dinh dang goi tin muc 1.4, 1.6).
# Sap xep khoa vi jsonb cua request_log tu doi thu tu khoa: phan hoi gui lai
# phai giong het lan dau tung byte. Ben nhan tra theo ten truong (muc 1.4).
JSON_PARAMS = {"separators": (",", ":"), "sort_keys": True}


def ok(data):
    body = {"success": True, "data": data}
    return JsonResponse(body, status=200, json_dumps_params=JSON_PARAMS)


def fail(error_code):
    body = {
        "success": False,
        "error_code": error_code,
        "message": ERROR_MESSAGE[error_code],
    }
    return JsonResponse(
        body, status=ERROR_HTTP[error_code], json_dumps_params=JSON_PARAMS
    )


def get_device(request):
    header = request.headers.get("Authorization", "")
    prefix = "Device "
    if not header.startswith(prefix):
        return None
    token = header[len(prefix):]
    if token == "":
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return Device.objects.filter(token_hash=token_hash).first()


def read_body(request, max_bytes):
    raw = request.body
    if len(raw) > max_bytes:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except ValueError:
        return None
    if type(data) is not dict:
        return None
    return data


def find_logged(device, request_id):
    row = RequestLog.objects.filter(device=device, request_id=request_id).first()
    if row is None:
        return None
    return row.response


def server_error(request):
    return fail("SERVER_ERROR")


def not_found(request, exception):
    return fail("INVALID_PAYLOAD")
