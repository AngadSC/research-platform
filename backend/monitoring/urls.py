from django.urls import path

from monitoring import views

app_name = "monitoring"
L = "labs/<uuid:lab_id>/sensors/"
urlpatterns = [
    path(L, views.SensorListView.as_view(), name="sensor-list"),
    path(L + "<uuid:sensor_id>/", views.SensorDetailView.as_view(), name="sensor-detail"),
    path(L + "<uuid:sensor_id>/token/", views.SensorTokenView.as_view(), name="sensor-token"),
    path(
        L + "<uuid:sensor_id>/test-reading/",
        views.SensorTestReadingView.as_view(),
        name="sensor-test-reading",
    ),
    path(
        L + "alerts/<uuid:sensoralert_id>/acknowledge/",
        views.AlertAcknowledgeView.as_view(),
        name="alert-acknowledge",
    ),
    # A device's own address: its token is the only credential (views.IngestView).
    path("sensors/ingest/", views.IngestView.as_view(), name="sensor-ingest"),
]
