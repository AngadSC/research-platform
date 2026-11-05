import base64
import hashlib
import os
import re
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
    "allauth.socialaccount.providers.saml",  # D152: apps come from core.InstitutionSSO
    "rest_framework",
    "drf_spectacular",
    "core",
    "labs",
    "projects",
    "documents",
    "provenance",
    "ethics",
    "training",
    "audit",
    "integrations",
    "assistant",  # Run 5, D160: AI tool layer and MCP server
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.UploadSizeLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "projects.activity.ActivityMiddleware",
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
        "BACKEND": "documents.storage.LabFilesS3Storage",  # D123: forced-download metadata
        "OPTIONS": {
            "bucket_name": LAB_FILES_BUCKET,
            "default_acl": "private",
            "querystring_auth": True,  # D90: url() signs; only the download view calls it
            "signature_version": "s3v4",
            "endpoint_url": os.environ.get("LAB_FILES_ENDPOINT_URL") or None,
            "region_name": os.environ.get("LAB_FILES_REGION") or None,
        },
    }
else:
    _lab_files = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": os.environ.get("LAB_FILES_ROOT", "/data/lab_files")},
    }
# D90, D123: with a bucket, forced-attachment downloads redirect to a presigned GET (60 s at
# most); PDFs, shown inline, always stream through Django.
# Set LAB_FILES_STREAM_DOWNLOADS=True for providers that ignore response-* overrides.
LAB_FILES_STREAM_DOWNLOADS = os.environ.get("LAB_FILES_STREAM_DOWNLOADS", "").lower() in {
    "1",
    "true",
}
LAB_FILES_PRESIGN_SECONDS = 60
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
        "task": "integrations.jobs.check_links_by_lab",
        "schedule": crontab(hour=2, minute=0),
    },
    "training-expiry-reminders": {  # D178
        "task": "training.jobs.send_expiry_reminders",
        "schedule": crontab(hour=1, minute=40),
    },
    "training-weekly-digest": {
        "task": "training.jobs.send_weekly_digest",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
    "assistant-prune-clients": {  # D200
        "task": "assistant.jobs.prune_unused_clients",
        "schedule": crontab(hour=3, minute=0),
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
        "search": "120/minute",
        "integration_connect": "30/hour",  # D81: each API-key connect calls the provider
        "integration_search": "30/minute",  # D85
        "login_methods": "60/minute",  # D156, per IP
        "ai_token": "20/hour",  # D164: personal access tokens created
        "ai_key": "20/hour",  # D187: each key save makes one provider call
        "ai_chat": "240/hour",  # D190: messages and approvals to the in-app assistant
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
        "AiGrantKindEnum": "assistant.models.GrantKind",  # D164
        "AiAccessEnum": "assistant.models.Access",
        "TrainingCategoryEnum": "training.models.TrainingCategory",  # Run 5
        "TrainingAppliesToEnum": "training.models.AppliesTo",
        "ComplianceStatusEnum": "training.models.ComplianceStatus",
    },
}

# ARCHITECTURE §4: X-Forwarded-For is trusted only behind this many proxies.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "0"))
# D155: behind Caddy (which sets X-Forwarded-Proto itself) requests are https. SAML builds the ACS
# URL and checks the response Destination from the request, so this must be right.
if TRUSTED_PROXY_COUNT:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

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
# D87: any other OAuth provider is configured by convention, with no settings change:
# INTEGRATION_<NAME>_CLIENT_ID / INTEGRATION_<NAME>_CLIENT_SECRET (NAME = registry key, upper case).
for _var, _value in os.environ.items():
    _m = re.fullmatch(r"INTEGRATION_([A-Z0-9_]+)_CLIENT_ID", _var)
    if _m and _m[1].lower() not in INTEGRATION_CLIENTS:
        INTEGRATION_CLIENTS[_m[1].lower()] = {
            "client_id": _value,
            "client_secret": os.environ.get(f"INTEGRATION_{_m[1]}_CLIENT_SECRET", ""),
        }
# D82: when set, self-hosted instance URLs (REDCap, GitLab, ...) must be on one of these hosts
# (comma-separated; `*.uni.edu` allows any subdomain). Empty: any public https host.
INTEGRATION_ALLOWED_INSTANCE_HOSTS = env_list("INTEGRATION_ALLOWED_INSTANCE_HOSTS")
# D120: outbound call limits (seconds / bytes). One request, connect to last body byte, may take
# INTEGRATION_HTTP_DEADLINE; a whole interactive endpoint INTEGRATION_ENDPOINT_BUDGET; in the
# daily job one request INTEGRATION_JOB_HTTP_DEADLINE, one link INTEGRATION_JOB_LINK_BUDGET and
# one lab INTEGRATION_JOB_LAB_BUDGET (under the Celery soft limit in integrations/jobs.py).
INTEGRATION_HTTP_DEADLINE = float(os.environ.get("INTEGRATION_HTTP_DEADLINE", "15"))
INTEGRATION_ENDPOINT_BUDGET = float(os.environ.get("INTEGRATION_ENDPOINT_BUDGET", "25"))
INTEGRATION_HTTP_MAX_BYTES = int(os.environ.get("INTEGRATION_HTTP_MAX_BYTES", str(2 * 1024 * 1024)))
INTEGRATION_JOB_HTTP_DEADLINE = float(os.environ.get("INTEGRATION_JOB_HTTP_DEADLINE", "30"))
INTEGRATION_JOB_LINK_BUDGET = float(os.environ.get("INTEGRATION_JOB_LINK_BUDGET", "60"))
INTEGRATION_JOB_LAB_BUDGET = float(os.environ.get("INTEGRATION_JOB_LAB_BUDGET", "900"))
# Public by design (the browser Picker needs them): API key and Cloud project number (app id).
INTEGRATION_PUBLIC = {
    "google_drive": {
        "api_key": os.environ.get("GOOGLE_DRIVE_API_KEY", ""),
        "app_id": os.environ.get("GOOGLE_DRIVE_APP_ID", ""),
    },
}

# Run 5, D160-D169: remote MCP server and its OAuth 2.1 authorization server (assistant app).
# MCP_BASE_URL is the public https origin Claude/ChatGPT reach (the issuer); the MCP endpoint is
# MCP_BASE_URL + "/mcp". Defaults to FRONTEND_URL because the SPA origin proxies /mcp, /.well-known
# and /api to Django (Vite in dev, Caddy in production).
MCP_BASE_URL = os.environ.get("MCP_BASE_URL", FRONTEND_URL).rstrip("/")
# D193: the exact https redirect URIs an AI app may use (dynamic registration and CIMD alike).
# `*` in the last path segment matches one id-like segment (ChatGPT's per-connector callback).
# Sources: Claude's connector docs (claude.com/docs/connectors/building/authentication) and
# support article 11503834 (the claude.com variant); OpenAI's plugins auth guide
# (developers.openai.com/plugins/build/auth: stable URI and per-callback URI). UNVERIFIED against
# live traffic: confirm before production. Loopback http://localhost, 127.0.0.1 or [::1] on any
# port is always allowed (RFC 8252, Claude Code).
MCP_ALLOWED_REDIRECT_URIS = env_list(
    "MCP_ALLOWED_REDIRECT_URIS",
    "https://claude.ai/api/mcp/auth_callback,"
    "https://claude.com/api/mcp/auth_callback,"
    "https://chatgpt.com/connector_platform_oauth_redirect,"
    "https://chatgpt.com/connector/oauth/*",
)
# D165: hosts whose Client ID Metadata Documents we fetch (SSRF-pinned, integrations/http.py).
MCP_CIMD_HOSTS = env_list("MCP_CIMD_HOSTS", "claude.ai,claude.com,chatgpt.com")
# D196: in-app assistant streams hold one gunicorn thread each (3 workers x 8 threads = 24 in
# deploy/docker-compose.prod.yml). At most ASSISTANT_MAX_STREAMS run at once on the whole server,
# so ordinary requests always find a thread. A stream is stopped after ASSISTANT_STREAM_DEADLINE
# seconds in total; its cache slots live ASSISTANT_LOCK_TTL seconds and are refreshed by a
# heartbeat while it runs. Keep DEADLINE + the provider read timeout (120) below LOCK_TTL, and
# MAX_STREAMS well below workers x threads.
ASSISTANT_MAX_STREAMS = int(os.environ.get("ASSISTANT_MAX_STREAMS", "10"))
ASSISTANT_STREAM_DEADLINE = int(os.environ.get("ASSISTANT_STREAM_DEADLINE", "300"))
ASSISTANT_LOCK_TTL = int(os.environ.get("ASSISTANT_LOCK_TTL", "600"))
# D166: browser origins allowed to call /mcp besides MCP_BASE_URL's (DNS-rebinding check).
MCP_ALLOWED_ORIGINS = env_list("MCP_ALLOWED_ORIGINS")
