"""SPA API for AI access (D161, D164): the consent step of the OAuth flow, and the "Connected AI
apps" / "Access tokens" lists in Settings, plus each lab's list for pi and lab_admin."""

from urllib.parse import urlencode, urlsplit

from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assistant import services
from assistant.models import Access, ClientKind
from assistant.serializers import (
    AuthorizeResultSerializer,
    AuthorizeSerializer,
    GrantSerializer,
    LabGrantSerializer,
    PatCreatedSerializer,
    PatCreateSerializer,
)
from assistant.services import LOOPBACK, OAuthError
from core.permissions import Perm, lab_role, labs_for
from core.views import LabScopedViewMixin

KNOWN_SCOPES = {"mcp:read", "mcp:write", "offline_access"}


def _redirect(uri, **params):
    params = {k: v for k, v in params.items() if v}
    params["iss"] = settings.MCP_BASE_URL  # RFC 9207, on success and error alike
    return uri + ("&" if urlsplit(uri).query else "?") + urlencode(params)


class AuthorizeView(APIView):
    """POST with decision `check` (validate and describe the request for the consent page),
    `approve` (labs and access chosen) or `deny`. Invalid client or redirect URI: 400 and never a
    redirect (RFC 6749 section 4.1.2.1); other errors: 400 with `redirect` to the client."""

    perms = {"POST": Perm.AUTHENTICATED}

    @extend_schema(request=AuthorizeSerializer, responses=AuthorizeResultSerializer)
    @sensitive_variables("code")
    def post(self, request):
        s = AuthorizeSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        q = s.validated_data
        try:
            client = services.resolve_client(q["client_id"])
        except OAuthError as exc:
            return Response({"error": exc.code, "error_description": exc.description}, 400)
        uri = q["redirect_uri"]
        if not services.redirect_matches(uri, client.redirect_uris) or not (
            services.redirect_allowed(uri)
        ):
            return Response(
                {"error": "invalid_request", "error_description": "The redirect URI is not valid."},
                400,
            )
        state = q.get("state", "")

        def fail(code, description):
            return Response(
                {
                    "error": code,
                    "error_description": description,
                    "redirect": _redirect(uri, error=code, state=state),
                },
                400,
            )

        if q.get("response_type") != "code":
            return fail("unsupported_response_type", "Only response_type=code is supported.")
        if not q.get("code_challenge") or q.get("code_challenge_method") != "S256":
            return fail("invalid_request", "PKCE with S256 is required.")
        resource = q.get("resource")
        if resource and services.canonical(resource) != services.canonical(services.mcp_url()):
            return fail("invalid_target", "Unknown resource.")
        scopes = set((q.get("scope") or "mcp:read").split())
        if not scopes <= KNOWN_SCOPES:
            return fail("invalid_scope", "Unknown scope.")

        decision = q["decision"]
        if decision == "check":
            host = urlsplit(uri).hostname or ""
            return Response(
                {
                    "client": {
                        "name": client.name,
                        "verified_host": (
                            urlsplit(client.client_id).hostname
                            if client.kind == ClientKind.CIMD
                            else None
                        ),
                        "redirect_host": host,
                        "loopback": host in LOOPBACK,
                    },
                    "labs": [
                        {"id": lab.pk, "name": lab.name, "role": lab_role(request.user, lab)}
                        for lab in labs_for(request.user)
                    ],
                }
            )
        if decision == "deny":
            return Response({"redirect": _redirect(uri, error="access_denied", state=state)})
        # approve: no password re-check; Google-only accounts have no password to give
        # D219: the person decides, whatever the app asked for; read only unless they choose write
        access = Access.WRITE if q.get("access") == "write" else Access.READ
        try:
            code = services.approve(
                request.user,
                client,
                lab_ids=q.get("labs") or [],
                access=access,
                redirect_uri=uri,
                challenge=q["code_challenge"],
                request=request,
            )
        except OAuthError as exc:
            return Response({"labs": [exc.description]}, 400)
        return Response({"redirect": _redirect(uri, code=code, state=state)})


class GrantListView(generics.ListAPIView):
    """Your connected AI apps and access tokens. POST creates a personal access token (D164)."""

    serializer_class = GrantSerializer
    pagination_class = None
    perms = {"GET": Perm.AUTHENTICATED, "POST": Perm.AUTHENTICATED}
    throttle_scope = "ai_token"

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    def get_queryset(self):
        # live grants, then those a password change, MFA removal or similar ended (D195)
        user = self.request.user
        return [*services.active_grants(user), *services.ended_by_security(user)]

    @extend_schema(request=PatCreateSerializer, responses={201: PatCreatedSerializer})
    @sensitive_variables("token")
    def post(self, request):
        s = PatCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        try:
            grant, token = services.create_pat(
                request.user,
                name=d["name"].strip(),
                lab_ids=d["labs"],
                access=d["access"],
                days=d["expires_in_days"],
                request=request,
            )
        except OAuthError as exc:
            return Response({"labs": [exc.description]}, 400)
        grant.token = token
        return Response(PatCreatedSerializer(grant).data, status=status.HTTP_201_CREATED)


class GrantDetailView(generics.DestroyAPIView):
    """Revoke one of your own grants; anyone else's is a 404."""

    lookup_url_kwarg = "aigrant_id"
    serializer_class = GrantSerializer
    perms = {"DELETE": Perm.AUTHENTICATED}

    def get_queryset(self):
        return services.active_grants(self.request.user)

    def perform_destroy(self, grant):
        services.revoke(grant, by=self.request.user, request=self.request)


class LabGrantListView(LabScopedViewMixin, generics.ListAPIView):
    """Every active AI grant that names this lab (manage_lab_integrations: pi, lab_admin)."""

    serializer_class = LabGrantSerializer
    pagination_class = None
    perms = {"GET": Perm.MANAGE_LAB_INTEGRATIONS}

    def get_queryset(self):
        return services.lab_grants(self.request.lab)


class LabGrantDetailView(LabScopedViewMixin, generics.DestroyAPIView):
    """Remove this lab from a member's grant (the grant ends if no lab is left)."""

    lookup_url_kwarg = "aigrant_id"
    serializer_class = LabGrantSerializer
    perms = {"DELETE": Perm.MANAGE_LAB_INTEGRATIONS}

    def get_queryset(self):
        return services.lab_grants(self.request.lab)

    def check_object_permissions(self, request, obj):  # the grant is not lab data: check the lab
        super().check_permissions(request)

    def perform_destroy(self, grant):
        services.revoke(grant, by=self.request.user, lab=self.request.lab, request=self.request)
