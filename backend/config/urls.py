from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("_allauth/", include("allauth.headless.urls")),
    path("api/", include("core.urls")),
    path("api/", include("labs.urls")),
    path("api/", include("audit.urls")),
]

if settings.DEBUG:  # ARCHITECTURE section 6: schema only in dev
    from drf_spectacular.views import SpectacularAPIView

    urlpatterns.append(path("api/schema/", SpectacularAPIView.as_view(), name="schema"))
