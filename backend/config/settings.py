import base64
import hashlib
import os
import secrets
from pathlib import Path

from celery.schedules import crontab
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DEBUG", False)  # D41: fail closed


def _dev_secret_key(path: Path) -> str:
    """D49: one random key per checkout, shared by backend, worker and beat. The key is written
    to a temp file and hard-linked into place, so a reader never sees a half-written key and
    the first writer wins."""
    if not path.exists():
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(secrets.token_urlsafe(64), encoding="utf-8")
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        except OSError:  # file system without hard links (some bind mounts)
            if not path.exists():
                os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
    return path.read_text(encoding="utf-8").strip()


SECRET_KEY = os.environ.get("SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY.startswith(("replace-with", "django-insecure")):
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY must be a real secret when DEBUG is false.")
    SECRET_KEY = _dev_secret_key(
        Path(os.environ.get("DEV_SECRET_KEY_FILE", BASE_DIR / ".dev_secret_key"))
    )

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# Production: https://<domain> so HTTPS POSTs pass Django's Origin check behind Caddy.
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

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
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "rest_framework",
    "drf_spectacular",
    "core",
    "labs",
    "projects",
    "documents",
    "provenance",
    "ethics",
    "audit",
    "integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.UploadSizeLimitMiddleware",
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
            # Parallel test runs pass a distinct TEST_DB_NAME so they don't share test_<db>.
            "TEST": {"NAME": os.environ.get("TEST_DB_NAME") or None},
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# D12: placeholder product name; the frontend mirrors it in src/lib/constants.ts.
PRODUCT_NAME = "Research Workspace"

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
STATIC_ROOT = BASE_DIR / "staticfiles"  # collectstatic target in deploy/Dockerfile.prod

# ARCHITECTURE section 8 / D26: lab files get their own storage alias. It is never served under
# MEDIA_URL or static(); downloads go through the authenticated endpoint only.
LAB_FILES_BUCKET = os.environ.get("LAB_FILES_BUCKET", "")
if LAB_FILES_BUCKET:
    _lab_files = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": LAB_FILES_BUCKET,
            "default_acl": "private",
            "querystring_auth": False,
            "endpoint_url": os.environ.get("LAB_FILES_ENDPOINT_URL") or None,
            "region_name": os.environ.get("LAB_FILES_REGION") or None,
        },
    }
else:
    _lab_files = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": os.environ.get("LAB_FILES_ROOT", "/data/lab_files")},
    }
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "lab_files": _lab_files,
}
ATTACHMENT_MAX_BYTES = 50 * 1024 * 1024
FILE_UPLOAD_HANDLERS = [  # D53: the size cap goes first, before anything spools to disk
    "core.uploads.SizeLimitUploadHandler",
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
INVITES_PER_LAB_PER_DAY = 100  # D50
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# D9/D17: Celery with Valkey, via the redis client.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
# Daily jobs (ARCHITECTURE section 5). Expiry is marked before reminders are sent.
CELERY_BEAT_SCHEDULE = {
    "ethics-mark-expired": {
        "task": "ethics.jobs.mark_expired",
        "schedule": crontab(hour=1, minute=0),
    },
    "ethics-expiry-reminders": {
        "task": "ethics.jobs.send_expiry_reminders",
        "schedule": crontab(hour=1, minute=10),
    },
    "retention-scan": {
        "task": "projects.jobs.retention_scan",
        "schedule": crontab(hour=1, minute=20),
    },
    "integrations-check-links": {
        "task": "integrations.jobs.check_links",
        "schedule": crontab(hour=2, minute=0),
    },
    "integrations-revoke-orphans": {
        "task": "integrations.jobs.revoke_orphans",
        "schedule": crontab(hour=1, minute=30),
    },
}

# D14: dev email goes to the console. Production sets EMAIL_BACKEND to an anymail backend, e.g.
# anymail.backends.postmark.EmailBackend or anymail.backends.amazon_ses.EmailBackend, plus the
# provider's credentials below. No code change is needed to switch provider.
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Research Platform <noreply@localhost>")
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
ANYMAIL = {
    k: v
    for k, v in {
        "POSTMARK_SERVER_TOKEN": os.environ.get("POSTMARK_SERVER_TOKEN"),
        "AMAZON_SES_CLIENT_PARAMS": (
            {"region_name": os.environ["AWS_SES_REGION_NAME"]}
            if os.environ.get("AWS_SES_REGION_NAME")
            else None
        ),
    }.items()
    if v
}

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
    # Google sign-in: failures land here with ?error=...; the SPA passes the same route as its
    # callback_url, so success and pending stages (verify email) land there too.
    "socialaccount_login_error": f"{FRONTEND_URL}/account/provider/callback",
}
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
# Verifying in the same browser session that signed up finishes login (no second password prompt).
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
# D74: sensitive account changes need a recent password/TOTP check; owners get notice emails.
ACCOUNT_REAUTHENTICATION_REQUIRED = True
ACCOUNT_EMAIL_NOTIFICATIONS = True
ACCOUNT_MAX_EMAIL_ADDRESSES = 5
ACCOUNT_RATE_LIMITS = {"manage_email": "5/h/user"}
MFA_SUPPORTED_TYPES = ["totp", "recovery_codes"]

# ARCHITECTURE section 7 / D62: Google sign-in (openid, email, profile only; no Drive scopes).
# Without GOOGLE_CLIENT_ID there is no app, so the headless config lists no Google provider.
SOCIALACCOUNT_ADAPTER = "core.auth.SocialAccountAdapter"
# Link to an existing account by email; core.auth.SocialAccountAdapter only matches verified ones.
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["openid", "email", "profile"],
        "AUTH_PARAMS": {"access_type": "online"},
        "APPS": (
            [{"client_id": GOOGLE_CLIENT_ID, "secret": os.environ.get("GOOGLE_CLIENT_SECRET", "")}]
            if GOOGLE_CLIENT_ID
            else []
        ),
    }
}

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
    "DEFAULT_THROTTLE_RATES": {
        "invites": "30/hour",
        "uploads": "60/hour",
        "lab_create": "5/day",
        "picker_token": "30/hour",
        "link_check": "60/hour",
    },
    "DEFAULT_PERMISSION_CLASSES": ["core.permissions.HasPerm"],
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.auth.SessionAuthentication"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": f"{PRODUCT_NAME} API",
    "VERSION": "0.1.0",
    # Stable enum names: same-named choice fields would otherwise get hash-suffixed names.
    "ENUM_NAME_OVERRIDES": {
        "LabRoleEnum": "labs.models.LabRole",
        "ProjectRoleEnum": "projects.models.ProjectRole",
        "ProjectStatusEnum": "projects.models.ProjectStatus",
        "TaskStatusEnum": "projects.models.TaskStatus",
        "ManuscriptStatusEnum": "provenance.models.ManuscriptStatus",
        "LineageKindEnum": "provenance.models.LineageKind",
        "ApprovalStatusEnum": "ethics.models.ApprovalStatus",
        "NotificationKindEnum": "core.models.NotificationKind",
    },
}

# ARCHITECTURE §4: X-Forwarded-For is trusted only behind this many proxies.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))

# ARCHITECTURE section 9 / D63: integration tokens are Fernet-encrypted with these keys, newest
# first (comma-separated). In DEBUG a missing value means a random dev key derived from the
# git-ignored backend/.dev_integration_key (the D49 pattern); outside DEBUG startup refuses.
INTEGRATION_ENCRYPTION_KEYS = env_list("INTEGRATION_ENCRYPTION_KEYS")
if not INTEGRATION_ENCRYPTION_KEYS:
    if not DEBUG:
        raise ImproperlyConfigured("INTEGRATION_ENCRYPTION_KEYS must be set when DEBUG is false.")
    _seed = _dev_secret_key(
        Path(os.environ.get("DEV_INTEGRATION_KEY_FILE", BASE_DIR / ".dev_integration_key"))
    )
    INTEGRATION_ENCRYPTION_KEYS = [
        base64.urlsafe_b64encode(hashlib.sha256(_seed.encode()).digest()).decode()
    ]
# D65: one OAuth callback for every integration provider, under /api/ so the Vite proxy covers it.
# Django only hides `sensitive_variables` on 500 pages when DEBUG is off. Keep them hidden always,
# so a token in a frame never shows up in a debug page.
DEFAULT_EXCEPTION_REPORTER_FILTER = "integrations.debug.AlwaysCleanse"
INTEGRATION_OAUTH_REDIRECT_URI = f"{FRONTEND_URL}/api/integrations/oauth/callback/"
# D66: integration OAuth clients are separate from the Google sign-in client.
INTEGRATION_CLIENTS = {
    "google_drive": {
        "client_id": os.environ.get("GOOGLE_DRIVE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_DRIVE_CLIENT_SECRET", ""),
    },
}
# Public by design (the browser Picker needs them): API key and Cloud project number (app id).
INTEGRATION_PUBLIC = {
    "google_drive": {
        "api_key": os.environ.get("GOOGLE_DRIVE_API_KEY", ""),
        "app_id": os.environ.get("GOOGLE_DRIVE_APP_ID", ""),
    },
}
