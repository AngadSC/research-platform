from django.urls import path

from labs import admin_views as av
from labs import contributions, dashboard, views

app_name = "labs"
urlpatterns = [
    path("labs/", views.LabListCreateView.as_view(), name="lab-list"),
    path("labs/<uuid:lab_id>/", views.LabDetailView.as_view(), name="lab-detail"),
    path("labs/<uuid:lab_id>/dashboard/", dashboard.DashboardView.as_view(), name="dashboard"),
    path(
        "labs/<uuid:lab_id>/contributions/",
        contributions.ContributionsView.as_view(),
        name="contributions",
    ),
    path("labs/<uuid:lab_id>/members/", views.MemberListView.as_view(), name="member-list"),
    path(
        "labs/<uuid:lab_id>/members/<uuid:membership_id>/",
        views.MemberDetailView.as_view(),
        name="member-detail",
    ),
    path("labs/<uuid:lab_id>/invites/", views.InviteListCreateView.as_view(), name="invite-list"),
    path(
        "labs/<uuid:lab_id>/invites/<uuid:invite_id>/",
        views.InviteDetailView.as_view(),
        name="invite-detail",
    ),
    path(
        "labs/<uuid:lab_id>/institution-resources/",
        av.ResourceListCreateView.as_view(),
        name="resource-list",
    ),
    path(
        "labs/<uuid:lab_id>/institution-resources/<uuid:institutionresource_id>/",
        av.ResourceDetailView.as_view(),
        name="resource-detail",
    ),
    path(
        "labs/<uuid:lab_id>/onboarding-items/",
        av.OnboardingListCreateView.as_view(),
        name="onboarding-list",
    ),
    path(
        "labs/<uuid:lab_id>/onboarding-items/<uuid:onboardingitem_id>/",
        av.OnboardingDetailView.as_view(),
        name="onboarding-detail",
    ),
    path(
        "labs/<uuid:lab_id>/onboarding-items/<uuid:onboardingitem_id>/completions/",
        av.OnboardingCompletionView.as_view(),
        name="onboarding-completion",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/", av.InventoryListCreateView.as_view(), name="inventory-list"
    ),
    path(
        "labs/<uuid:lab_id>/inventory/export/",
        av.InventoryExportView.as_view(),
        name="inventory-export",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/<uuid:inventoryitem_id>/",
        av.InventoryDetailView.as_view(),
        name="inventory-detail",
    ),
    path("invites/preview/", views.InvitePreviewView.as_view(), name="invite-preview"),
    path("invites/accept/", views.InviteAcceptView.as_view(), name="invite-accept"),
]
