from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("_allauth/", include("allauth.headless.urls")),
    path("api/", include("core.urls")),
    path("api/", include("labs.urls")),
    path("api/", include("audit.urls")),
    # --- projects/tasks (Phase 3) ---
    path("api/", include("projects.urls")),
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3) ---
    path("api/", include("documents.urls")),
    # --- end documents/attachments (Phase 3) ---
]

if settings.DEBUG:  # ARCHITECTURE section 6 / D41: schema and Django admin only in dev
    urlpatterns.append(path("admin/", admin.site.urls))
    from drf_spectacular.views import SpectacularAPIView

    urlpatterns.append(path("api/schema/", SpectacularAPIView.as_view(), name="schema"))
