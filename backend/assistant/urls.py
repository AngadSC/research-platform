"""Mounted at the site root (config/urls.py): the MCP endpoint and the well-known metadata must
sit at fixed root paths; the rest is under /api/ like every other endpoint."""

from django.urls import path

from assistant import ai_views, file_links, mcp, oauth, views

app_name = "assistant"
L = "api/labs/<uuid:lab_id>/"
urlpatterns = [
    path("mcp", mcp.mcp_endpoint, name="mcp"),
    path(".well-known/oauth-protected-resource", oauth.protected_resource, name="prm"),
    path(".well-known/oauth-protected-resource/mcp", oauth.protected_resource, name="prm-mcp"),
    path(".well-known/oauth-authorization-server", oauth.authorization_server, name="as-metadata"),
    path("api/oauth/register/", oauth.register, name="oauth-register"),
    path("api/oauth/token/", oauth.token, name="oauth-token"),
    path("api/oauth/authorize/", views.AuthorizeView.as_view(), name="authorize"),
    path("api/ai/grants/", views.GrantListView.as_view(), name="grant-list"),
    path("api/ai/grants/<uuid:aigrant_id>/", views.GrantDetailView.as_view(), name="grant-detail"),
    path(L + "ai-grants/", views.LabGrantListView.as_view(), name="lab-grant-list"),
    path(
        L + "ai-grants/<uuid:aigrant_id>/",
        views.LabGrantDetailView.as_view(),
        name="lab-grant-detail",
    ),
    # VISION S1: download and upload links for tools on the person's computer (MATLAB)
    path("api/file-link", file_links.FileLinkView.as_view(), name="file-link"),
    # In-app assistant (D187-D192)
    path("api/ai/keys/", ai_views.KeyListView.as_view(), name="key-list"),
    path("api/ai/keys/<str:ai_provider>/", ai_views.KeyDetailView.as_view(), name="key-detail"),
    path(L + "ai-policy/", ai_views.PolicyView.as_view(), name="ai-policy"),
    path(L + "assistant/config/", ai_views.ConfigView.as_view(), name="assistant-config"),
    path(
        L + "assistant/conversations/",
        ai_views.ConversationListView.as_view(),
        name="conversation-list",
    ),
    path(
        L + "assistant/conversations/<uuid:conversation_id>/",
        ai_views.ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        L + "assistant/conversations/<uuid:conversation_id>/messages/",
        ai_views.MessageView.as_view(),
        name="conversation-message",
    ),
    path(
        L + "assistant/conversations/<uuid:conversation_id>/approvals/",
        ai_views.ApprovalView.as_view(),
        name="conversation-approval",
    ),
]
