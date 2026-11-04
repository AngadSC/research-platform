from django.urls import path

from audit import views

app_name = "audit"
urlpatterns = [
    path(
        "labs/<uuid:lab_id>/audit-events/",
        views.AuditEventListView.as_view(),
        name="audit-event-list",
    ),
]
