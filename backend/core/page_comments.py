"""Comments on any page (the floating comment button). A comment belongs to a page path in one lab;
when the path is inside a project the comment is that project's, so only people who can see the
project read it or are told about it."""

import re
import uuid

from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.models import PageComment
from core.notifications import notify_mentions
from core.permissions import Perm, can
from core.serializers import UserSerializer
from core.views import LabScopedViewMixin

PROJECT_IN_PATH = re.compile(r"^/labs/[0-9a-fA-F-]{36}/projects/([0-9a-fA-F-]{36})(?:/|$)")


def clean_path(raw: str, lab_id) -> str:
    """The page path without query or hash, and only inside this lab."""
    path = (raw or "").split("?")[0].split("#")[0].rstrip("/") or "/"
    if not path.startswith(f"/labs/{lab_id}") or len(path) > 500 or "//" in path:
        raise ValidationError({"path": "Comment on a page of this lab."})
    return path


def project_of(path: str, user, lab):
    """The project a path is inside, if any. 404 when the person cannot see it."""
    m = PROJECT_IN_PATH.match(path)
    if not m:
        return None
    from projects.models import Project

    try:
        pk = uuid.UUID(m.group(1))
    except ValueError:
        raise NotFound from None
    project = Project.objects.visible_to(user, lab).filter(pk=pk).first()
    if project is None:
        raise NotFound
    return project


class PageCommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = PageComment
        fields = ["id", "author", "path", "page_label", "quote", "body", "created_at"]
        read_only_fields = fields


class PageCommentCreateSerializer(serializers.Serializer):
    path = serializers.CharField(max_length=500)
    page_label = serializers.CharField(max_length=200, allow_blank=True, default="")
    quote = serializers.CharField(max_length=500, allow_blank=True, default="")
    body = serializers.CharField(max_length=4000)

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Write a comment.")
        return value


class PageCommentMixin(LabScopedViewMixin):
    model = PageComment
    serializer_class = PageCommentSerializer
    pagination_class = None
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"

    def get_throttles(self):  # writing only
        return super().get_throttles() if self.request.method == "POST" else []

    def get_queryset(self):
        return super().get_queryset().select_related("author")


class PageCommentListCreateView(PageCommentMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}

    @extend_schema(
        parameters=[OpenApiParameter("path", str, description="The page's path in the app.")],
        responses=PageCommentSerializer(many=True),
    )
    def get(self, request, lab_id):
        """The comments on one page, oldest first."""
        path = clean_path(request.query_params.get("path", ""), lab_id)
        project_of(path, request.user, request.lab)  # 404 for a project the person cannot see
        qs = self.get_queryset().filter(path=path).order_by("created_at", "id")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=PageCommentCreateSerializer, responses={201: PageCommentSerializer})
    @transaction.atomic
    def post(self, request, lab_id):
        ser = PageCommentCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        path = clean_path(data["path"], lab_id)
        project = project_of(path, request.user, request.lab)
        comment = PageComment.objects.create(
            lab=request.lab,
            project=project,
            author=request.user,
            path=path,
            page_label=data["page_label"].strip(),
            quote=data["quote"].strip(),
            body=data["body"].strip(),
        )
        # Only people who can see the page are told: its project, or the whole lab.
        notify_mentions(
            lab=request.lab,
            author=request.user,
            body=comment.body,
            where=f"a comment on {comment.page_label or 'a page'}",
            perm=Perm.VIEW_PROJECT if project else Perm.VIEW_LAB,
            target=project or request.lab,
            key=f"pagecomment:{comment.pk}",
        )
        return Response(self.get_serializer(comment).data, status=status.HTTP_201_CREATED)


class PageCommentDetailView(PageCommentMixin, generics.GenericAPIView):
    lookup_url_kwarg = "page_comment_id"
    perms = {"DELETE": Perm.VIEW_LAB}

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, page_comment_id):
        """Its author, or someone who can manage the lab."""
        comment = self.get_object()
        if comment.author_id != request.user.pk and not can(
            request.user, Perm.MANAGE_LAB, request.lab
        ):
            raise PermissionDenied
        comment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
