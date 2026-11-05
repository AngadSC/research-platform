from django.urls import path

from provenance import views

app_name = "provenance"
_P = "labs/<uuid:lab_id>/projects/<uuid:project_id>/"
_L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(_P + "datasets/", views.DatasetListCreateView.as_view(), name="dataset-list"),
    path(
        _L + "datasets/<uuid:datasetrecord_id>/",
        views.DatasetDetailView.as_view(),
        name="dataset-detail",
    ),
    path(_P + "analyses/", views.AnalysisListCreateView.as_view(), name="analysis-list"),
    path(
        _L + "analyses/<uuid:analysis_id>/",
        views.AnalysisDetailView.as_view(),
        name="analysis-detail",
    ),
    path(_P + "results/", views.ResultListCreateView.as_view(), name="result-list"),
    path(_L + "results/<uuid:result_id>/", views.ResultDetailView.as_view(), name="result-detail"),
    path(_P + "decisions/", views.DecisionListCreateView.as_view(), name="decision-list"),
    path(
        _L + "decisions/<uuid:decision_id>/",
        views.DecisionDetailView.as_view(),
        name="decision-detail",
    ),
    path(_P + "manuscripts/", views.ManuscriptListCreateView.as_view(), name="manuscript-list"),
    path(
        _L + "manuscripts/<uuid:manuscriptlink_id>/",
        views.ManuscriptDetailView.as_view(),
        name="manuscript-detail",
    ),
    path(_P + "funding/", views.FundingListCreateView.as_view(), name="funding-list"),
    path(
        _L + "funding/<uuid:fundingrecord_id>/",
        views.FundingDetailView.as_view(),
        name="funding-detail",
    ),
    path(_P + "review-items/", views.ReviewListCreateView.as_view(), name="review-list"),
    path(
        _L + "review-items/<uuid:reviewitem_id>/",
        views.ReviewDetailView.as_view(),
        name="review-detail",
    ),
    path(
        _P + "recruitment-entries/",
        views.RecruitmentListCreateView.as_view(),
        name="recruitment-list",
    ),
    path(
        _L + "recruitment-entries/<uuid:recruitmententry_id>/",
        views.RecruitmentDetailView.as_view(),
        name="recruitment-detail",
    ),
    path(_P + "recruitment-plan/", views.RecruitmentPlanView.as_view(), name="recruitment-plan"),
    path(_P + "lineage/", views.LineageView.as_view(), name="lineage"),
    path(_P + "export/", views.ExportView.as_view(), name="export"),
]
