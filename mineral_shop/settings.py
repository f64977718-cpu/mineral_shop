"""Налаштування проєкту «Кам'яна Грань». Усі секрети беруться з .env / змінних середовища."""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    return os.environ.get(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


# ---------- Базові ----------
DEBUG = env_bool("DJANGO_DEBUG", True)
_DEV_KEY = "django-insecure-dev-only-change-me"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", _DEV_KEY)
if not DEBUG and SECRET_KEY == _DEV_KEY:
    raise ImproperlyConfigured("Задайте DJANGO_SECRET_KEY у .env для продакшну.")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    if env_bool("BEHIND_PROXY"):
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'store',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'store.middleware.AdminAccessLogMiddleware',  # пише візити адмінів у БД
]

ROOT_URLCONF = 'mineral_shop.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'store.context_processors.cart',
            ],
        },
    },
]

WSGI_APPLICATION = 'mineral_shop.wsgi.application'

# ---------- База даних ----------
# 1) DATABASE_URL (повний рядок) або 2) окремі DB_* змінні (зручно для Aiven) або 3) SQLite.
DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST")

if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, ssl_require=True)}
elif DB_HOST:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "defaultdb"),
            "USER": os.environ.get("DB_USER", "avnadmin"),
            "PASSWORD": os.environ.get("DB_PASSWORD", ""),
            "HOST": DB_HOST,
            "PORT": os.environ.get("DB_PORT", "5432"),
            "CONN_MAX_AGE": 600,
            "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "require")},
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

_root_cert = os.environ.get("DB_SSLROOTCERT")
if _root_cert and DATABASES["default"]["ENGINE"].endswith("postgresql"):
    cert_path = Path(_root_cert)
    if not cert_path.is_absolute():
        cert_path = BASE_DIR / cert_path
    _opts = DATABASES["default"].setdefault("OPTIONS", {})
    _opts["sslrootcert"] = str(cert_path)
    # З сертифікатом перевіряємо справжність сервера (verify-ca), а не лише шифруємо (require)
    if _opts.get("sslmode", "require") == "require":
        _opts["sslmode"] = "verify-ca"

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'uk'
TIME_ZONE = 'Europe/Kyiv'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

CART_SESSION_ID = 'cart'

# ---------- Оплата ----------
SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
# stripe | liqpay | mock (mock — лише для розробки, при DEBUG=True)
PAYMENT_PROVIDER = os.environ.get("PAYMENT_PROVIDER", "mock" if DEBUG else "").lower()
PAYMENT_CURRENCY = os.environ.get("PAYMENT_CURRENCY", "UAH").upper()
PAYMENT_PENDING_TTL_MINUTES = int(os.environ.get("PAYMENT_PENDING_TTL_MINUTES", "90"))

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

LIQPAY_PUBLIC_KEY = os.environ.get("LIQPAY_PUBLIC_KEY", "")
LIQPAY_PRIVATE_KEY = os.environ.get("LIQPAY_PRIVATE_KEY", "")
LIQPAY_SANDBOX = env_bool("LIQPAY_SANDBOX", False)

# Довіряти X-Forwarded-For для визначення IP (лише якщо сайт за nginx/балансувальником)
USE_X_FORWARDED_FOR = env_bool("USE_X_FORWARDED_FOR", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"store.payments": {"handlers": ["console"], "level": "INFO"}},
}
