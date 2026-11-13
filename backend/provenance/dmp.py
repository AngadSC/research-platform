"""Data management plan (Run 5, D180 to D183): one plan per project in the Tri-Agency RDM / DMP
Assistant sections, a numbered revision after every save, approval by project leads."""

from django.db import transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import Perm
from core.serializers import UserSerializer
from documents.models import Attachment
from projects.views import ProjectScopedMixin
from provenance.models import (
    DMP_SECTIONS,
    DataManagementPlan,
    DataManagementPlanRevision,
    DmpStatus,
    validate_web_url,
)
from provenance.serializers import AttachmentRefSerializer

SNAPSHOT_FIELDS = (*DMP_SECTIONS, "status", "external_url")


# ---------------------------------------------------------------- serializers


class DmpSerializer(serializers.ModelSerializer):
    exists = serializers.SerializerMethodField()
    attachment = AttachmentRefSerializer(read_only=True)
    approved_by = UserSerializer(read_only=True)
    updated_by = UserSerializer(read_only=True)

    class Meta:
        model = DataManagementPlan
        fields = [
            "exists",
            *DMP_SECTIONS,
            "status",
            "last_reviewed",
            "external_url",
            "attachment",
            "approved_by",
            "approved_at",
            "updated_by",
            "updated_at",
        ]
        read_only_fields = fields

    def get_exists(self, obj) -> bool:
        return obj.created_at is not None


class DmpRevisionSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = DataManagementPlanRevision
        fields = ["id", "number", "snapshot", "created_by", "created_at"]
        read_only_fields = fields


class DmpInputSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[DmpStatus.DRAFT, DmpStatus.SUBMITTED], required=False)
    last_reviewed = serializers.DateField(allow_null=True, required=False)
    external_url = serializers.CharField(
        max_length=500, allow_blank=True, required=False, validators=[validate_web_url]
    )
    attachment = serializers.UUIDField(allow_null=True, required=False)
    data_description = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    collection = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    documentation = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    storage = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    preservation = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    sharing = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    responsibilities = serializers.CharField(allow_blank=True, required=False, max_length=20000)
    ethics_legal = serializers.CharField(allow_blank=True, required=False, max_length=20000)


# ---------------------------------------------------------------- services


def get_plan(project):
    """The saved plan, or an unsaved empty draft (a read writes nothing)."""
    plan = DataManagementPlan.objects.for_lab(project.lab_id).filter(project=project).first()
    return plan or DataManagementPlan(lab=project.lab, project=project)


def _revise(plan, user):
    last = plan.revisions.order_by("-number").values_list("number", flat=True).first() or 0
    snap = {f: getattr(plan, f) for f in SNAPSHOT_FIELDS}
    snap["last_reviewed"] = plan.last_reviewed.isoformat() if plan.last_reviewed else None
    shown = plan.attachment_id and not plan.attachment.pi_only  # D226: every member reads this
    snap["attachment"] = plan.attachment.original_filename if shown else None
    DataManagementPlanRevision.objects.create(
        lab=plan.lab, plan=plan, number=last + 1, snapshot=snap, created_by=user
    )


@transaction.atomic
def save_plan(*, project, user, data, request=None):
    data = dict(data)
    plan = (
        DataManagementPlan.objects.for_lab(project.lab_id)
        .select_for_update()
        .filter(project=project)
        .first()
    )
    created = plan is None
    plan = plan or DataManagementPlan(lab=project.lab, project=project)
    changed = []
    if "attachment" in data:
        pk = data.pop("attachment")
        att = None
        if pk is not None:
            att = (
                Attachment.objects.for_lab(project.lab_id)
                .filter(pk=pk, project=project, deleted_at__isnull=True)
                .first()
            )
            if att is None:
                raise ValidationError({"attachment": "This item does not exist in this project."})
        if (att and att.pk) != plan.attachment_id:
            changed.append("attachment")
        plan.attachment = att
    for key, value in data.items():
        if getattr(plan, key) != value:
            changed.append(key)
        setattr(plan, key, value)
    if plan.status == DmpStatus.APPROVED and changed:
        # D182: an approval vouches for the text that was approved; any change reopens it
        plan.status, plan.approved_by, plan.approved_at = DmpStatus.DRAFT, None, None
    plan.updated_by = user
    plan.save()
    _revise(plan, user)
    record(
        A.DMP_CREATED if created else A.DMP_UPDATED,
        actor=user,
        lab=project.lab,
        target=plan,
        request=request,
        metadata={"fields": sorted(changed)},
    )
    return plan


@transaction.atomic
def approve_plan(*, project, user, request=None):
    plan = (
        DataManagementPlan.objects.for_lab(project.lab_id)
        .select_for_update()
        .filter(project=project)
        .first()
    )
    if plan is None:
        raise ValidationError({"detail": "Save the plan before approving it."})
    plan.status, plan.approved_by, plan.approved_at = DmpStatus.APPROVED, user, timezone.now()
    plan.last_reviewed = timezone.localdate()
    plan.updated_by = user
    plan.save()
    _revise(plan, user)
    record(A.DMP_APPROVED, actor=user, lab=project.lab, target=plan, request=request)
    return plan


@transaction.atomic
def delete_plan(*, project, user, request=None):
    plan = DataManagementPlan.objects.for_lab(project.lab_id).filter(project=project).first()
    if plan is None:
        return
    record(
        A.DMP_DELETED,
        actor=user,
        lab=project.lab,
        target=plan,
        request=request,
        metadata={"status": plan.status},
    )
    plan.delete()


# ---------------------------------------------------------------- views


class DmpView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = DmpSerializer
    perms = {"GET": Perm.VIEW_PROJECT, "PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_PROJECT}

    @extend_schema(responses=DmpSerializer)
    def get(self, request, lab_id, project_id):
        return self.out(get_plan(self.project))

    @extend_schema(request=DmpInputSerializer, responses=DmpSerializer)
    def patch(self, request, lab_id, project_id):
        data = self.body(DmpInputSerializer, partial=True)
        plan = save_plan(project=self.project, user=request.user, data=data, request=request)
        return self.out(plan)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, project_id):
        delete_plan(project=self.project, user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DmpApproveView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = DmpSerializer
    perms = {"POST": Perm.EDIT_PROJECT}

    @extend_schema(request=None, responses=DmpSerializer)
    def post(self, request, lab_id, project_id):
        plan = approve_plan(project=self.project, user=request.user, request=request)
        return self.out(plan)


class DmpRevisionsView(ProjectScopedMixin, generics.GenericAPIView):
    serializer_class = DmpRevisionSerializer
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses=DmpRevisionSerializer(many=True))
    def get(self, request, lab_id, project_id):
        rows = (
            DataManagementPlanRevision.objects.for_lab(self.project.lab_id)
            .filter(plan__project=self.project)
            .select_related("created_by")
            .order_by("-number")
        )
        return Response(self.get_serializer(rows, many=True).data)
