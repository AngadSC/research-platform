from django.urls import path

from core.views import HealthView, MeView

app_name = "core"
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("me/", MeView.as_view(), name="me"),
]
