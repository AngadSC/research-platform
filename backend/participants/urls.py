from django.urls import path

from participants import views

app_name = "participants"
_P = "labs/<uuid:lab_id>/projects/<uuid:project_id>/"
_L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(_P + "participants/", views.ParticipantListCreateView.as_view(), name="participant-list"),
    path(
        _P + "participants/<uuid:participant_id>/",
        views.ParticipantDetailView.as_view(),
        name="participant-detail",
    ),
    path(
        _P + "participants/<uuid:participant_id>/archive/",
        views.ParticipantArchiveView.as_view(),
        name="participant-archive",
    ),
    path(
        _P + "participants/<uuid:participant_id>/restore/",
        views.ParticipantRestoreView.as_view(),
        name="participant-restore",
    ),
    path(
        _P + "participants/<uuid:participant_id>/events/",
        views.ParticipantEventsView.as_view(),
        name="participant-events",
    ),
    path(
        _P + "participants/<uuid:participant_id>/cells/<uuid:component_id>/",
        views.CellSetView.as_view(),
        name="cell-set",
    ),
    path(
        _P + "participant-components/",
        views.ComponentListCreateView.as_view(),
        name="component-list",
    ),
    path(
        _P + "participant-components/<uuid:component_id>/",
        views.ComponentDetailView.as_view(),
        name="component-detail",
    ),
    path(_P + "participant-cells/", views.CellListView.as_view(), name="cell-list"),
    path(
        _P + "participant-cells/<uuid:cell_id>/files/",
        views.CellFileCreateView.as_view(),
        name="cell-files",
    ),
    path(
        _P + "participant-files/<uuid:file_id>/", views.FileDetailView.as_view(), name="file-detail"
    ),
    path(_L + "participant-reasons/", views.ReasonListCreateView.as_view(), name="reason-list"),
    path(
        _L + "participant-reasons/<uuid:reason_id>/",
        views.ReasonDetailView.as_view(),
        name="reason-detail",
    ),
    path(_P + "participant-imports/", views.ImportListCreateView.as_view(), name="import-list"),
    path(
        _P + "participant-imports/preview/",
        views.ImportPreviewView.as_view(),
        name="import-preview",
    ),
    path(
        _P + "participant-imports/<uuid:run_id>/undo/",
        views.ImportUndoView.as_view(),
        name="import-undo",
    ),
    path(_P + "participant-file-matches/", views.MatchFilesView.as_view(), name="files-match"),
    path(
        _P + "participant-file-matches/attach/",
        views.AttachFilesView.as_view(),
        name="files-attach",
    ),
    path(_P + "participant-link-health/", views.LinkHealthView.as_view(), name="link-health"),
    path(
        _P + "participant-link-health/refresh/",
        views.LinkRefreshView.as_view(),
        name="link-refresh",
    ),
    path(_P + "participant-tasks/", views.TaskGapsView.as_view(), name="gap-tasks"),
    path(_L + "participant-overview/", views.LabOverviewView.as_view(), name="lab-overview"),
    path(_P + "participant-rules/", views.RuleListCreateView.as_view(), name="rule-list"),
    path(
        _P + "participant-rules/<uuid:rule_id>/", views.RuleDetailView.as_view(), name="rule-detail"
    ),
    path(
        _P + "participant-rules/<uuid:rule_id>/evaluate/",
        views.RuleEvaluateView.as_view(),
        name="rule-evaluate",
    ),
    path(_P + "analysis-sets/", views.SetListCreateView.as_view(), name="set-list"),
    path(_P + "analysis-sets/<uuid:set_id>/", views.SetDetailView.as_view(), name="set-detail"),
    path(
        _P + "analysis-sets/<uuid:set_id>/new-version/",
        views.SetNewVersionView.as_view(),
        name="set-new-version",
    ),
    path(_P + "participant-flow/", views.FlowView.as_view(), name="flow"),
    path(_P + "participant-flow/export/", views.FlowExportView.as_view(), name="flow-export"),
    path(_P + "participant-rules/preview/", views.RulePreviewView.as_view(), name="rule-preview"),
]
