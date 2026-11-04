from django.urls import path

from core.views import (
    HealthView,
    MeView,
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
)

app_name = "core"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("me/", MeView.as_view(), name="me"),
    path(L + "notifications/", NotificationListView.as_view(), name="notification-list"),
    path(
        L + "notifications/read-all/",
        NotificationReadAllView.as_view(),
        name="notification-read-all",
    ),
    path(
        L + "notifications/<uuid:notification_id>/read/",
        NotificationReadView.as_view(),
        name="notification-read",
    ),
]
