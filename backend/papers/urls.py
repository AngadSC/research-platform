from django.urls import path

from papers import views

app_name = "papers"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(L + "papers/", views.PaperListCreateView.as_view(), name="paper-list"),
    path(L + "papers/doi-lookup/", views.DoiLookupView.as_view(), name="doi-lookup"),
    path(L + "papers/zotero/", views.ZoteroImportView.as_view(), name="zotero-import"),
    path(L + "papers/<uuid:paper_id>/", views.PaperDetailView.as_view(), name="paper-detail"),
    path(L + "papers/<uuid:paper_id>/pdf/", views.PaperPdfView.as_view(), name="paper-pdf"),
    path(
        L + "papers/<uuid:paper_id>/citation/",
        views.PaperCitationView.as_view(),
        name="paper-citation",
    ),
    path(
        L + "papers/<uuid:paper_id>/notes/",
        views.PaperNoteCreateView.as_view(),
        name="paper-notes",
    ),
    path(
        L + "paper-notes/<uuid:papernote_id>/",
        views.PaperNoteDetailView.as_view(),
        name="note-detail",
    ),
]
