from django.urls import path

from core.page_comments import PageCommentDetailView, PageCommentListCreateView
from core.usage import UsageView
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
    WeatherView,
)

app_name = "core"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("me/", MeView.as_view(), name="me"),
    path("me/avatar/", MyAvatarView.as_view(), name="me-avatar"),
    path("users/<uuid:user_id>/avatar/", UserAvatarView.as_view(), name="user-avatar"),
    path("weather/", WeatherView.as_view(), name="weather"),
    path("usage/", UsageView.as_view(), name="usage"),  # D379, site staff only
    path("auth/login-methods/", LoginMethodsView.as_view(), name="login-methods"),
    path(L + "search/", SearchView.as_view(), name="search"),
    path(L + "page-comments/", PageCommentListCreateView.as_view(), name="page-comment-list"),
    path(
        L + "page-comments/<uuid:page_comment_id>/",
        PageCommentDetailView.as_view(),
        name="page-comment-detail",
    ),
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
