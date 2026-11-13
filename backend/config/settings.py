import os
from pathlib import Path
from urllib.parse import unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

# Bien moi truong, Thiet ke backend muc 1.6
SECRET_KEY = os.environ["SECRET_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]
SOURCE1_URL = os.environ["SOURCE1_URL"]
SOURCE2_URL = os.environ["SOURCE2_URL"]
SOURCE2_HMAC_SECRET = os.environ["SOURCE2_HMAC_SECRET"]
SOURCE1_PAY_URL = os.environ["SOURCE1_PAY_URL"]
SOURCE2_PAY_URL = os.environ["SOURCE2_PAY_URL"]
PAY_HMAC_SECRET = os.environ["PAY_HMAC_SECRET"]

DEBUG = False
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "corsheaders",
    "devices",
    "lockers",
    "identity",
    "payments",
    "dashboard",
]

# Khong co CsrfViewMiddleware vi API khong dung cookie (Q21)
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
]

CORS_ALLOW_ALL_ORIGINS = True
APPEND_SLASH = False

ROOT_URLCONF = "config.urls"

# DATABASE_URL dang postgres://user:password@host:port/name (Q22)
db_url = urlparse(DATABASE_URL)
db_port = db_url.port
if db_port is None:
    db_port = 5432
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": db_url.path[1:],
        "USER": unquote(db_url.username or ""),
        "PASSWORD": unquote(db_url.password or ""),
        "HOST": db_url.hostname,
        "PORT": str(db_port),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Thiet ke backend muc 1.1
LANGUAGE_CODE = "vi"
TIME_ZONE = "Asia/Ho_Chi_Minh"
USE_I18N = False
USE_TZ = True

# Hang so, Quy chuan API muc 1.7 va 6.4
UNLOCK_MS = 800
DOOR_TIMEOUT_SEC = 30
WAIT_OPEN_SEC = 30
OPEN_MAX_SEC = 600
LOCK_REST_SEC = 60
PAY_TIMEOUT_SEC = 120
COMMAND_TTL_SEC = 300
REQUEST_LOG_TTL_SEC = 600
EXTERNAL_TIMEOUT_SEC = 1
JWT_TTL_SEC = 28800
