from django.urls import path

from core.views import (
    HealthView,
    LoginMethodsView,
    MeView,
    MyAvatarView,
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
    SearchView,
    UserAvatarView,
)

app_name = "core"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", MyAvatarView.as_view(), name="me-avatar"),
    path("users/<uuid:user_id>/avatar/", UserAvatarView.as_view(), name="user-avatar"),
    path("auth/login-methods/", LoginMethodsView.as_view(), name="login-methods"),
    path(L + "search/", SearchView.as_view(), name="search"),
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
