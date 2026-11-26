from django.urls import path

from samples import views

app_name = "samples"
S = "labs/<uuid:lab_id>/samples/"
T = "labs/<uuid:lab_id>/storage/"
urlpatterns = [
    path(S, views.SampleListCreateView.as_view(), name="sample-list"),
    path(S + "next-codes/", views.NextCodesView.as_view(), name="next-codes"),
    path(S + "export/", views.SampleExportView.as_view(), name="sample-export"),
    path(S + "import/", views.SampleImportView.as_view(), name="sample-import"),
    path(S + "<uuid:sample_id>/", views.SampleDetailView.as_view(), name="sample-detail"),
    path(S + "<uuid:sample_id>/files/", views.SampleFilesView.as_view(), name="sample-files"),
    path(
        S + "<uuid:sample_id>/files/<uuid:samplefile_id>/",
        views.SampleFileView.as_view(),
        name="sample-file",
    ),
    path(T, views.UnitListCreateView.as_view(), name="unit-list"),
    path(T + "<uuid:storageunit_id>/", views.UnitDetailView.as_view(), name="unit-detail"),
    path(T + "boxes/", views.BoxCreateView.as_view(), name="box-list"),
    path(T + "boxes/<uuid:storagebox_id>/", views.BoxDetailView.as_view(), name="box-detail"),
    path(T + "tubes/", views.TubeCreateView.as_view(), name="tube-list"),
    path(T + "tubes/<uuid:tube_id>/", views.TubeDetailView.as_view(), name="tube-detail"),
]
