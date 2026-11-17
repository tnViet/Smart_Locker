# JWT cho dashboard: HS256, khoa JWT_SECRET, han 8 gio (BE 1.2, API 3.4)
from datetime import timedelta

import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone


def role_of(user):
    # Quyen lay tu group. admin uu tien hon viewer. Khong thuoc group nao thi tra ""
    names = []
    for group in user.groups.all():
        names.append(group.name)
    if "admin" in names:
        return "admin"
    if "viewer" in names:
        return "viewer"
    return ""


def make_token(user, now):
    payload = {
        "sub": str(user.id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.JWT_TTL_SEC)).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")


def check_token(request, need_admin):
    # Tra (user, role, error_code). error_code rong khi hop le.
    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return None, "", "UNAUTHORIZED"
    token = header[len(prefix):]
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=["HS256"],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None, "", "UNAUTHORIZED"

    try:
        user_id = int(payload["sub"])
    except (TypeError, ValueError):
        return None, "", "UNAUTHORIZED"
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is None:
        return None, "", "UNAUTHORIZED"

    # Doc lai group moi lan goi de go quyen co hieu luc ngay
    role = role_of(user)
    if role == "":
        return None, "", "FORBIDDEN"
    if need_admin and role != "admin":
        return None, "", "FORBIDDEN"
    return user, role, ""
