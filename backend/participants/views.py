from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm
from core.views import LabScopedViewMixin
from participants import imports, overview, rules, services
from participants.models import (
    AnalysisSet,
    Component,
    ComponentFile,
    ImportRun,
    InclusionRule,
    Participant,
    ParticipantComponent,
    ParticipantEvent,
    StatusReason,
)
from participants.serializers import (
    CellInputSerializer,
    CellSerializer,
    ComponentInputSerializer,
    ComponentSerializer,
    EventSerializer,
    FileInputSerializer,
    FileSerializer,
    ParticipantAttachInputSerializer,
    ParticipantBulkSerializer,
    ParticipantImportInputSerializer,
    ParticipantImportPreviewInputSerializer,
    ParticipantImportRunSerializer,
    ParticipantInputSerializer,
    ParticipantMatchInputSerializer,
    ParticipantSerializer,
    ReasonInputSerializer,
    ReasonSerializer,
    RuleInputSerializer,
    RuleSerializer,
    RuleSpecSerializer,
    SetInputSerializer,
    SetPatchSerializer,
    SetSerializer,
    TaskGapsInputSerializer,
)
from projects.views import ProjectScopedMixin


class RegistryMixin(ProjectScopedMixin, generics.GenericAPIView):
    """A project's registry: every route is nested under the project, so an invisible project
    is a 404 before anything else is looked at."""

    nested = True

    def body(self, serializer_class, *, partial=False, code_fields=("code",)):
        ser = serializer_class(data=self.request.data, partial=partial)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        services.guard(
            lab=self.request.lab,
            actor=self.request.user,
            data=data,
            request=self.request,
            code_fields=code_fields,
        )
        return data

    def item(self, kwarg):
        return get_object_or_404(self.get_queryset(), pk=self.kwargs[kwarg])


# ---------------------------------------------------------------- participants


class ParticipantListCreateView(RegistryMixin):
    model = Participant
    serializer_class = ParticipantSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(
        parameters=[OpenApiParameter("archived", OpenApiTypes.BOOL, description="Only archived")],
        responses=ParticipantSerializer(many=True),
    )
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().order_by("code")
        archived = request.query_params.get("archived") in ("1", "true")
        qs = qs.filter(archived_at__isnull=not archived)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        request=ParticipantBulkSerializer, responses={201: ParticipantSerializer(many=True)}
    )
    def post(self, request, lab_id, project_id):
        ser = ParticipantBulkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        shared = {k: data[k] for k in ("group", "cohort") if k in data}
        rows = [{**shared, "code": c} for c in data.get("codes", [])]
        rows += [{**shared, **row} for row in data.get("participants", [])]
        if not rows:
            raise serializers.ValidationError({"codes": "Give at least one participant code."})
        for row in rows:  # every row, so one bad code refuses the whole list
            services.guard(lab=request.lab, actor=request.user, data=row, request=request)
        made = services.create_participants(
            self.project, user=request.user, rows=rows, request=request
        )
        return Response(self.get_serializer(made, many=True).data, status=status.HTTP_201_CREATED)


class ParticipantDetailView(RegistryMixin):
    model = Participant
    serializer_class = ParticipantSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT}

    @extend_schema(responses=ParticipantSerializer)
    def get(self, request, lab_id, project_id, participant_id):
        return Response(self.get_serializer(self.item("participant_id")).data)

    @extend_schema(request=ParticipantInputSerializer, responses=ParticipantSerializer)
    def patch(self, request, lab_id, project_id, participant_id):
        p = services.update_participant(
            self.item("participant_id"),
            user=request.user,
            data=self.body(ParticipantInputSerializer, partial=True),
            request=request,
        )
        return Response(self.get_serializer(p).data)


class ParticipantArchiveView(RegistryMixin):
    model = Participant
    serializer_class = ParticipantSerializer
    perms = {"POST": Perm.EDIT_CONTENT}
    archive = True

    @extend_schema(request=None, responses=ParticipantSerializer)
    def post(self, request, lab_id, project_id, participant_id):
        p = services.set_archived(
            self.item("participant_id"), self.archive, user=request.user, request=request
        )
        return Response(self.get_serializer(p).data)


class ParticipantRestoreView(ParticipantArchiveView):
    archive = False


class ParticipantEventsView(RegistryMixin):
    model = ParticipantEvent
    serializer_class = EventSerializer
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=EventSerializer(many=True))
    def get(self, request, lab_id, project_id, participant_id):
        qs = self.get_queryset().filter(participant_id=participant_id)[:200]
        return Response(self.get_serializer(qs, many=True).data)


# ---------------------------------------------------------------- columns


class ComponentListCreateView(RegistryMixin):
    model = Component
    serializer_class = ComponentSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_PROJECT}

    @extend_schema(responses=ComponentSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().filter(archived_at__isnull=True)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=ComponentInputSerializer, responses={201: ComponentSerializer})
    def post(self, request, lab_id, project_id):
        c = services.create_component(
            self.project,
            user=request.user,
            data=self.body(ComponentInputSerializer, code_fields=()),
            request=request,
        )
        return Response(self.get_serializer(c).data, status=status.HTTP_201_CREATED)


class ComponentDetailView(RegistryMixin):
    model = Component
    serializer_class = ComponentSerializer
    perms = {"PATCH": Perm.EDIT_PROJECT, "DELETE": Perm.EDIT_PROJECT}

    @extend_schema(request=ComponentInputSerializer, responses=ComponentSerializer)
    def patch(self, request, lab_id, project_id, component_id):
        c = services.update_component(
            self.item("component_id"),
            user=request.user,
            data=self.body(ComponentInputSerializer, partial=True, code_fields=()),
            request=request,
        )
        return Response(self.get_serializer(c).data)

    @extend_schema(
        responses={
            200: inline_serializer(
                "ParticipantColumnDeleted", {"cells_removed": serializers.IntegerField()}
            )
        }
    )
    def delete(self, request, lab_id, project_id, component_id):
        n = services.delete_component(self.item("component_id"), user=request.user, request=request)
        return Response({"cells_removed": n})


# ---------------------------------------------------------------- cells and links


class CellListView(RegistryMixin):
    model = ParticipantComponent
    serializer_class = CellSerializer
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=CellSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().prefetch_related("files", "task_links__task")
        return Response(self.get_serializer(qs, many=True).data)


class CellSetView(RegistryMixin):
    model = Participant
    serializer_class = CellSerializer
    perms = {"PATCH": Perm.EDIT_CONTENT}

    @extend_schema(request=CellInputSerializer, responses=CellSerializer)
    def patch(self, request, lab_id, project_id, participant_id, component_id):
        participant = self.item("participant_id")
        component = get_object_or_404(
            Component.objects.visible_to(request.user, request.lab).filter(project=self.project),
            pk=component_id,
        )
        cell = services.set_cell(
            participant,
            component,
            user=request.user,
            data=self.body(CellInputSerializer, code_fields=()),
            request=request,
        )
        cell = (
            ParticipantComponent.objects.visible_to(request.user, request.lab)
            .prefetch_related("files", "task_links__task")
            .get(pk=cell.pk)
        )
        return Response(self.get_serializer(cell).data)


class CellFileCreateView(RegistryMixin):
    model = ParticipantComponent
    serializer_class = FileSerializer
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(request=FileInputSerializer, responses={201: FileSerializer})
    def post(self, request, lab_id, project_id, cell_id):
        f = services.add_file(
            self.item("cell_id"),
            user=request.user,
            data=self.body(FileInputSerializer, code_fields=()),
            request=request,
        )
        return Response(self.get_serializer(f).data, status=status.HTTP_201_CREATED)


class FileDetailView(RegistryMixin):
    model = ComponentFile
    serializer_class = FileSerializer
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(request=FileInputSerializer, responses=FileSerializer)
    def patch(self, request, lab_id, project_id, file_id):
        f = services.update_file(
            self.item("file_id"),
            user=request.user,
            data=self.body(FileInputSerializer, partial=True, code_fields=()),
            request=request,
        )
        return Response(self.get_serializer(f).data)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, project_id, file_id):
        services.remove_file(self.item("file_id"), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- lab reasons


class ReasonMixin(LabScopedViewMixin):
    model = StatusReason
    serializer_class = ReasonSerializer
    pagination_class = None


class ReasonListCreateView(ReasonMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_LAB}

    @extend_schema(responses=ReasonSerializer(many=True))
    def get(self, request, lab_id):
        services.seed_reasons(request.lab)
        return Response(
            self.get_serializer(self.get_queryset().order_by("kind", "label"), many=True).data
        )

    @extend_schema(request=ReasonInputSerializer, responses={201: ReasonSerializer})
    def post(self, request, lab_id):
        ser = ReasonInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        services.guard(
            lab=request.lab,
            actor=request.user,
            data=ser.validated_data,
            request=request,
            code_fields=(),
        )
        r = services.save_reason(
            request.lab, user=request.user, data=ser.validated_data, request=request
        )
        return Response(self.get_serializer(r).data, status=status.HTTP_201_CREATED)


class ReasonDetailView(ReasonMixin, generics.GenericAPIView):
    perms = {"PATCH": Perm.MANAGE_LAB}

    @extend_schema(request=ReasonInputSerializer, responses=ReasonSerializer)
    def patch(self, request, lab_id, reason_id):
        r = get_object_or_404(self.get_queryset(), pk=reason_id)
        ser = ReasonInputSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        services.guard(
            lab=request.lab,
            actor=request.user,
            data=ser.validated_data,
            request=request,
            code_fields=(),
        )
        r = services.save_reason(
            request.lab, user=request.user, data=ser.validated_data, reason=r, request=request
        )
        return Response(self.get_serializer(r).data)


# ---------------------------------------------------------------- import, matching, link health


class ImportMixin(RegistryMixin):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"


class ImportPreviewView(ImportMixin):
    model = ImportRun
    serializer_class = ParticipantImportRunSerializer
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(
        request=ParticipantImportPreviewInputSerializer,
        responses=inline_serializer(
            "ParticipantImportPreview",
            {
                "headers": serializers.ListField(child=serializers.CharField()),
                "rows": serializers.ListField(
                    child=serializers.ListField(child=serializers.CharField())
                ),
                "total": serializers.IntegerField(),
                "blocked_headers": serializers.ListField(child=serializers.CharField()),
                "link_columns": serializers.ListField(child=serializers.CharField()),
            },
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = ParticipantImportPreviewInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(imports.preview(ser.validated_data["csv"]))


class ImportListCreateView(ImportMixin):
    model = ImportRun
    serializer_class = ParticipantImportRunSerializer
    perms = {"GET": Perm.EDIT_PROJECT, "POST": Perm.EDIT_PROJECT}

    @extend_schema(responses=ParticipantImportRunSerializer(many=True))
    def get(self, request, lab_id, project_id):
        runs = list(self.get_queryset()[:20])
        latest = next((r.pk for r in runs if r.undone_at is None), None)
        ser = ParticipantImportRunSerializer(runs, many=True, context={"latest": latest})
        return Response(ser.data)

    @extend_schema(
        request=ParticipantImportInputSerializer,
        responses=inline_serializer(
            "ParticipantImportResult",
            {
                "created": serializers.IntegerField(),
                "updated": serializers.IntegerField(),
                "skipped": serializers.IntegerField(),
                "links": serializers.IntegerField(),
                "components_created": serializers.IntegerField(),
                "attention": serializers.ListField(child=serializers.DictField()),
                "attention_total": serializers.IntegerField(),
                "dry_run": serializers.BooleanField(),
                "run": serializers.UUIDField(required=False),
            },
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = ParticipantImportInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        result = imports.run_import(
            self.project,
            request.user,
            text=d["csv"],
            mapping=d["mapping"],
            dry_run=d["dry_run"],
            source=d["source"],
            request=request,
        )
        return Response(result)


class ImportUndoView(ImportMixin):
    model = ImportRun
    serializer_class = ParticipantImportRunSerializer
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(request=None, responses=ParticipantImportRunSerializer)
    def post(self, request, lab_id, project_id, run_id):
        run = imports.undo_last(self.project, request.user, self.item("run_id"), request)
        return Response(ParticipantImportRunSerializer(run, context={"latest": None}).data)


class MatchFilesView(ImportMixin):
    model = ImportRun
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(
        request=ParticipantMatchInputSerializer,
        responses=inline_serializer(
            "ParticipantFileMatches",
            {"matches": serializers.ListField(child=serializers.DictField())},
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = ParticipantMatchInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        return Response({"matches": imports.match_files(self.project, d["files"], d["pattern"])})


class AttachFilesView(ImportMixin):
    model = ImportRun
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(
        request=ParticipantAttachInputSerializer,
        responses=inline_serializer(
            "ParticipantAttachResult",
            {"attached": serializers.IntegerField(), "skipped": serializers.IntegerField()},
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = ParticipantAttachInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        items = [
            dict(i, participant=str(i["participant"]), component=str(i["component"]))
            for i in ser.validated_data["items"]
        ]
        for it in items:
            services.guard(
                lab=request.lab, actor=request.user, data=it, request=request, code_fields=()
            )
        return Response(imports.attach_matches(self.project, request.user, items, request))


class LinkHealthView(RegistryMixin):
    model = ComponentFile
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(
        responses=inline_serializer(
            "ParticipantLinkHealth",
            {
                "counts": serializers.DictField(child=serializers.IntegerField()),
                "problems": serializers.ListField(child=serializers.DictField()),
                "changed": serializers.ListField(child=serializers.DictField()),
            },
        )
    )
    def get(self, request, lab_id, project_id):
        return Response(services.link_health(self.project))


class LinkRefreshView(RegistryMixin):
    model = ComponentFile
    perms = {"POST": Perm.EDIT_CONTENT}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(
        request=None,
        responses=inline_serializer(
            "ParticipantLinkRefresh",
            {"checked": serializers.IntegerField(), "problems": serializers.IntegerField()},
        ),
    )
    def post(self, request, lab_id, project_id):
        return Response(services.refresh_links(self.project, request.user, request=request))


class TaskGapsView(RegistryMixin):
    model = ParticipantComponent
    perms = {"POST": Perm.EDIT_CONTENT}

    @extend_schema(
        request=TaskGapsInputSerializer,
        responses=inline_serializer(
            "ParticipantTasksCreated",
            {
                "created": serializers.IntegerField(),
                "skipped": serializers.IntegerField(),
                "tasks": serializers.ListField(child=serializers.UUIDField()),
            },
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = TaskGapsInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        made, skipped = services.create_tasks(
            self.project,
            request.user,
            pairs=[(c["participant"], c["component"]) for c in d["cells"]],
            mode=d["mode"],
            assignee=str(d["assignee"]) if d.get("assignee") else None,
            due_date=d.get("due_date"),
            request=request,
        )
        return Response(
            {"created": len(made), "skipped": skipped, "tasks": [t.pk for t in made]},
            status=status.HTTP_201_CREATED,
        )


class LabOverviewView(LabScopedViewMixin, generics.GenericAPIView):
    model = Participant
    perms = {"GET": Perm.VIEW_LAB}
    pagination_class = None

    @extend_schema(
        responses=inline_serializer(
            "ParticipantOverview",
            {
                "projects": serializers.ListField(child=serializers.DictField()),
                "by_component": serializers.ListField(child=serializers.DictField()),
                "missing_by_reason": serializers.ListField(child=serializers.DictField()),
                "translation_pending": serializers.ListField(child=serializers.DictField()),
                "waiting_on_me": serializers.ListField(child=serializers.DictField()),
                "recent": serializers.ListField(child=serializers.DictField()),
            },
        )
    )
    def get(self, request, lab_id):
        return Response(overview.lab_overview(request.user, request.lab))


# ---------------------------------------------------------------- rules, locked sets, flow


class RuleListCreateView(RegistryMixin):
    model = InclusionRule
    serializer_class = RuleSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_PROJECT}

    @extend_schema(responses=RuleSerializer(many=True))
    def get(self, request, lab_id, project_id):
        qs = self.get_queryset().filter(archived_at__isnull=True).order_by("name")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=RuleInputSerializer, responses={201: RuleSerializer})
    def post(self, request, lab_id, project_id):
        r = rules.save_rule(
            self.project,
            request.user,
            data=self.body(RuleInputSerializer, code_fields=()),
            request=request,
        )
        return Response(self.get_serializer(r).data, status=status.HTTP_201_CREATED)


class RuleDetailView(RegistryMixin):
    model = InclusionRule
    serializer_class = RuleSerializer
    perms = {"PATCH": Perm.EDIT_PROJECT, "DELETE": Perm.EDIT_PROJECT}

    @extend_schema(request=RuleInputSerializer, responses=RuleSerializer)
    def patch(self, request, lab_id, project_id, rule_id):
        rule = self.item("rule_id")
        data = self.body(RuleInputSerializer, partial=True, code_fields=())
        return Response(
            self.get_serializer(
                rules.save_rule(self.project, request.user, data=data, rule=rule, request=request)
            ).data
        )

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, project_id, rule_id):
        rules.archive_rule(self.item("rule_id"), request.user, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RuleEvaluateView(RegistryMixin):
    model = InclusionRule
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(
        responses=inline_serializer(
            "ParticipantRuleResult",
            {
                "eligible": serializers.ListField(child=serializers.CharField()),
                "one_away": serializers.ListField(child=serializers.DictField()),
                "not_eligible": serializers.IntegerField(),
                "not_eligible_why": serializers.DictField(child=serializers.IntegerField()),
            },
        )
    )
    def get(self, request, lab_id, project_id, rule_id):
        out = rules.evaluate(self.project, self.item("rule_id").spec)
        out.pop("_people")
        return Response(out)


class SetListCreateView(RegistryMixin):
    model = AnalysisSet
    serializer_class = SetSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_PROJECT}

    @extend_schema(responses=SetSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=SetInputSerializer, responses={201: SetSerializer})
    def post(self, request, lab_id, project_id):
        d = self.body(SetInputSerializer, code_fields=())
        rule = get_object_or_404(
            InclusionRule.objects.visible_to(request.user, request.lab).filter(
                project=self.project, archived_at__isnull=True
            ),
            pk=d["rule"],
        )
        s = rules.lock_set(self.project, request.user, rule=rule, name=d["name"], request=request)
        return Response(self.get_serializer(s).data, status=status.HTTP_201_CREATED)


class SetDetailView(RegistryMixin):
    model = AnalysisSet
    serializer_class = SetSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_PROJECT}

    @extend_schema(
        responses=inline_serializer(
            "ParticipantSetDetail",
            {
                "set": SetSerializer(),
                "codes": serializers.ListField(child=serializers.CharField()),
                "changes": serializers.ListField(child=serializers.DictField()),
            },
        )
    )
    def get(self, request, lab_id, project_id, set_id):
        s = self.item("set_id")
        codes = sorted(
            Participant.objects.visible_to(request.user, request.lab)
            .filter(project=self.project, pk__in=s.participant_ids)
            .values_list("code", flat=True)
        )
        return Response(
            {
                "set": self.get_serializer(s).data,
                "codes": codes,
                "changes": rules.set_changes(self.project, s),
            }
        )

    @extend_schema(request=SetPatchSerializer, responses=SetSerializer)
    def patch(self, request, lab_id, project_id, set_id):
        s = self.item("set_id")
        d = self.body(SetPatchSerializer, code_fields=())
        analysis = None
        if d["analysis"] is not None:
            from provenance.models import Analysis

            analysis = get_object_or_404(
                Analysis.objects.visible_to(request.user, request.lab).filter(project=self.project),
                pk=d["analysis"],
            )
        s.analysis = analysis  # the only thing that may change on a locked set: what it fed
        s.save(update_fields=["analysis", "updated_at"])
        return Response(self.get_serializer(s).data)


class SetNewVersionView(RegistryMixin):
    model = AnalysisSet
    serializer_class = SetSerializer
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(request=None, responses={201: SetSerializer})
    def post(self, request, lab_id, project_id, set_id):
        s = rules.new_version(self.project, request.user, self.item("set_id"), request)
        return Response(self.get_serializer(s).data, status=status.HTTP_201_CREATED)


class FlowView(RegistryMixin):
    model = AnalysisSet
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(
        parameters=[OpenApiParameter("set", OpenApiTypes.UUID, description="A locked set")],
        responses=inline_serializer("ParticipantFlow", {"screened": serializers.DictField()}),
    )
    def get(self, request, lab_id, project_id):
        s = None
        if request.query_params.get("set"):
            s = get_object_or_404(self.get_queryset(), pk=request.query_params["set"])
        return Response(rules.flow(self.project, s))


class FlowExportView(RegistryMixin):
    """Logs that the summary was exported. The file itself is built in the browser from the
    counts above, so no row-level data ever leaves the server."""

    model = AnalysisSet
    perms = {"POST": Perm.EXPORT}

    @extend_schema(
        request=inline_serializer(
            "ParticipantFlowExport",
            {"kind": serializers.ChoiceField(choices=["table", "svg", "png"])},
        ),
        responses={204: None},
    )
    def post(self, request, lab_id, project_id):
        kind = request.data.get("kind")
        if kind not in ("table", "svg", "png"):
            raise serializers.ValidationError({"kind": "Choose table, svg or png."})
        rules.record_export(self.project, request.user, kind, request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RulePreviewView(RegistryMixin):
    """The live result while a rule is being written. Saves nothing."""

    model = InclusionRule
    perms = {"POST": Perm.VIEW_PROJECT}

    @extend_schema(
        request=RuleSpecSerializer,
        responses=inline_serializer(
            "ParticipantRulePreview",
            {
                "eligible": serializers.ListField(child=serializers.CharField()),
                "one_away": serializers.ListField(child=serializers.DictField()),
                "not_eligible": serializers.IntegerField(),
                "not_eligible_why": serializers.DictField(child=serializers.IntegerField()),
            },
        ),
    )
    def post(self, request, lab_id, project_id):
        ser = RuleSpecSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = rules.evaluate(self.project, ser.validated_data)
        except KeyError as exc:
            raise serializers.ValidationError({"requires": "That column does not exist."}) from exc
        out.pop("_people")
        return Response(out)
