from django.urls import path

from documents import views

app_name = "documents"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(
        L + "projects/<uuid:project_id>/documents/",
        views.DocumentListCreateView.as_view(),
        name="document-list",
    ),
    path(
        L + "documents/<uuid:document_id>/",
        views.DocumentDetailView.as_view(),
        name="document-detail",
    ),
    path(
        L + "documents/<uuid:document_id>/revisions/",
        views.RevisionListView.as_view(),
        name="revision-list",
    ),
    path(
        L + "documents/<uuid:document_id>/revisions/<int:version>/",
        views.RevisionDetailView.as_view(),
        name="revision-detail",
    ),
    path(
        L + "documents/<uuid:document_id>/revisions/<int:version>/restore/",
        views.RevisionRestoreView.as_view(),
        name="revision-restore",
    ),
    path(
        L + "projects/<uuid:project_id>/attachments/",
        views.AttachmentListCreateView.as_view(),
        name="attachment-list",
    ),
    path(
        L + "attachments/<uuid:attachment_id>/",
        views.AttachmentDetailView.as_view(),
        name="attachment-detail",
    ),
    path(
        L + "attachments/<uuid:attachment_id>/download/",
        views.AttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
]
