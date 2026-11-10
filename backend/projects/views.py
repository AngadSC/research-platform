from django.core.exceptions import PermissionDenied
from django.db.models import Case, Count, IntegerField, Prefetch, When
from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, can
from core.tenancy import project_of
from core.views import LabScopedViewMixin
from documents.models import Attachment, Document
from labs.models import LabMembership
from projects import handover, services
from projects.models import ChatMessage, Project, ProjectDeadline, ProjectMembership, Task, TaskPost
from projects.serializers import (
    ChatMessageFilterSerializer,
    ChatMessageInputSerializer,
    ChatMessageSerializer,
    ChatReadInputSerializer,
    ChatUnreadSerializer,
    DeadlineInputSerializer,
    DeadlineSerializer,
    HandoverSerializer,
    ProjectInputSerializer,
    ProjectMembershipCreateSerializer,
    ProjectMembershipRoleSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
    RetentionItemSerializer,
    TaskFilterSerializer,
    TaskInputSerializer,
    TaskLinkInputSerializer,
    TaskPostInputSerializer,
    TaskPostSerializer,
    TaskSerializer,
)


def _task_attachments(request):
    """A task never names a file the person cannot open, such as a grant letter (D226)."""
    return Prefetch("attachments", Attachment.objects.visible_to(request.user, request.lab))


class ProjectScopedMixin(LabScopedViewMixin):
    """Resolves `self.project` before permissions run (ARCHITECTURE section 2), so a project
    or item the user cannot see is a 404 and HasPerm checks the project's perms.

    - `<project_id>` in the URL (nested collections and the project itself): that project.
    - otherwise `lookup_url_kwarg` (flat item routes): the item's project.
    """

    project = None
    nested = False  # collection under /projects/<project_id>/: filter to that project
    pagination_class = None

    def check_permissions(self, request):
        user, lab = request.user, request.lab
        if "project_id" in self.kwargs:
            self.project = (
                Project.objects.visible_to(user, lab).filter(pk=self.kwargs["project_id"]).first()
            )
        elif self.lookup_url_kwarg in self.kwargs:
            item = self.get_queryset().filter(pk=self.kwargs[self.lookup_url_kwarg]).first()
            self.project = project_of(item) if item is not None else None
        else:
            return super().check_permissions(request)
        if self.project is None:
            raise Http404
        super().check_permissions(request)

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(project=self.project) if self.nested else qs

    def body(self, serializer_class, *, partial=False):
        ser = serializer_class(data=self.request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        return ser.validated_data

    def out(self, obj, code=status.HTTP_200_OK):
        return Response(self.get_serializer(obj).data, status=code)


# ---------------------------------------------------------------- projects


class ProjectListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    model = Project
    serializer_class = ProjectSerializer
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.CREATE_PROJECT}

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("created_by", "last_activity_by")
            .order_by("name", "id")
        )

    @extend_schema(responses=ProjectSerializer(many=True))
    def get(self, request, lab_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=ProjectInputSerializer, responses={201: ProjectSerializer})
    def post(self, request, lab_id):
        project = services.create_project(
            lab=request.lab,
            user=request.user,
            data=self.body(ProjectInputSerializer),
            request=request,
        )
        return self.out(project, status.HTTP_201_CREATED)


class ProjectDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = Project
    serializer_class = ProjectSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_PROJECT, "DELETE": Perm.DELETE_PROJECT}

    def get_queryset(self):
        return super().get_queryset().select_related("created_by", "last_activity_by")

    @extend_schema(responses=ProjectSerializer)
    def get(self, request, lab_id, project_id):
        return self.out(self.project)

    @extend_schema(request=ProjectInputSerializer, responses=ProjectSerializer)
    def patch(self, request, lab_id, project_id):
        data = self.body(ProjectInputSerializer, partial=True)
        project = services.update_project(
            project=self.project, user=request.user, data=data, request=request
        )
        return self.out(project)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, project_id):
        services.delete_project(project=self.project, user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- members


class ProjectMemberListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    model = ProjectMembership
    serializer_class = ProjectMembershipSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.MANAGE_PROJECT_MEMBERS}

    def get_queryset(self):
        return super().get_queryset().select_related("user").order_by("created_at", "id")

    @extend_schema(responses=ProjectMembershipSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(
        request=ProjectMembershipCreateSerializer, responses={201: ProjectMembershipSerializer}
    )
    def post(self, request, lab_id, project_id):
        data = self.body(ProjectMembershipCreateSerializer)
        membership = services.add_member(
            project=self.project,
            by=request.user,
            user_id=data["user"],
            role=data["role"],
            request=request,
        )
        return self.out(membership, status.HTTP_201_CREATED)


class ProjectMemberDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = ProjectMembership
    serializer_class = ProjectMembershipSerializer
    lookup_url_kwarg = "projectmembership_id"
    perms = {"PATCH": Perm.MANAGE_PROJECT_MEMBERS, "DELETE": Perm.MANAGE_PROJECT_MEMBERS}

    @extend_schema(request=ProjectMembershipRoleSerializer, responses=ProjectMembershipSerializer)
    def patch(self, request, lab_id, projectmembership_id):
        membership = services.change_member_role(
            membership=self.get_object(),
            by=request.user,
            role=self.body(ProjectMembershipRoleSerializer)["role"],
            request=request,
        )
        return self.out(membership)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, projectmembership_id):
        services.remove_member(membership=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- deadlines

# high, then medium, then low (D137)
PRIORITY_ORDER = Case(
    When(priority="high", then=0),
    When(priority="medium", then=1),
    default=2,
    output_field=IntegerField(),
)


class DeadlineListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    model = ProjectDeadline
    serializer_class = DeadlineSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_PROJECT}

    def get_queryset(self):
        return super().get_queryset().order_by(PRIORITY_ORDER, "due_date", "id")

    @extend_schema(responses=DeadlineSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=DeadlineInputSerializer, responses={201: DeadlineSerializer})
    def post(self, request, lab_id, project_id):
        deadline = services.create_deadline(
            project=self.project, data=self.body(DeadlineInputSerializer)
        )
        return self.out(deadline, status.HTTP_201_CREATED)


class DeadlineDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = ProjectDeadline
    serializer_class = DeadlineSerializer
    lookup_url_kwarg = "projectdeadline_id"
    perms = {"PATCH": Perm.EDIT_PROJECT, "DELETE": Perm.EDIT_PROJECT}

    @extend_schema(request=DeadlineInputSerializer, responses=DeadlineSerializer)
    def patch(self, request, lab_id, projectdeadline_id):
        data = self.body(DeadlineInputSerializer, partial=True)
        return self.out(services.update_deadline(deadline=self.get_object(), data=data))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, projectdeadline_id):
        services.delete_deadline(deadline=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- tasks


class TaskListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    model = Task
    serializer_class = TaskSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("assignee", "created_by")
            .prefetch_related("documents", _task_attachments(self.request))
            .annotate(post_count=Count("posts"))
            .order_by("status", "position", "created_at", "id")
        )

    @extend_schema(parameters=[TaskFilterSerializer], responses=TaskSerializer(many=True))
    def get(self, request, lab_id, project_id):
        filters = TaskFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        qs = self.get_queryset()
        if "status" in filters.validated_data:
            qs = qs.filter(status=filters.validated_data["status"])
        if "assignee" in filters.validated_data:
            qs = qs.filter(assignee_id=filters.validated_data["assignee"])
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=TaskInputSerializer, responses={201: TaskSerializer})
    def post(self, request, lab_id, project_id):
        task = services.create_task(
            project=self.project, by=request.user, data=self.body(TaskInputSerializer)
        )
        return self.out(task, status.HTTP_201_CREATED)


class TaskDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = Task
    serializer_class = TaskSerializer
    lookup_url_kwarg = "task_id"
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("assignee", "created_by")
            .prefetch_related("documents", _task_attachments(self.request))
            .annotate(post_count=Count("posts"))
        )

    @extend_schema(responses=TaskSerializer)
    def get(self, request, lab_id, task_id):
        return self.out(self.get_object())

    @extend_schema(request=TaskInputSerializer, responses=TaskSerializer)
    def patch(self, request, lab_id, task_id):
        data = self.body(TaskInputSerializer, partial=True)
        services.update_task(task=self.get_object(), data=data)
        return self.out(self.get_queryset().get(pk=task_id))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, task_id):
        services.delete_task(task=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- chat


class ChatMessageListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    """D206: everyone on the project can read and post, viewers included. Clients poll this."""

    model = ChatMessage
    serializer_class = ChatMessageSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.VIEW_PROJECT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "chat"
    page_size = 100

    def get_throttles(self):  # sending only; polling is not rate limited
        return super().get_throttles() if self.request.method == "POST" else []

    def get_queryset(self):
        return super().get_queryset().select_related("author")

    @extend_schema(
        parameters=[ChatMessageFilterSerializer], responses=ChatMessageSerializer(many=True)
    )
    def get(self, request, lab_id, project_id):
        """The newest page, oldest first; `before` (a message's created_at) pages back."""
        filters = ChatMessageFilterSerializer(data=request.query_params)
        filters.is_valid(raise_exception=True)
        qs = self.get_queryset()
        if "before" in filters.validated_data:
            qs = qs.filter(created_at__lt=filters.validated_data["before"])
        page = list(qs.order_by("-created_at", "-id")[: self.page_size])
        return Response(self.get_serializer(reversed(page), many=True).data)

    @extend_schema(request=ChatMessageInputSerializer, responses={201: ChatMessageSerializer})
    def post(self, request, lab_id, project_id):
        message = services.post_message(
            project=self.project,
            by=request.user,
            body=self.body(ChatMessageInputSerializer)["body"],
        )
        return self.out(message, status.HTTP_201_CREATED)


class ChatMessageDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = ChatMessage
    serializer_class = ChatMessageSerializer
    lookup_url_kwarg = "chatmessage_id"
    perms = {"DELETE": Perm.VIEW_PROJECT}  # services.delete_message narrows this to author or lead

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, chatmessage_id):
        services.delete_message(message=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatReadView(ProjectScopedMixin, generics.GenericAPIView):
    model = ChatMessage
    serializer_class = ChatReadInputSerializer
    nested = True
    perms = {"POST": Perm.VIEW_PROJECT}

    @extend_schema(request=ChatReadInputSerializer, responses={204: None})
    def post(self, request, lab_id, project_id):
        services.mark_chat_read(
            project=self.project,
            user=request.user,
            read_to=self.body(ChatReadInputSerializer)["last_read_at"],
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatUnreadView(LabScopedViewMixin, generics.GenericAPIView):
    """Unread counts for the sidebar badges (D207). Clients poll this."""

    serializer_class = ChatUnreadSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=ChatUnreadSerializer(many=True))
    def get(self, request, lab_id):
        rows = services.unread_chat_counts(user=request.user, lab=request.lab)
        return Response(self.get_serializer(rows, many=True).data)


class TaskChildMixin(ProjectScopedMixin):
    """Routes under `L/tasks/<task_id>/...` (thread, links): the task is resolved first, so a
    task the user cannot see is a 404, and its project drives the permission check."""

    task = None

    def check_permissions(self, request):
        self.task = (
            Task.objects.visible_to(request.user, request.lab)
            .select_related("project", "assignee")
            .filter(pk=self.kwargs["task_id"])
            .first()
        )
        if self.task is None:
            raise Http404
        self.project = self.task.project
        super(ProjectScopedMixin, self).check_permissions(request)  # HasPerm, on self.project


class TaskPostListCreateView(TaskChildMixin, generics.GenericAPIView):
    model = TaskPost
    serializer_class = TaskPostSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}  # D142

    @extend_schema(responses=TaskPostSerializer(many=True))
    def get(self, request, lab_id, task_id):
        qs = self.get_queryset().filter(task=self.task).select_related("author")
        return Response(self.get_serializer(qs.order_by("created_at", "id"), many=True).data)

    @extend_schema(request=TaskPostInputSerializer, responses={201: TaskPostSerializer})
    def post(self, request, lab_id, task_id):
        body = self.body(TaskPostInputSerializer)["body"]
        post = services.create_post(task=self.task, author=request.user, body=body)
        return self.out(post, status.HTTP_201_CREATED)


class TaskPostDetailView(ProjectScopedMixin, generics.GenericAPIView):
    model = TaskPost
    serializer_class = TaskPostSerializer
    lookup_url_kwarg = "taskpost_id"
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    def get_queryset(self):
        return super().get_queryset().select_related("author", "task__project")

    @extend_schema(request=TaskPostInputSerializer, responses=TaskPostSerializer)
    def patch(self, request, lab_id, taskpost_id):
        body = self.body(TaskPostInputSerializer)["body"]
        return self.out(services.edit_post(post=self.get_object(), by=request.user, body=body))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, taskpost_id):
        services.delete_post(post=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class _TaskLinkMixin(TaskChildMixin, generics.GenericAPIView):
    kind = ""  # "documents" or "attachments"
    link_model = None
    serializer_class = TaskSerializer
    perms = {"POST": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    def _in_project(self, pk):
        item = self.link_model.objects.visible_to(self.request.user, self.request.lab)
        item = item.filter(pk=pk, project=self.project).first()
        if item is None:
            raise Http404
        return item

    def _out(self):
        task = (
            Task.objects.visible_to(self.request.user, self.request.lab)
            .select_related("assignee", "created_by")
            .prefetch_related("documents", _task_attachments(self.request))
            .annotate(post_count=Count("posts"))
            .get(pk=self.task.pk)
        )
        return Response(TaskSerializer(task).data)


class TaskDocumentAddView(_TaskLinkMixin):
    kind, link_model = "documents", Document

    @extend_schema(request=TaskLinkInputSerializer, responses={200: TaskSerializer})
    def post(self, request, lab_id, task_id):
        pk = self.body(TaskLinkInputSerializer)["id"]
        try:
            item = self._in_project(pk)
        except Http404:  # a body id is a 400, like every other scoped FK input
            raise serializers.ValidationError({"id": "That item is not in this project."}) from None
        services.link_to_task(task=self.task, kind=self.kind, obj=item)
        return self._out()


class TaskAttachmentAddView(TaskDocumentAddView):
    kind, link_model = "attachments", Attachment


class TaskDocumentRemoveView(_TaskLinkMixin):
    kind, link_model = "documents", Document

    @extend_schema(responses={200: TaskSerializer})
    def delete(self, request, lab_id, task_id, document_id):
        services.unlink_from_task(task=self.task, kind=self.kind, obj=self._in_project(document_id))
        return self._out()


class TaskAttachmentRemoveView(_TaskLinkMixin):
    kind, link_model = "attachments", Attachment

    @extend_schema(responses={200: TaskSerializer})
    def delete(self, request, lab_id, task_id, attachment_id):
        services.unlink_from_task(
            task=self.task, kind=self.kind, obj=self._in_project(attachment_id)
        )
        return self._out()


# ---------------------------------------------------------------- retention


class RetentionDueView(LabScopedViewMixin, generics.GenericAPIView):
    """The PI review list: items past `retain_until`, soft-deleted ones flagged. Read only."""

    serializer_class = RetentionItemSerializer
    pagination_class = None
    perms = {"GET": Perm.VIEW_RETENTION}

    @extend_schema(responses=RetentionItemSerializer(many=True))
    def get(self, request, lab_id):
        projects, documents = services.retention_due(request.lab)
        rows = [
            {
                "kind": "project",
                "id": p.pk,
                "name": p.name,
                "project_id": p.pk,
                "project_name": p.name,
                "retain_until": p.retain_until,
                "retention_note": p.retention_note,
                "deleted_at": p.deleted_at,
            }
            for p in projects
        ] + [
            {
                "kind": "document",
                "id": d.pk,
                "name": d.title,
                "project_id": d.project_id,
                "project_name": d.project.name,
                "retain_until": d.retain_until,
                "retention_note": d.retention_note,
                "deleted_at": d.deleted_at,
            }
            for d in documents
        ]
        rows.sort(key=lambda r: (r["retain_until"], r["name"]))
        return Response(self.get_serializer(rows, many=True).data)


# ---------------------------------------------------------------- handover (Phase 6)


def _handover(request, membership, project=None):
    report = handover.build_report(
        requester=request.user, lab=request.lab, membership=membership, project=project
    )
    counts = {s["key"]: len(s["items"]) for s in report["sections"]}
    record(
        AuditAction.HANDOVER_GENERATED,
        actor=request.user,
        lab=request.lab,
        target=project or membership,
        request=request,
        metadata={
            "person": str(membership.user_id),
            "counts": counts | {"no_other_owner": len(report["no_other_owner"])},
        },
    )
    return Response(report)


class MemberHandoverView(LabScopedViewMixin, generics.GenericAPIView):
    """manage_members, or the target is the requester."""

    model = LabMembership
    serializer_class = HandoverSerializer
    lookup_url_kwarg = "membership_id"
    pagination_class = None
    perms = {"GET": Perm.VIEW_LAB}

    def get_queryset(self):
        return super().get_queryset().select_related("user")

    @extend_schema(responses=HandoverSerializer)
    def get(self, request, lab_id, membership_id):
        membership = self.get_object()
        if membership.user_id != request.user.pk and not can(
            request.user, Perm.MANAGE_MEMBERS, request.lab
        ):
            raise PermissionDenied
        return _handover(request, membership)


class ProjectHandoverView(ProjectScopedMixin, generics.GenericAPIView):
    """manage_project_members, limited to this project. `?user=<user_id>` picks the person
    (default: the requester)."""

    serializer_class = HandoverSerializer
    perms = {"GET": Perm.MANAGE_PROJECT_MEMBERS}

    @extend_schema(
        parameters=[OpenApiParameter("user", OpenApiTypes.UUID, description="Person to report on")],
        responses=HandoverSerializer,
    )
    def get(self, request, lab_id, project_id):
        user_id = serializers.UUIDField().run_validation(
            request.query_params.get("user", request.user.pk)
        )
        membership = (
            LabMembership.objects.visible_to(request.user, request.lab)
            .select_related("user")
            .filter(user_id=user_id)
            .first()
        )
        if membership is None:
            raise Http404
        return _handover(request, membership, self.project)
