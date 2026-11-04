import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)  # D41: fail closed

if DEBUG:
    SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-dev-only")
else:
    SECRET_KEY = os.environ.get("SECRET_KEY", "")
    if not SECRET_KEY or SECRET_KEY.startswith(("replace-with", "django-insecure")):
        raise ImproperlyConfigured("SECRET_KEY must be a real secret when DEBUG is false.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "allauth",
    "allauth.account",
    "allauth.headless",
    "allauth.mfa",
    "rest_framework",
    "drf_spectacular",
    "core",
    "labs",
    "projects",
    "documents",
    "provenance",
    "ethics",
    "audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# D15: Postgres when POSTGRES_HOST is set, SQLite otherwise.
if os.environ.get("POSTGRES_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("POSTGRES_DB", "research"),
            "USER": os.environ.get("POSTGRES_USER", "research"),
            "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
            "HOST": os.environ["POSTGRES_HOST"],
            "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# D16: custom user model.
AUTH_USER_MODEL = "core.User"

# D8: Argon2 first, then Django's PBKDF2 hashers as fallback.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# D9/D17: Celery with Valkey, via the redis client.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")

# D14: dev email goes to the console.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", True)
    CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", True)
    SECURE_HSTS_SECONDS = int(os.environ.get("SECURE_HSTS_SECONDS", "0"))
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)

# D37: email links point at the SPA.
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# ARCHITECTURE section 7 / D6: allauth headless (session cookies) with email login.
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
ACCOUNT_ADAPTER = "core.auth.AccountAdapter"
HEADLESS_ADAPTER = "core.auth.HeadlessAdapter"
HEADLESS_ONLY = True
HEADLESS_CLIENTS = ("browser",)
HEADLESS_FRONTEND_URLS = {
    "account_confirm_email": f"{FRONTEND_URL}/account/verify-email/{{key}}",
    "account_reset_password": f"{FRONTEND_URL}/account/password/reset",
    "account_reset_password_from_key": f"{FRONTEND_URL}/account/password/reset/key/{{key}}",
    "account_signup": f"{FRONTEND_URL}/account/signup",
}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Verifying in the same browser session that signed up finishes login (no second password prompt).
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]

SESSION_COOKIE_AGE = 7 * 24 * 3600
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

# D41: shared cache (Valkey) so allauth and DRF throttles count across processes.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("CACHE_URL", "redis://valkey:6379/1"),
    }
}

REST_FRAMEWORK = {
    "DEFAULT_THROTTLE_RATES": {"invites": "30/hour"},
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.HasPerm"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.auth.SessionAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Research Workspace API",
    "VERSION": "0.1.0",
}

# ARCHITECTURE §4: X-Forwarded-For is trusted only behind this many proxies.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
