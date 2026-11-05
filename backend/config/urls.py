from django.conf import settings
from django.contrib import admin
from django.http import HttpResponseNotFound
from django.urls import include, path

from core.auth import VerifyEmailView
from core.healthz import healthz

urlpatterns = [
    # Plain Django view outside /api/, unauthenticated (deploy/Caddyfile, Dockerfile HEALTHCHECK).
    path("healthz", healthz),
    # D72: our verify view first, so it wins over allauth's own route of the same path.
    path("_allauth/browser/v1/auth/email/verify", VerifyEmailView.as_api_view(client="browser")),
    path("_allauth/", include("allauth.headless.urls")),
    # Provider callbacks only (HEADLESS_ONLY), e.g. /accounts/google/login/callback/.
    # D73: the One Tap token endpoint is unused; answer 404 before allauth's route can match.
    path("accounts/google/login/token/", lambda request: HttpResponseNotFound()),
    path("accounts/", include("allauth.urls")),
    path("api/", include("core.urls")),
    path("api/", include("labs.urls")),
    path("api/", include("audit.urls")),
    # --- projects/tasks (Phase 3) ---
    path("api/", include("projects.urls")),
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3) ---
    path("api/", include("documents.urls")),
    # --- end documents/attachments (Phase 3) ---
    # --- provenance (Phase 4) ---
    path("api/", include("provenance.urls")),
    # --- end provenance (Phase 4) ---
    # --- ethics (Phase 5) ---
    path("api/", include("ethics.urls")),
    # --- end ethics (Phase 5) ---
    path("api/", include("integrations.urls")),
]

if settings.DEBUG:  # ARCHITECTURE section 6 / D41: schema and Django admin only in dev
    urlpatterns.append(path("admin/", admin.site.urls))
    from drf_spectacular.views import SpectacularAPIView

    urlpatterns.append(path("api/schema/", SpectacularAPIView.as_view(), name="schema"))
