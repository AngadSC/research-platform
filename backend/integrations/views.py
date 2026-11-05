"""Integration endpoints (ARCHITECTURE section 9). Views validate and serialize; services act."""

from urllib.parse import urlencode

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import Perm
from core.views import LabScopedViewMixin
from integrations import registry, services
from integrations.http import IntegrationError
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink
from integrations.serializers import (
    ConnectedAccountSerializer,
    ConnectInputSerializer,
    ConnectOutputSerializer,
    ExternalLinkInputSerializer,
    ExternalLinkSerializer,
    PickerTokenSerializer,
    ProviderSerializer,
)
from integrations.services import OAuthError
from projects.views import ProjectScopedMixin

# What a person sees for each OAuthError.code. The code itself is safe to return and redirect.
OAUTH_MESSAGES = {
    "invalid_state": "That connection attempt expired. Start again.",
    "access_denied": "The connection was cancelled.",
    "provider_error": "The service could not complete the connection. Try again.",
    "invalid_request": "The service did not send what we needed. Try again.",
    "invalid_scope": "That permission is not available.",
    "unknown_provider": "That service is not available.",
    "provider_not_configured": "This service is not set up for your institution yet.",
    "scope_not_granted": "Allow every requested permission to connect.",
    "identity_failed": "We could not confirm which account you connected. Try again.",
    "other_account_connected": "Another account is already connected. Disconnect it first.",
}


def oauth_error(code):
    return Response(
        {"detail": OAUTH_MESSAGES.get(code, OAUTH_MESSAGES["provider_error"]), "code": code},
        status=status.HTTP_400_BAD_REQUEST,
    )


def _own_account(accounts, provider):
    """Active account first, otherwise the most recent one."""
    rows = [a for a in accounts if a.provider == provider]
    rows.sort(key=lambda a: (a.status == AccountStatus.ACTIVE, a.connected_at), reverse=True)
    return rows[0] if rows else None


class ProviderListView(LabScopedViewMixin, generics.GenericAPIView):
    model = ConnectedAccount
    serializer_class = ProviderSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=ProviderSerializer(many=True))
    def get(self, request, lab_id):
        mine = list(self.get_queryset().filter(user=request.user))
        out = []
        for p in registry.PROVIDERS.values():
            account = _own_account(mine, p.name)
            out.append(
                {
                    "name": p.name,
                    "label": p.label,
                    "auth_type": p.auth_type,
                    "icon": p.icon,
                    "scopes": list(p.scopes),
                    "configured": p.configured,
                    "public_config": p.public_config,
                    "account": account
                    and {
                        "id": account.pk,
                        "status": account.status,
                        "external_email": account.external_email,
                    },
                }
            )
        return Response(self.get_serializer(out, many=True).data)


class AccountMixin(LabScopedViewMixin):
    model = ConnectedAccount
    serializer_class = ConnectedAccountSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().select_related("user")


class AccountListView(AccountMixin, generics.GenericAPIView):
    """Your own accounts; `?all=true` adds every member's for people who hold
    manage_lab_integrations (everyone else still gets only their own, via visible_to)."""

    perms = {"GET": Perm.MANAGE_INTEGRATIONS}

    @extend_schema(responses=ConnectedAccountSerializer(many=True))
    def get(self, request, lab_id):
        qs = self.get_queryset().order_by("provider", "-connected_at", "id")
        if request.query_params.get("all") != "true":
            qs = qs.filter(user=request.user)
        return Response(self.get_serializer(qs, many=True).data)


class AccountDetailView(AccountMixin, generics.GenericAPIView):
    lookup_url_kwarg = "connectedaccount_id"
    perms = {"DELETE": Perm.MANAGE_INTEGRATIONS}

    @extend_schema(request=None, responses=ConnectedAccountSerializer)
    def delete(self, request, lab_id, connectedaccount_id):
        """Own account: disconnect. Another member's (manage_lab_integrations): revoke."""
        account = self.get_object()
        services.disconnect(account, actor=request.user, request=request)
        return Response(self.get_serializer(account).data)


class ConnectView(LabScopedViewMixin, generics.GenericAPIView):
    model = ConnectedAccount
    serializer_class = ConnectOutputSerializer
    perms = {"POST": Perm.MANAGE_INTEGRATIONS}

    @extend_schema(request=ConnectInputSerializer, responses=ConnectOutputSerializer)
    def post(self, request, lab_id, provider):
        body = ConnectInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            url = services.start_connect(
                request, request.lab, provider, scopes=body.validated_data.get("scopes")
            )
        except OAuthError as exc:
            return oauth_error(exc.code)
        return Response({"authorization_url": url})


class PickerTokenView(LabScopedViewMixin, generics.GenericAPIView):
    """D70: the single place a token leaves the server. The requester's own active Drive
    account only, the access token only, valid for at most an hour, never cached."""

    model = ConnectedAccount
    serializer_class = PickerTokenSerializer
    perms = {"GET": Perm.MANAGE_INTEGRATIONS}

    @extend_schema(responses=PickerTokenSerializer)
    @sensitive_variables("token")
    def get(self, request, lab_id):
        provider = registry.GOOGLE
        account = self.get_queryset().filter(
            user=request.user, provider=provider.name, status=AccountStatus.ACTIVE
        ).first()
        if account is None:
            raise Http404
        if account.token_expires_at and account.token_expires_at <= timezone.now() + timedelta(
            seconds=120
        ):
            try:
                services.refresh_access_token(account)
            except IntegrationError:
                return oauth_error("provider_error")
        if account.token_expires_at:
            left = (account.token_expires_at - timezone.now()).total_seconds()
        else:
            left = 3000  # Google access tokens last an hour; stay under it
        token = account.access_token()
        resp = Response(
            {
                "access_token": token,
                "expires_in": max(1, min(3600, int(left))),
                "scope": " ".join(provider.scopes),
            }
        )
        resp["Cache-Control"] = "no-store"
        return resp


def _frontend(path, **query):
    suffix = f"?{urlencode(query)}" if query else ""
    return HttpResponseRedirect(f"{settings.FRONTEND_URL}{path}{suffix}")


class OAuthCallbackView(APIView):
    """The browser comes back from the provider here. Always ends in a redirect to the SPA."""

    perms = {"GET": Perm.AUTHENTICATED}

    @extend_schema(responses={302: None})
    def get(self, request):
        state = request.query_params.get("state", "")
        entry = request.session.get(services.SESSION_KEY, {}).get(state)
        lab_id = entry["lab"] if entry and entry["user"] == str(request.user.pk) else None
        try:
            account = services.complete_connect(
                request,
                state=state,
                code=request.query_params.get("code", ""),
                error=request.query_params.get("error", ""),
            )
        except OAuthError as exc:
            code = exc.code
        except (Http404, DjangoPermissionDenied):
            code = "invalid_state"  # no longer a member, or no longer allowed
        except IntegrationError:
            code = "provider_error"  # token exchange refused or the provider was unreachable
        else:
            return _frontend(
                f"/labs/{account.lab_id}/settings/integrations", connected=account.provider
            )
        if lab_id:
            return _frontend(f"/labs/{lab_id}/settings/integrations", error=code)
        return _frontend("/integrations/error", code=code)


class ExternalLinkMixin(ProjectScopedMixin):
    model = ExternalLink
    serializer_class = ExternalLinkSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("linked_by", "connected_account")


class ExternalLinkListCreateView(ExternalLinkMixin, generics.GenericAPIView):
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=ExternalLinkSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().order_by("-created_at", "id")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=ExternalLinkInputSerializer, responses={201: ExternalLinkSerializer})
    def post(self, request, lab_id, project_id):
        link = services.create_link(
            project=self.project,
            user=request.user,
            data=self.body(ExternalLinkInputSerializer),
            request=request,
        )
        out = self.get_queryset().get(pk=link.pk)
        out.version_note = link.version_note
        return self.out(out, status.HTTP_201_CREATED)


class ExternalLinkDetailView(ExternalLinkMixin, generics.GenericAPIView):
    lookup_url_kwarg = "externallink_id"
    perms = {"GET": Perm.VIEW_PROJECT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(responses=ExternalLinkSerializer)
    def get(self, request, lab_id, externallink_id):
        return self.out(self.get_object())

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, externallink_id):
        services.remove_link(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExternalLinkCheckView(ExternalLinkMixin, generics.GenericAPIView):
    lookup_url_kwarg = "externallink_id"
    perms = {"POST": Perm.VIEW_PROJECT}

    @extend_schema(request=None, responses=ExternalLinkSerializer)
    def post(self, request, lab_id, externallink_id):
        """Freshness check now, with the linker's account (whoever asks)."""
        link = self.get_object()
        try:
            services.check_link(link)
        except IntegrationError:
            return Response(
                {"detail": "The service could not be reached. Try again shortly."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        return self.out(self.get_queryset().get(pk=link.pk))


class ExternalLinkAcceptChangeView(ExternalLinkMixin, generics.GenericAPIView):
    lookup_url_kwarg = "externallink_id"
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=None, responses=ExternalLinkSerializer)
    def post(self, request, lab_id, externallink_id):
        link = services.accept_change(self.get_object(), user=request.user, request=request)
        return self.out(self.get_queryset().get(pk=link.pk))
