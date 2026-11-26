from django.urls import path

from instruments import views as v

app_name = "instruments"

L = "labs/<uuid:lab_id>"
urlpatterns = [
    path("instrument-software/", v.SoftwareChoicesView.as_view(), name="software"),
    path(f"{L}/instrument-files/", v.InstrumentFileListView.as_view(), name="file-list"),
    path(
        f"{L}/instrument-files/<uuid:instrumentfile_id>/",
        v.InstrumentFileDetailView.as_view(),
        name="file-detail",
    ),
    path(
        f"{L}/projects/<uuid:project_id>/instruments/<uuid:inventoryitem_id>/files/",
        v.DropFileView.as_view(),
        name="drop-file",
    ),
    path(
        f"{L}/instruments/<uuid:inventoryitem_id>/drop-links/",
        v.DropLinkListCreateView.as_view(),
        name="link-list",
    ),
    path(
        f"{L}/instrument-drop-links/<uuid:instrumentdroplink_id>/",
        v.DropLinkDetailView.as_view(),
        name="link-detail",
    ),
    # Public: the token (query string, or the form for an upload) is the only credential.
    path("instrument-drop/", v.PublicDropView.as_view(), name="drop"),
]
