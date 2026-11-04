from django.urls import path

from labs import views

app_name = "labs"
urlpatterns = [
    path("labs/", views.LabListCreateView.as_view(), name="lab-list"),
    path("labs/<uuid:lab_id>/", views.LabDetailView.as_view(), name="lab-detail"),
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
    path("invites/preview/", views.InvitePreviewView.as_view(), name="invite-preview"),
    path("invites/accept/", views.InviteAcceptView.as_view(), name="invite-accept"),
]
