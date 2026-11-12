"""SPA API for the in-app assistant (D187-D192): a person's provider keys, the lab's AI policy
and key (VISION A5), and the conversations with their streamed answers."""

import json
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.http import StreamingHttpResponse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from assistant.ai import catalog, chat, keys, lab_keys, prompt
from assistant.ai.types import ProviderError
from assistant.ai_serializers import (
    ApprovalDecisionSerializer,
    AssistantConfigSerializer,
    ConversationCreateSerializer,
    ConversationDetailSerializer,
    ConversationSerializer,
    KeySaveSerializer,
    KeyStatusSerializer,
    KeyUpdateSerializer,
    LabKeyCapSerializer,
    LabKeySaveSerializer,
    LabKeyStatusSerializer,
    MessageInputSerializer,
    PolicySerializer,
)
from assistant.models import AIProviderKey, Conversation, Provider
from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm
from core.views import LabScopedViewMixin
from labs.models import AiPolicy
from projects.models import Project

log = logging.getLogger(__name__)

PRIVACY_NOTICE = (
    "Content from records you can see is sent to the AI provider you choose, under your own API "
    "key (or your lab's) and that account's terms with them. Do not paste participant names or "
    "other identifying details. Ask your lab before using this with sensitive data."
)
KEEPALIVE_SECONDS = 10
HEARTBEAT_SECONDS = 10  # D196: how often a running stream refreshes its cache slots
DEADLINE_MESSAGE = "The answer took too long and was stopped. Try again, or ask something narrower."


# ---------------------------------------------------------------- keys (per user)


class KeyListView(APIView):
    perms = {"GET": Perm.AUTHENTICATED}

    @extend_schema(responses=KeyStatusSerializer(many=True))
    def get(self, request):
        return Response(KeyStatusSerializer(keys.status(request.user), many=True).data)


@method_decorator(sensitive_post_parameters("api_key"), name="dispatch")
class KeyDetailView(APIView):
    """PUT checks the key with the provider (one free call) and stores it encrypted; the answer
    never contains it. PATCH changes the Anthropic refusal-fallback setting. DELETE removes it."""

    perms = {
        "PUT": Perm.AUTHENTICATED,
        "PATCH": Perm.AUTHENTICATED,
        "DELETE": Perm.AUTHENTICATED,
    }
    throttle_scope = "ai_key"

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.request.method == "PUT" else []

    def _provider(self, ai_provider):
        if ai_provider not in Provider.values:
            raise NotFound()
        return ai_provider

    def _one(self, user, provider):
        return next(s for s in keys.status(user) if s["provider"] == provider)

    @extend_schema(request=KeySaveSerializer, responses=KeyStatusSerializer)
    @sensitive_variables()  # `body` holds the key; keep every local out of the debug page
    def put(self, request, ai_provider):
        provider = self._provider(ai_provider)
        body = KeySaveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        keys.save(request.user, provider, body.validated_data["api_key"], request=request)
        return Response(KeyStatusSerializer(self._one(request.user, provider)).data)

    @extend_schema(request=KeyUpdateSerializer, responses=KeyStatusSerializer)
    def patch(self, request, ai_provider):
        provider = self._provider(ai_provider)
        body = KeyUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        if (
            keys.set_fallback(request.user, provider, body.validated_data["refusal_fallback"])
            is None
        ):
            raise NotFound()
        return Response(KeyStatusSerializer(self._one(request.user, provider)).data)

    @extend_schema(responses={204: None})
    def delete(self, request, ai_provider):
        provider = self._provider(ai_provider)
        if not keys.remove(request.user, provider, request=request):
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- lab policy


class PolicyView(LabScopedViewMixin, generics.GenericAPIView):
    """The lab's AI policy (D188): everyone in the lab reads it; pi and lab_admin change it."""

    serializer_class = PolicySerializer
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_LAB}

    @extend_schema(responses=PolicySerializer)
    def get(self, request, lab_id):
        return Response({"ai_policy": request.lab.ai_policy})

    @extend_schema(request=PolicySerializer, responses=PolicySerializer)
    def patch(self, request, lab_id):
        body = PolicySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        lab, new = request.lab, body.validated_data["ai_policy"]
        if lab.ai_policy != new:
            lab.ai_policy = new
            lab.save(update_fields=["ai_policy", "updated_at"])
            record(
                AuditAction.LAB_UPDATED,
                actor=request.user,
                lab=lab,
                request=request,
                metadata={"name": lab.name, "changed": ["ai_policy"], "ai_policy": new},
            )
        return Response({"ai_policy": lab.ai_policy})


def _require_full(lab):
    """D188: creating a chat and sending a message need the policy `full`."""
    if lab.ai_policy != AiPolicy.FULL:
        why = (
            "AI assistants are turned off for this lab."
            if lab.ai_policy == AiPolicy.OFF
            else "This lab allows AI apps over MCP only; the in-app assistant is turned off."
        )
        raise PermissionDenied(why + " A PI or lab admin can change this in Settings.")


# ---------------------------------------------------------------- config for the panel


class ConfigView(LabScopedViewMixin, generics.GenericAPIView):
    serializer_class = AssistantConfigSerializer
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=AssistantConfigSerializer)
    def get(self, request, lab_id):
        saved = set(
            AIProviderKey.objects.filter(user=request.user).values_list("provider", flat=True)
        )
        can_use = request.lab.ai_policy == AiPolicy.FULL
        lab_key = lab_keys.get(request.lab) if can_use else None
        return Response(
            {
                "ai_policy": request.lab.ai_policy,
                "can_use": can_use,
                "privacy_notice": PRIVACY_NOTICE,
                "providers": [
                    {
                        "provider": p,
                        "label": catalog.LABELS[p],
                        "default_model": catalog.DEFAULT_MODEL[p],
                        "has_key": p in saved or (lab_key is not None and lab_key.provider == p),
                        "models": catalog.MODELS[p],
                    }
                    for p in Provider.values
                ],
                # VISION A5: whether the lab's key is there for this person (never the key)
                "lab_key": {
                    "provider": lab_key.provider,
                    "label": catalog.LABELS[lab_key.provider],
                    "own_key_wins": lab_key.provider in saved,
                    "limit_reached": not lab_keys.under_cap(lab_key),
                }
                if lab_key
                else None,
            }
        )


# ---------------------------------------------------------------- the lab's key (VISION A5)


@method_decorator(sensitive_post_parameters("api_key"), name="dispatch")
class LabKeyView(LabScopedViewMixin, generics.GenericAPIView):
    """The lab's one provider key and its monthly cap, and this month's spend per person. Only
    pi and lab_admin (manage_lab, like the AI policy) may see or change any of it. PUT sets or
    replaces the key (checked with the provider first), PATCH changes the cap, DELETE removes the
    key. The answer never contains the key: only its last 4 characters."""

    serializer_class = LabKeyStatusSerializer
    perms = {m: Perm.MANAGE_LAB for m in ("GET", "PUT", "PATCH", "DELETE")}
    throttle_scope = "ai_key"

    def get_throttles(self):
        return [ScopedRateThrottle()] if self.request.method == "PUT" else []

    def _status(self, lab):
        row = lab_keys.get(lab)
        return Response(
            LabKeyStatusSerializer(
                {
                    "saved": row is not None,
                    "provider": row.provider if row else None,
                    "label": catalog.LABELS[row.provider] if row else "",
                    "last4": row.last4 if row else "",
                    "monthly_cap_usd": row.monthly_cap_usd if row else None,
                    "updated_at": row.updated_at if row else None,
                    "month": lab_keys.this_month(),
                    "spent_usd": lab_keys.spent(lab),
                    "usage": lab_keys.usage(lab),
                }
            ).data
        )

    @extend_schema(responses=LabKeyStatusSerializer)
    def get(self, request, lab_id):
        return self._status(request.lab)

    @extend_schema(request=LabKeySaveSerializer, responses=LabKeyStatusSerializer)
    @sensitive_variables()  # `body` holds the key; keep every local out of the debug page
    def put(self, request, lab_id):
        body = LabKeySaveSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        lab_keys.save(
            request.lab,
            request.user,
            d["provider"],
            d["api_key"],
            d["monthly_cap_usd"],
            request=request,
        )
        return self._status(request.lab)

    @extend_schema(request=LabKeyCapSerializer, responses=LabKeyStatusSerializer)
    def patch(self, request, lab_id):
        body = LabKeyCapSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        cap = body.validated_data["monthly_cap_usd"]
        if lab_keys.set_cap(request.lab, request.user, cap, request=request) is None:
            raise NotFound()
        return self._status(request.lab)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id):
        if not lab_keys.remove(request.lab, request.user, request=request):
            raise NotFound()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- conversations


def _mine(request):
    return Conversation.objects.filter(user=request.user, lab=request.lab)


class ConversationListView(LabScopedViewMixin, generics.ListCreateAPIView):
    """Your conversations in this lab (never anyone else's, lab managers included)."""

    serializer_class = ConversationSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}

    def get_queryset(self):
        qs = _mine(self.request).order_by("-updated_at")
        project = self.request.query_params.get("project")
        return qs.filter(project_id=project) if project else qs[:50]

    @extend_schema(request=ConversationCreateSerializer, responses={201: ConversationSerializer})
    def post(self, request, lab_id):
        _require_full(request.lab)
        body = ConversationCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        d = body.validated_data
        project = None
        if d.get("project"):
            project = (
                Project.objects.visible_to(request.user, request.lab)
                .filter(pk=d["project"], deleted_at__isnull=True)
                .first()
            )
            if project is None:
                return Response({"project": "This project does not exist."}, status=400)
        conv = Conversation.objects.create(
            user=request.user,
            lab=request.lab,
            project=project,
            provider=d["provider"],
            model=d["model"],
            system_prompt=prompt.build(
                lab=request.lab, project=project, today=timezone.localdate()
            ),
        )
        return Response(ConversationSerializer(conv).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(LabScopedViewMixin, generics.RetrieveDestroyAPIView):
    """Read or delete your own conversation. Another person's is a 404."""

    lookup_url_kwarg = "conversation_id"
    serializer_class = ConversationDetailSerializer
    perms = {"GET": Perm.VIEW_LAB, "DELETE": Perm.VIEW_LAB}

    def get_queryset(self):
        return _mine(self.request)

    def check_object_permissions(self, request, obj):  # a conversation is not lab data: the lab
        super().check_permissions(
            request
        )  # permission was already checked, the owner filter is the rule

    def retrieve(self, request, *args, **kwargs):
        conv = self.get_object()
        conv.items = chat.timeline(conv)
        conv.pending = chat.awaiting_approval(conv)
        return Response(ConversationDetailSerializer(conv).data)


# ---------------------------------------------------------------- streaming


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _generate(request, conv, key, make):
    """The SSE body. The lock and the user message are taken when the first chunk is pulled, not
    when the view returns, so a response nobody reads leaves nothing behind. D196: a total
    deadline (shorter than the lock TTL), a heartbeat that keeps the slots alive, and the provider
    stream is closed whenever this generator is (client gone, deadline, error)."""
    from projects.activity import _request  # a write the assistant makes stamps "last edited"

    token = _request.set(request)
    lease = inner = None
    try:
        try:
            lease = chat.acquire(conv)
        except chat.Busy as exc:
            yield _sse({"type": "error", "code": "busy", "message": str(exc), "retryable": True})
            yield _sse({"type": "done"})
            return
        yield _sse(chat.start_event(conv))
        started = last_ping = beat = time.monotonic()
        try:
            inner = make(chat.Run(conv, request.user, request, key))
            for ev in inner:
                now = time.monotonic()
                if now - started > settings.ASSISTANT_STREAM_DEADLINE:
                    inner.close()  # stop reading from the provider before telling the browser
                    yield _sse(
                        {
                            "type": "error",
                            "code": "deadline",
                            "message": DEADLINE_MESSAGE,
                            "retryable": True,
                        }
                    )
                    break
                if now - beat >= HEARTBEAT_SECONDS:
                    beat = now
                    lease.touch()
                if ev["type"] == "ping":
                    if now - last_ping >= KEEPALIVE_SECONDS:
                        last_ping = now
                        yield ": keepalive\n\n"
                    continue
                yield _sse(ev)
        except ProviderError as exc:
            yield _sse(chat.error_event(exc))
        except lab_keys.Unavailable as exc:
            yield _sse(
                {"type": "error", "code": exc.code, "message": exc.message, "retryable": False}
            )
        except chat.PolicyOff:
            yield _sse(
                {
                    "type": "error",
                    "code": "ai_disabled",
                    "message": "The lab turned the in-app assistant off.",
                    "retryable": False,
                }
            )
        except Exception:  # never show internals; the log has the traceback
            log.exception("assistant stream failed")
            yield _sse(
                {
                    "type": "error",
                    "code": "unknown",
                    "message": "Something went wrong. Please try again.",
                    "retryable": True,
                }
            )
        yield _sse({"type": "done"})
    finally:
        if inner is not None:
            inner.close()
        if lease is not None:
            lease.release()
        try:
            _request.reset(token)
        except ValueError:  # reset from another context (server closed the stream)
            pass


def _stream_response(request, conv, key, make):
    resp = StreamingHttpResponse(
        _generate(request, conv, key, make), content_type="text/event-stream; charset=utf-8"
    )
    # no caching, no transformation, and tell nginx-style proxies not to buffer (docs/DEPLOY.md)
    resp["Cache-Control"] = "no-cache, no-transform"
    resp["X-Accel-Buffering"] = "no"
    return resp


def _ready(request, conv_id):
    """Common checks before a stream starts. Returns (conversation, key) or raises/returns a
    Response with the reason."""
    conv = generics.get_object_or_404(_mine(request), pk=conv_id)
    _require_full(request.lab)
    try:  # VISION A5: the person's own key wins, then the lab's key while under its cap
        key = lab_keys.key_for(request.user, request.lab, conv.provider)
    except lab_keys.Unavailable as exc:
        return conv, Response(
            {"detail": exc.message, "code": exc.code}, status=status.HTTP_400_BAD_REQUEST
        )
    if key is None:
        return conv, Response(
            {
                "detail": "Save your API key for this provider first, in Settings, "
                "under Assistant API keys.",
                "code": "no_key",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    if cache.get(f"asst-lock:{conv.pk}"):
        return conv, Response(
            {"detail": "This conversation is already answering.", "code": "busy"}, status=409
        )
    return conv, key


class MessageView(LabScopedViewMixin, generics.GenericAPIView):
    """Send a message; the answer streams back as server-sent events (text/event-stream)."""

    serializer_class = MessageInputSerializer
    perms = {"POST": Perm.VIEW_LAB}
    throttle_scope = "ai_chat"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    @extend_schema(
        request=MessageInputSerializer,
        responses={(200, "text/event-stream"): OpenApiResponse(description="Server-sent events")},
    )
    def post(self, request, lab_id, conversation_id):
        body = MessageInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        conv, key = _ready(request, conversation_id)
        if isinstance(key, Response):
            return key
        if conv.messages.count() >= catalog.MAX_MESSAGES:
            return Response(
                {"detail": "This conversation is full. Start a new one.", "code": "full"},
                status=400,
            )
        text = body.validated_data["text"].strip()
        if not conv.title:
            conv.title = text[:60]
            conv.save(update_fields=["title"])
        return _stream_response(
            request,
            conv,
            key,
            lambda run: run.send(text, body.validated_data.get("page")),
        )


class ApprovalView(LabScopedViewMixin, generics.GenericAPIView):
    """Approve or decline the write actions the assistant is waiting on, then stream on."""

    serializer_class = ApprovalDecisionSerializer
    perms = {"POST": Perm.VIEW_LAB}
    throttle_scope = "ai_chat"

    def get_throttles(self):
        return [ScopedRateThrottle()]

    @extend_schema(
        request=ApprovalDecisionSerializer,
        responses={(200, "text/event-stream"): OpenApiResponse(description="Server-sent events")},
    )
    def post(self, request, lab_id, conversation_id):
        body = ApprovalDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        conv, key = _ready(request, conversation_id)
        if isinstance(key, Response):
            return key
        waiting = {c["id"] for c in chat.awaiting_approval(conv)}
        if not waiting:
            return Response(
                {"detail": "Nothing is waiting for approval.", "code": "nothing_pending"},
                status=409,
            )
        decisions = body.validated_data["decisions"]
        if set(decisions) != waiting:
            return Response({"decisions": "Answer every action that is waiting."}, status=400)
        return _stream_response(request, conv, key, lambda run: run.decide(decisions))
