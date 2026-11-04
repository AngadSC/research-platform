from django.urls import path

from ethics import views

app_name = "ethics"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(L + "ethics-approvals/", views.ApprovalListCreateView.as_view(), name="approval-list"),
    path(
        L + "ethics-approvals/<uuid:ethicsapproval_id>/",
        views.ApprovalDetailView.as_view(),
        name="approval-detail",
    ),
    path(
        L + "ethics-approvals/<uuid:ethicsapproval_id>/attachments/",
        views.ApprovalAttachmentUploadView.as_view(),
        name="approval-attachments",
    ),
]
