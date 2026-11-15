from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.response import Response

from core.permissions import Perm
from projects.services import refuse_if_archived
from projects.views import ProjectScopedMixin
from provenance import services
from provenance.serializers import (
    INPUT,
    OUTPUT,
    ExportSerializer,
    LineageSerializer,
    RecruitmentPlanInputSerializer,
    RecruitmentPlanSerializer,
    ResultSerializer,
    ResultSetInputSerializer,
    WorkflowMarkSerializer,
    WorkflowProgressSerializer,
    queryset,
)
from provenance.services import SPECS


class KindMixin(ProjectScopedMixin):
    """One view pair per kind. `ProjectScopedMixin` resolves and permission-checks the project
    (404 if invisible); reads then go through `serializers.queryset`, which is scoped to that
    project and prefetches every nested link, so no list or detail makes per-row queries."""

    kind = ""
    pagination_class = None

    @property
    def model(self):
        return SPECS[self.kind].model

    def get_serializer_class(self):
        return OUTPUT[self.kind]

    def fresh(self, obj):
        return get_object_or_404(queryset(self.kind, self.project, self.request.user), pk=obj.pk)

    def body(self, *, partial=False):
        return super().body(INPUT[self.kind], partial=partial)


class KindListCreate(KindMixin, generics.GenericAPIView):
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    def get(self, request, lab_id, project_id):
        return Response(
            self.get_serializer(
                queryset(self.kind, self.project, self.request.user), many=True
            ).data
        )

    def post(self, request, lab_id, project_id):
        obj = services.create(
            self.kind, project=self.project, user=request.user, data=self.body(), request=request
        )
        return self.out(self.fresh(obj), status.HTTP_201_CREATED)


class KindDetail(KindMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @property
    def lookup_url_kwarg(self):
        return f"{self.model._meta.model_name}_id"

    def get_object(self):
        obj = get_object_or_404(
            queryset(self.kind, self.project, self.request.user),
            pk=self.kwargs[self.lookup_url_kwarg],
        )
        self.check_object_permissions(self.request, obj)
        return obj

    def get(self, request, lab_id, **kwargs):
        return self.out(self.get_object())

    def patch(self, request, lab_id, **kwargs):
        obj = services.update(
            self.kind,
            self.get_object(),
            user=request.user,
            data=self.body(partial=True),
            request=request,
        )
        return self.out(self.fresh(obj))

    def delete(self, request, lab_id, **kwargs):
        services.delete(self.kind, self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _list_schema(kind):
    out = OUTPUT[kind]
    return extend_schema_view(
        get=extend_schema(responses=out(many=True)),
        post=extend_schema(request=INPUT[kind], responses={201: out}),
    )


def _detail_schema(kind):
    out = OUTPUT[kind]
    return extend_schema_view(
        get=extend_schema(responses=out),
        patch=extend_schema(request=INPUT[kind], responses=out),
        delete=extend_schema(responses={204: None}),
    )


@_list_schema("dataset")
class DatasetListCreateView(KindListCreate):
    kind = "dataset"


@_detail_schema("dataset")
class DatasetDetailView(KindDetail):
    kind = "dataset"


@_list_schema("analysis")
class AnalysisListCreateView(KindListCreate):
    kind = "analysis"


@_detail_schema("analysis")
class AnalysisDetailView(KindDetail):
    kind = "analysis"


@_list_schema("result")
class ResultListCreateView(KindListCreate):
    kind = "result"


@_detail_schema("result")
class ResultDetailView(KindDetail):
    kind = "result"


@_list_schema("decision")
class DecisionListCreateView(KindListCreate):
    kind = "decision"


@_detail_schema("decision")
class DecisionDetailView(KindDetail):
    kind = "decision"


@_list_schema("manuscript")
class ManuscriptListCreateView(KindListCreate):
    kind = "manuscript"


@_detail_schema("manuscript")
class ManuscriptDetailView(KindDetail):
    kind = "manuscript"


@_list_schema("funding")
class FundingListCreateView(KindListCreate):
    kind = "funding"
    perms = {"GET": Perm.ACCESS_FUNDING, "POST": Perm.ACCESS_FUNDING}  # D226


@_detail_schema("funding")
class FundingDetailView(KindDetail):
    kind = "funding"
    perms = {  # D226
        "GET": Perm.ACCESS_FUNDING,
        "PATCH": Perm.ACCESS_FUNDING,
        "DELETE": Perm.ACCESS_FUNDING,
    }


@_list_schema("review")
class ReviewListCreateView(KindListCreate):
    kind = "review"


@_detail_schema("review")
class ReviewDetailView(KindDetail):
    kind = "review"


@_list_schema("recruitment")
class RecruitmentListCreateView(KindListCreate):
    kind = "recruitment"


@_detail_schema("recruitment")
class RecruitmentDetailView(KindDetail):
    kind = "recruitment"


@_list_schema("external")
class ExternalListCreateView(KindListCreate):
    kind = "external"

    def post(self, request, lab_id, project_id):
        refuse_if_archived(self.project)
        return super().post(request, lab_id, project_id)


@_detail_schema("external")
class ExternalDetailView(KindDetail):
    kind = "external"


class ResultSetView(ProjectScopedMixin, generics.GenericAPIView):
    """Add a full set of results at once (all from one analysis)."""

    serializer_class = ResultSerializer
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=ResultSetInputSerializer, responses={201: ResultSerializer(many=True)})
    def post(self, request, lab_id, project_id):
        made = services.create_result_set(
            project=self.project,
            user=request.user,
            **self.body(ResultSetInputSerializer),
            request=request,
        )
        ids = [r.pk for r in made]
        rows = queryset("result", self.project, request.user).filter(pk__in=ids)
        return Response(self.get_serializer(rows, many=True).data, status=status.HTTP_201_CREATED)


class WorkflowProgressView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = WorkflowProgressSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT}

    @extend_schema(responses=WorkflowProgressSerializer)
    def get(self, request, lab_id, project_id):
        return Response(services.workflow_progress(self.project, request.user))

    @extend_schema(request=WorkflowMarkSerializer, responses=WorkflowProgressSerializer)
    def patch(self, request, lab_id, project_id):
        project = services.mark_workflow_stage(
            project=self.project,
            user=request.user,
            **self.body(WorkflowMarkSerializer),
            request=request,
        )
        return Response(services.workflow_progress(project, request.user))


class RecruitmentPlanView(ProjectScopedMixin, generics.GenericAPIView):
    """The project's target enrolment and notes (D136); no plan yet reads as empty."""

    serializer_class = RecruitmentPlanSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT}

    @extend_schema(responses=RecruitmentPlanSerializer)
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(services.recruitment_plan(self.project)).data)

    @extend_schema(request=RecruitmentPlanInputSerializer, responses=RecruitmentPlanSerializer)
    def patch(self, request, lab_id, project_id):
        plan = services.update_recruitment_plan(
            project=self.project,
            user=request.user,
            data=self.body(RecruitmentPlanInputSerializer, partial=True),
            request=request,
        )
        return Response(self.get_serializer(plan).data)


class LineageView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = LineageSerializer
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=LineageSerializer)
    def get(self, request, lab_id, project_id):
        return Response(services.lineage(self.project))


class ExportView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = ExportSerializer
    perms = {"POST": Perm.EXPORT}

    @extend_schema(request=None, responses=ExportSerializer)
    def post(self, request, lab_id, project_id):
        data = services.export_project(
            project=self.project,
            user=request.user,
            context=self.get_serializer_context(),
            request=request,
        )
        return Response(ExportSerializer(data, context=self.get_serializer_context()).data)
