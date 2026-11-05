from django.urls import path

from integrations import views

app_name = "integrations"
L = "labs/<uuid:lab_id>/"
urlpatterns = [
    path(L + "integrations/providers/", views.ProviderListView.as_view(), name="provider-list"),
    path(L + "integrations/accounts/", views.AccountListView.as_view(), name="account-list"),
    path(
        L + "integrations/accounts/<uuid:connectedaccount_id>/",
        views.AccountDetailView.as_view(),
        name="account-detail",
    ),
    path(L + "integrations/<slug:provider>/connect/", views.ConnectView.as_view(), name="connect"),
    path("integrations/oauth/callback/", views.OAuthCallbackView.as_view(), name="oauth-callback"),
    path(
        L + "projects/<uuid:project_id>/external-links/",
        views.ExternalLinkListCreateView.as_view(),
        name="external-link-list",
    ),
    path(
        L + "external-links/<uuid:externallink_id>/",
        views.ExternalLinkDetailView.as_view(),
        name="external-link-detail",
    ),
]
