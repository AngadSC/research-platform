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
    path(L + "lab-documents/", views.LabDocumentListCreateView.as_view(), name="lab-document-list"),
    path(
        L + "documents/<uuid:document_id>/",
        views.DocumentDetailView.as_view(),
        name="document-detail",
    ),
    path(
        L + "documents/<uuid:document_id>/move/",
        views.DocumentMoveView.as_view(),
        name="document-move",
    ),
    path(
        L + "projects/<uuid:project_id>/folders/",
        views.FolderListCreateView.as_view(),
        name="folder-list",
    ),
    path(
        L + "folders/<uuid:folder_id>/",
        views.FolderDetailView.as_view(),
        name="folder-detail",
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
        L + "attachments/<uuid:attachment_id>/move/",
        views.AttachmentMoveView.as_view(),
        name="attachment-move",
    ),
    path(
        L + "attachments/<uuid:attachment_id>/edit-in-google/",
        views.AttachmentEditInGoogleView.as_view(),
        name="attachment-edit-in-google",
    ),
    path(
        L + "attachments/<uuid:attachment_id>/download/",
        views.AttachmentDownloadView.as_view(),
        name="attachment-download",
    ),
]
