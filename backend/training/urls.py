from django.urls import path

from training import views

app_name = "training"
L = "labs/<uuid:lab_id>/training/"
urlpatterns = [
    path(L + "requirements/", views.RequirementListCreateView.as_view(), name="requirement-list"),
    path(
        L + "requirements/<uuid:trainingrequirement_id>/",
        views.RequirementDetailView.as_view(),
        name="requirement-detail",
    ),
    path(L + "records/", views.RecordListCreateView.as_view(), name="record-list"),
    path(
        L + "records/<uuid:trainingrecord_id>/",
        views.RecordDetailView.as_view(),
        name="record-detail",
    ),
    path(
        L + "records/<uuid:trainingrecord_id>/verify/",
        views.RecordVerifyView.as_view(),
        name="record-verify",
    ),
    path(
        L + "records/<uuid:trainingrecord_id>/certificate/",
        views.RecordCertificateView.as_view(),
        name="record-certificate",
    ),
    path(L + "compliance/", views.ComplianceView.as_view(), name="compliance"),
    path(L + "my/", views.MyTrainingView.as_view(), name="my-training"),
    path(L + "expiring/", views.ExpiringView.as_view(), name="expiring"),
]
