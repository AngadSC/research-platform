"""Integration endpoints (ARCHITECTURE section 9). Views validate and serialize; services act."""

from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import Throttled, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from audit import services as audit
from audit.models import AuditAction
from core.permissions import Perm
from core.views import LabScopedViewMixin
from integrations import http, registry, services, webhooks
from integrations.http import IntegrationError
from integrations.models import AccountStatus, ConnectedAccount, ExternalLink, Webhook
from integrations.serializers import (
    ConnectedAccountSerializer,
    ConnectInputSerializer,
    ConnectOutputSerializer,
    ExternalLinkInputSerializer,
    ExternalLinkSerializer,
    ImportResultSerializer,
    ImportTasksInputSerializer,
    ItemSearchQuerySerializer,
    ItemSearchResultSerializer,
    PickerTokenSerializer,
    ProviderSerializer,
    TaskSourceSerializer,
    WebhookCreatedSerializer,
    WebhookCreateSerializer,
    WebhookListSerializer,
    WebhookSerializer,
    WebhookTestResultSerializer,
    WebhookUpdateSerializer,
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
    "unexpected_scope": "The service granted more access than we asked for. Try again.",
    "other_account_connected": "Another account is already connected. Disconnect it first.",
    "invalid_key": "The service did not accept that key. Check it and try again.",
    "invalid_instance_url": "Enter the server's https address, for example "
    "https://redcap.example.edu. It must be reachable from the internet.",
    "instance_not_allowed": "This server is not on your institution's list of allowed servers.",
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


def provider_entry(p, account) -> dict:
    """Registry metadata for the generic UI (D80). Never a client secret or a key."""
    return {
        "name": p.name,
        "label": p.label,
        "auth_type": p.auth_type,
        "category": p.category,
        "icon": p.icon,
        "metadata_only": p.metadata_only,
        "scopes": list(p.scopes),
        "configured": p.configured,
        "public_config": p.public_config,
        "link_targets": [t for t in registry.TARGETS if t in p.link_targets],
        "link_methods": list(p.link_methods),
        "needs_instance_url": p.needs_instance_url,
        "connect_fields": [
            {
                "name": f.name,
                "label": f.label,
                "help_text": f.help_text,
                "required": f.required,
                "secret": f.secret,
            }
            for f in p.connect_fields
        ],
        "external_id_pattern": p.external_id_pattern,
        "url_pattern": p.url_pattern,
        "link_hosts": sorted(p.link_hosts),
        "can_check": p.fetch_item is not None,
        "task_import": p.fetch_tasks is not None,
        "account": account
        and {
            "id": account.pk,
            "status": account.status,
            "external_email": account.external_email,
            "instance_url": account.instance_url,
        },
    }


class ProviderListView(LabScopedViewMixin, generics.GenericAPIView):
    model = ConnectedAccount
    serializer_class = ProviderSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=ProviderSerializer(many=True))
    def get(self, request, lab_id):
        mine = list(self.get_queryset().filter(user=request.user))
        shown = [p for p in registry.PROVIDERS.values() if p.configured or not p.opt_in]  # D240
        out = [provider_entry(p, _own_account(mine, p.name)) for p in shown]
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


@method_decorator(sensitive_post_parameters("api_key", "secret"), name="dispatch")
class ConnectView(LabScopedViewMixin, generics.GenericAPIView):
    """oauth2: start the flow, returns the authorization URL. api_key: validate the key with
    the provider and store it (D81); the key is never echoed, logged or audited."""

    model = ConnectedAccount
    serializer_class = ConnectOutputSerializer
    perms = {"POST": Perm.MANAGE_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_connect"

    @extend_schema(request=ConnectInputSerializer, responses=ConnectOutputSerializer)
    @sensitive_variables()
    def post(self, request, lab_id, provider):
        body = ConnectInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        entry = registry.PROVIDERS.get(provider)
        try:
            if entry is not None and entry.auth_type == registry.AuthType.API_KEY:
                account = services.connect_with_key(
                    request,
                    request.lab,
                    provider,
                    api_key=data.get("api_key", ""),
                    secret=data.get("secret", ""),
                    instance_url=data.get("instance_url", ""),
                )
                out = {"authorization_url": "", "account": account}
            else:
                url = services.start_connect(
                    request, request.lab, provider, scopes=data.get("scopes")
                )
                out = {"authorization_url": url, "account": None}
        except OAuthError as exc:
            return oauth_error(exc.code)
        return Response(self.get_serializer(out).data)


class PickerTokenView(LabScopedViewMixin, generics.GenericAPIView):
    """D70: the single place a token leaves the server. The requester's own active Drive
    account only, the access token only, valid for at most an hour, never cached."""

    model = ConnectedAccount
    serializer_class = PickerTokenSerializer
    perms = {"GET": Perm.MANAGE_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "picker_token"

    @extend_schema(responses=PickerTokenSerializer)
    @sensitive_variables("token")
    def get(self, request, lab_id):
        provider = registry.get("google_drive")
        account = (
            self.get_queryset()
            .filter(user=request.user, provider=provider.name, status=AccountStatus.ACTIVE)
            .first()
        )
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
        audit.record(  # who got a browser token and when; never the token itself
            AuditAction.INTEGRATION_PICKER_TOKEN,
            actor=request.user,
            lab=request.lab,
            target=account,
            request=request,
            metadata={"provider": provider.name},
        )
        resp = Response(
            {
                "access_token": token,
                "expires_in": max(1, min(3600, int(left))),
                "scope": " ".join(account.granted_scopes),
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "link_check"

    @extend_schema(request=None, responses=ExternalLinkSerializer)
    def post(self, request, lab_id, externallink_id):
        """Freshness check now, with the linker's account (whoever asks)."""
        link = self.get_object()
        if link.last_checked_at:
            wait = (
                services.CHECK_MIN_INTERVAL
                - (timezone.now() - link.last_checked_at).total_seconds()
            )
            if wait > 0:
                raise Throttled(
                    wait=int(wait) + 1, detail="Checked a moment ago. Try again in a minute."
                )
        try:
            with http.budget(settings.INTEGRATION_ENDPOINT_BUDGET):
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


class ItemSearchView(ProjectScopedMixin, generics.GenericAPIView):
    """D85: candidates from a provider without a picker. Your own account only, edit_content on
    the project, throttled, never cached (here or by the browser)."""

    model = ExternalLink
    serializer_class = ItemSearchResultSerializer
    perms = {"GET": Perm.EDIT_CONTENT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_search"

    @extend_schema(
        parameters=[
            OpenApiParameter("q", str, description="Empty: the provider's recent items."),
            OpenApiParameter("target", str, enum=list(registry.TARGETS)),
        ],
        responses=ItemSearchResultSerializer(many=True),
    )
    def get(self, request, lab_id, project_id, provider):
        query = ItemSearchQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        try:
            results = services.search_items(
                project=self.project,
                user=request.user,
                provider_name=provider,
                query=query.validated_data["q"],
                target=query.validated_data["target"],
                request=request,
            )
        except IntegrationError:
            resp = Response(
                {"detail": "The service could not be reached. Try again shortly."},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        else:
            resp = Response(self.get_serializer(results, many=True).data)
        resp["Cache-Control"] = "no-store"
        return resp


# ---- task import (D240)


def _unavailable():
    return Response(
        {"detail": "The service could not be reached. Try again shortly."},
        status=status.HTTP_502_BAD_GATEWAY,
    )


class TaskSourcesView(LabScopedViewMixin, generics.GenericAPIView):
    """The lists you can import tasks from, read with your own account."""

    model = ConnectedAccount
    serializer_class = TaskSourceSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_search"

    @extend_schema(responses=TaskSourceSerializer(many=True))
    def get(self, request, lab_id, provider):
        try:
            found = services.task_sources(request.lab, user=request.user, provider_name=provider)
        except IntegrationError:
            return _unavailable()
        return Response(self.get_serializer(found, many=True).data)


class ImportTasksView(ProjectScopedMixin, generics.GenericAPIView):
    """Copy tasks from an outside list into this project (edit_content, your own account)."""

    model = ExternalLink
    serializer_class = ImportResultSerializer
    perms = {"POST": Perm.EDIT_CONTENT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_search"

    @extend_schema(request=ImportTasksInputSerializer, responses=ImportResultSerializer)
    def post(self, request, lab_id, project_id, provider):
        body = ImportTasksInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = services.import_tasks(
                project=self.project,
                user=request.user,
                provider_name=provider,
                source=body.validated_data["source"],
                request=request,
            )
        except IntegrationError:
            return _unavailable()
        return Response(result)


# ---- outgoing webhooks (D241). manage_lab_integrations: PIs and lab admins only.


class WebhookMixin(LabScopedViewMixin):
    model = Webhook
    serializer_class = WebhookSerializer
    pagination_class = None


def _audit_webhook(action, hook, request, **extra):
    audit.record(
        action,
        actor=request.user,
        lab=request.lab,
        target=hook,
        request=request,
        metadata={"kind": hook.kind, "host": hook.host, **extra},
    )


URL_HELP = {
    "webhook": "Enter the full https address the service gave you, with nothing after a ?.",
    "slack": "Enter the address Slack gave you. It starts with https://hooks.slack.com/",
}


@method_decorator(sensitive_post_parameters("url"), name="dispatch")
class WebhookListView(WebhookMixin, generics.GenericAPIView):
    perms = {"GET": Perm.MANAGE_LAB_INTEGRATIONS, "POST": Perm.MANAGE_LAB_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_connect"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses=WebhookListSerializer)
    def get(self, request, lab_id):
        events = [{"value": k, "label": v} for k, v in webhooks.EVENTS.items()]
        rows = self.get_queryset().order_by("created_at", "id")
        return Response({"events": events, "webhooks": self.get_serializer(rows, many=True).data})

    @extend_schema(request=WebhookCreateSerializer, responses={201: WebhookCreatedSerializer})
    @sensitive_variables("url", "data", "secret", "body")
    def post(self, request, lab_id):
        body = WebhookCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        if self.get_queryset().count() >= webhooks.MAX_PER_LAB:
            raise ValidationError({"name": "This lab already has as many webhooks as it can."})
        try:
            url = webhooks.clean_url(data["url"], data["kind"])
        except http.InstanceURLError:
            raise ValidationError({"url": URL_HELP[data["kind"]]}) from None
        with transaction.atomic():
            hook, secret = webhooks.create(
                lab=request.lab,
                user=request.user,
                name=data["name"],
                kind=data["kind"],
                url=url,
                events=data["events"],
            )
            _audit_webhook(AuditAction.WEBHOOK_CREATED, hook, request, events=hook.events)
        out = WebhookSerializer(hook).data
        return Response({**out, "secret": secret}, status=status.HTTP_201_CREATED)


class WebhookDetailView(WebhookMixin, generics.GenericAPIView):
    lookup_url_kwarg = "webhook_id"
    perms = {"PATCH": Perm.MANAGE_LAB_INTEGRATIONS, "DELETE": Perm.MANAGE_LAB_INTEGRATIONS}

    @extend_schema(request=WebhookUpdateSerializer, responses=WebhookSerializer)
    def patch(self, request, lab_id, webhook_id):
        hook = self.get_object()
        body = WebhookUpdateSerializer(data=request.data, partial=True)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            for field, value in body.validated_data.items():
                setattr(hook, field, value)
            hook.save(update_fields=[*body.validated_data, "updated_at"])
            _audit_webhook(AuditAction.WEBHOOK_UPDATED, hook, request, events=hook.events)
        return Response(self.get_serializer(hook).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, webhook_id):
        hook = self.get_object()
        with transaction.atomic():
            _audit_webhook(AuditAction.WEBHOOK_DELETED, hook, request)
            hook.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class WebhookTestView(WebhookMixin, generics.GenericAPIView):
    """Send one test message now, so an admin can see the address works."""

    lookup_url_kwarg = "webhook_id"
    serializer_class = WebhookTestResultSerializer
    perms = {"POST": Perm.MANAGE_LAB_INTEGRATIONS}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "integration_connect"

    @extend_schema(request=None, responses=WebhookTestResultSerializer)
    def post(self, request, lab_id, webhook_id):
        sent = webhooks.send_test(self.get_object())
        return Response({"ok": sent is not None and 200 <= sent < 300, "status": sent})
