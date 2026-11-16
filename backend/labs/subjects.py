"""What a project studies when it is not people (D329): animals and cohorts, microbial strains,
cell lines and samples. A person is never a subject here: people are participants, with coded
IDs and their own rules. Reading needs view_project, writing edit_content."""

import csv

from django.db import IntegrityError, transaction
from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.models import AuditAction as A
from audit.services import record
from core.permissions import Perm
from core.serializers import UserSerializer, no_control_chars
from labs.models import Subject, SubjectKind, SubjectStatus
from projects.views import ProjectScopedMixin

FIELDS = [
    "kind",
    "code",
    "species",
    "line",
    "genotype",
    "sex",
    "count",
    "source",
    "start_date",
    "passage",
    "location",
    "status",
    "approval",
    "notes",
]


class SubjectSerializer(serializers.ModelSerializer):
    created_by = UserSerializer(read_only=True)

    class Meta:
        model = Subject
        fields = ["id", *FIELDS, "created_by", "created_at", "updated_at"]
        read_only_fields = fields


def _text(max_length, **kw):
    return serializers.CharField(
        max_length=max_length, allow_blank=True, required=False, validators=[no_control_chars], **kw
    )


class SubjectInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=SubjectKind.choices)
    code = serializers.CharField(max_length=60, validators=[no_control_chars])
    species = _text(120)
    line = _text(160)
    genotype = _text(300)
    sex = _text(16)
    count = serializers.IntegerField(min_value=1, max_value=100000, required=False)
    source = _text(200)
    start_date = serializers.DateField(allow_null=True, required=False)
    passage = _text(40)
    location = _text(200)
    status = serializers.ChoiceField(choices=SubjectStatus.choices, required=False)
    approval = _text(120)
    notes = serializers.CharField(max_length=5000, allow_blank=True, required=False)


def _taken(code):
    return ValidationError({"code": f'"{code}" is already used in this project. Pick another.'})


@transaction.atomic
def create_subject(*, project, user, data, request=None) -> Subject:
    data = {**data, "code": data["code"].strip()}
    if not data["code"]:
        raise ValidationError({"code": "Give it a label."})
    try:
        with transaction.atomic():
            subject = Subject.objects.create(
                lab=project.lab, project=project, created_by=user, **data
            )
    except IntegrityError:
        raise _taken(data["code"]) from None
    record(
        A.SUBJECT_CREATED,
        actor=user,
        lab=project.lab,
        target=subject,
        request=request,
        metadata={"kind": subject.kind, "project": str(project.pk)},
    )
    return subject


@transaction.atomic
def update_subject(subject, *, user, data, request=None) -> Subject:
    if "code" in data:
        data["code"] = data["code"].strip()
        if not data["code"]:
            raise ValidationError({"code": "Give it a label."})
    for key, value in data.items():
        setattr(subject, key, value)
    try:
        with transaction.atomic():
            subject.save()
    except IntegrityError:
        raise _taken(subject.code) from None
    record(
        A.SUBJECT_UPDATED,
        actor=user,
        lab=subject.lab,
        target=subject,
        request=request,
        metadata={"fields": sorted(data), "project": str(subject.project_id)},
    )
    return subject


@transaction.atomic
def delete_subject(subject, *, user, request=None) -> None:
    record(
        A.SUBJECT_DELETED,
        actor=user,
        lab=subject.lab,
        target=subject,
        request=request,
        metadata={"kind": subject.kind, "project": str(subject.project_id)},
    )
    subject.delete()


class _SubjectMixin(ProjectScopedMixin, generics.GenericAPIView):
    model = Subject
    serializer_class = SubjectSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("created_by").order_by("code", "id")


class SubjectListCreateView(_SubjectMixin):
    nested = True
    perms = {"GET": Perm.VIEW_PROJECT, "POST": Perm.EDIT_CONTENT}

    @extend_schema(responses=SubjectSerializer(many=True))
    def get(self, request, lab_id, project_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=SubjectInputSerializer, responses={201: SubjectSerializer})
    def post(self, request, lab_id, project_id):
        subject = create_subject(
            project=self.project,
            user=request.user,
            data=dict(self.body(SubjectInputSerializer)),
            request=request,
        )
        return self.out(self.get_queryset().get(pk=subject.pk), status.HTTP_201_CREATED)


class SubjectDetailView(_SubjectMixin):
    lookup_url_kwarg = "subject_id"
    perms = {"PATCH": Perm.EDIT_CONTENT, "DELETE": Perm.EDIT_CONTENT}

    @extend_schema(request=SubjectInputSerializer, responses=SubjectSerializer)
    def patch(self, request, lab_id, subject_id):
        subject = update_subject(
            self.get_object(),
            user=request.user,
            data=dict(self.body(SubjectInputSerializer, partial=True)),
            request=request,
        )
        return self.out(self.get_queryset().get(pk=subject.pk))

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, subject_id):
        delete_subject(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


def _safe(value):
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


class SubjectExportView(_SubjectMixin):
    """A spreadsheet of the project's subjects, for a methods section or a regulator."""

    nested = True
    perms = {"GET": Perm.VIEW_PROJECT}

    @extend_schema(responses={(200, "text/csv"): bytes})
    def get(self, request, lab_id, project_id):
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="subjects.csv"'
        w = csv.writer(resp)
        w.writerow(FIELDS)
        for s in self.get_queryset():
            w.writerow(_safe(getattr(s, f)) for f in FIELDS)
        return resp
