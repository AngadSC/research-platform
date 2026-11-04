from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.response import Response

from core.permissions import Perm
from core.tenancy import project_of
from core.views import LabScopedViewMixin
from projects import services
from projects.models import Project, ProjectDeadline, ProjectMembership, Task
from projects.serializers import (
    DeadlineInputSerializer,
    DeadlineSerializer,
    ProjectInputSerializer,
    ProjectMembershipCreateSerializer,
    ProjectMembershipRoleSerializer,
    ProjectMembershipSerializer,
    ProjectSerializer,
    TaskFilterSerializer,
    TaskInputSerializer,
    TaskSerializer,
)


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
        return super().get_queryset().select_related("created_by").order_by("name", "id")

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
        return super().get_queryset().select_related("created_by")

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


class DeadlineListCreateView(ProjectScopedMixin, generics.GenericAPIView):
    model = ProjectDeadline
    serializer_class = DeadlineSerializer
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_PROJECT}

    def get_queryset(self):
        return super().get_queryset().order_by("due_date", "id")

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
        return super().get_queryset().select_related("assignee", "created_by")

    @extend_schema(responses=TaskSerializer)
    def get(self, request, lab_id, task_id):
        return self.out(self.get_object())

    @extend_schema(request=TaskInputSerializer, responses=TaskSerializer)
    def patch(self, request, lab_id, task_id):
        data = self.body(TaskInputSerializer, partial=True)
        return self.out(services.update_task(task=self.get_object(), data=data))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, task_id):
        services.delete_task(task=self.get_object(), by=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
