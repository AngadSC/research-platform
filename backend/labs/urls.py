from django.urls import path

from labs import admin_views as av
from labs import contributions, dashboard, lab_calendar, protocols, views

app_name = "labs"
urlpatterns = [
    path("labs/", views.LabListCreateView.as_view(), name="lab-list"),
    path("institutions/search/", views.InstitutionSearchView.as_view(), name="institution-search"),
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
        "labs/<uuid:lab_id>/institution-resources/load-starters/",
        av.ResourceLoadStartersView.as_view(),
        name="resource-load-starters",
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
        "labs/<uuid:lab_id>/inventory/import/",
        av.InventoryImportView.as_view(),
        name="inventory-import",
    ),
    path(
        "labs/<uuid:lab_id>/projects/<uuid:project_id>/protocols/",
        protocols.ProtocolListCreateView.as_view(),
        name="protocol-list",
    ),
    path(
        "labs/<uuid:lab_id>/protocols/<uuid:protocol_id>/",
        protocols.ProtocolDetailView.as_view(),
        name="protocol-detail",
    ),
    path(
        "labs/<uuid:lab_id>/protocols/<uuid:protocol_id>/use/",
        protocols.ProtocolUseView.as_view(),
        name="protocol-use",
    ),
    path(
        "labs/<uuid:lab_id>/projects/<uuid:project_id>/inventory-usage/",
        protocols.UsageListView.as_view(),
        name="inventory-usage",
    ),
    path(
        "labs/<uuid:lab_id>/inventory-usage/<uuid:inventoryusage_id>/reverse/",
        protocols.UsageReverseView.as_view(),
        name="inventory-usage-reverse",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/orders/",
        av.OrderListCreateView.as_view(),
        name="order-list",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/orders/export/",
        av.OrderExportView.as_view(),
        name="order-export",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/orders/<uuid:inventoryorder_id>/",
        av.OrderDetailView.as_view(),
        name="order-detail",
    ),
    path("labs/<uuid:lab_id>/chat/messages/", views.LabChatListView.as_view(), name="labchat-list"),
    path(
        "labs/<uuid:lab_id>/chat/messages/read/",
        views.LabChatReadView.as_view(),
        name="labchat-read",
    ),
    path(
        "labs/<uuid:lab_id>/chat/messages/<uuid:labchatmessage_id>/",
        views.LabChatDetailView.as_view(),
        name="labchat-detail",
    ),
    path("labs/<uuid:lab_id>/calendar/", lab_calendar.CalendarView.as_view(), name="calendar"),
    path(
        "labs/<uuid:lab_id>/calendar/feed/",
        lab_calendar.CalendarFeedTokenView.as_view(),
        name="calendar-feed",
    ),
    path("calendar.ics", lab_calendar.CalendarIcsView.as_view(), name="calendar-ics"),
    path(
        "labs/<uuid:lab_id>/calendar/meetings/",
        lab_calendar.MeetingCreateView.as_view(),
        name="meeting-list",
    ),
    path(
        "labs/<uuid:lab_id>/calendar/meetings/<uuid:meeting_id>/",
        lab_calendar.MeetingDetailView.as_view(),
        name="meeting-detail",
    ),
    path(
        "labs/<uuid:lab_id>/calendar/events/",
        lab_calendar.LabEventCreateView.as_view(),
        name="labevent-list",
    ),
    path(
        "labs/<uuid:lab_id>/calendar/events/<uuid:labevent_id>/",
        lab_calendar.LabEventDetailView.as_view(),
        name="labevent-detail",
    ),
    path(
        "labs/<uuid:lab_id>/inventory/<uuid:inventoryitem_id>/",
        av.InventoryDetailView.as_view(),
        name="inventory-detail",
    ),
    path("invites/preview/", views.InvitePreviewView.as_view(), name="invite-preview"),
    path("invites/accept/", views.InviteAcceptView.as_view(), name="invite-accept"),
]
