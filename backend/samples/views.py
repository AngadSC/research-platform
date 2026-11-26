"""Sample registry and freezer boxes. Read with view_lab, write with manage_samples, and all of it
answers 403 while the lab has inventory turned off (D227), like inventory."""

import csv

from django.db.models import Count, Prefetch, Q
from django.http import Http404, HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from audit.models import AuditAction
from audit.services import record
from core.permissions import Perm, visible_projects
from core.views import LabScopedViewMixin
from documents.models import Attachment
from documents.serializers import AttachmentSerializer, AttachmentUploadSerializer
from documents.services import delete_attachment
from documents.views import download_response
from labs.admin_views import _safe_cell
from samples import services as svc
from samples.models import Sample, SampleKind, StorageBox, StorageUnit, Tube
from samples.serializers import (
    BoxDetailSerializer,
    BoxInputSerializer,
    SampleDetailSerializer,
    SampleImportInputSerializer,
    SampleImportResultSerializer,
    SampleInputSerializer,
    SampleSerializer,
    TubeInputSerializer,
    TubeSerializer,
    UnitInputSerializer,
    UnitSerializer,
)


def _body(serializer_class, request, partial=False):
    ser = serializer_class(data=request.data, partial=partial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


class SamplesMixin(LabScopedViewMixin):
    pagination_class = None
    needs_inventory = True  # D227: HasPerm answers 403 while the lab has inventory turned off


def _tubes(user, lab):
    return Prefetch(
        "tubes",
        queryset=Tube.objects.visible_to(user, lab)
        .select_related("box__unit", "owner")
        .order_by("box__unit__name", "box__name", "row", "col"),
    )


class SampleMixin(SamplesMixin):
    model = Sample
    serializer_class = SampleSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("owner")
            .prefetch_related(_tubes(self.request.user, self.request.lab))
        )

    def detail(self, sample, code=status.HTTP_200_OK):
        """Parents, children, projects and files, each limited to what the reader can see."""
        user, lab = self.request.user, self.request.lab
        sample = self.get_queryset().get(pk=sample.pk)
        seen = Sample.objects.visible_to(user, lab).order_by("code")
        context = {
            "parents": seen.filter(children=sample),
            "children": seen.filter(parents=sample),
            "projects": sample.projects.filter(
                pk__in=visible_projects(user, lab).filter(deleted_at__isnull=True).values("pk")
            ).order_by("name"),
            # D244: project files go through visible_to, which drops PI-only files and files in
            # projects the reader cannot see.
            "files": [
                *sample.attachments.filter(deleted_at__isnull=True).select_related("uploaded_by"),
                *sample.linked_files.filter(
                    deleted_at__isnull=True,
                    pk__in=Attachment.objects.visible_to(user, lab).values("pk"),
                ).select_related("uploaded_by", "project"),
            ],
        }
        return Response(SampleDetailSerializer(sample, context=context).data, status=code)


FILTER_PARAMS = [
    OpenApiParameter("q", str, description="Search code, name, description and the details"),
    OpenApiParameter("kind", str),
    OpenApiParameter("status", str),
    OpenApiParameter("owner", str, description="A user id"),
]
SEARCHED = ["code", "name", "description", "backbone", "insert", "species", "genotype", "tag"]


def _filtered(qs, params):
    if q := params.get("q", "").strip():
        cond = Q()
        for f in SEARCHED:
            cond |= Q(**{f"{f}__icontains": q})
        qs = qs.filter(cond)
    for f in ("kind", "status"):
        if v := params.get(f):
            qs = qs.filter(**{f: v})
    if owner := params.get("owner"):
        try:
            qs = qs.filter(owner_id=serializers.UUIDField().to_internal_value(owner))
        except serializers.ValidationError:
            qs = qs.none()
    return qs.order_by("kind", "code", "id")


class SampleListCreateView(SampleMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_SAMPLES}

    @extend_schema(parameters=FILTER_PARAMS, responses=SampleSerializer(many=True))
    def get(self, request, lab_id):
        qs = _filtered(self.get_queryset(), request.query_params)
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(request=SampleInputSerializer, responses={201: SampleDetailSerializer})
    def post(self, request, lab_id):
        sample = svc.create_sample(
            lab=request.lab,
            user=request.user,
            data=_body(SampleInputSerializer, request),
            request=request,
        )
        return self.detail(sample, status.HTTP_201_CREATED)


class SampleDetailView(SampleMixin, generics.GenericAPIView):
    lookup_url_kwarg = "sample_id"
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_SAMPLES, "DELETE": Perm.MANAGE_SAMPLES}

    @extend_schema(responses=SampleDetailSerializer)
    def get(self, request, lab_id, sample_id):
        return self.detail(self.get_object())

    @extend_schema(request=SampleInputSerializer, responses=SampleDetailSerializer)
    def patch(self, request, lab_id, sample_id):
        sample = svc.update_sample(
            self.get_object(),
            user=request.user,
            data=_body(SampleInputSerializer, request, True),
            request=request,
        )
        return self.detail(sample)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, sample_id):
        svc.delete_sample(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NextCodesView(SamplesMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(
        responses=inline_serializer(
            "SampleNextCodes", {k.value: serializers.CharField() for k in SampleKind}
        )
    )
    def get(self, request, lab_id):
        return Response(svc.next_codes(request.lab))


EXPORT_HEADER = ["Code", "Kind", "Name", "Description", "Status", "Owner", "Backbone", "Insert"]
EXPORT_HEADER += ["Resistance", "Tag", "Species", "Genotype", "Sequence", "Concentration"]
EXPORT_HEADER += ["Buffer", "Made on", "Parents", "Tubes"]


class SampleExportView(SampleMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(parameters=FILTER_PARAMS, responses=OpenApiTypes.BINARY)
    def get(self, request, lab_id):
        seen = Sample.objects.visible_to(request.user, request.lab)
        qs = _filtered(self.get_queryset(), request.query_params).prefetch_related(
            Prefetch("parents", queryset=seen.order_by("code"), to_attr="seen_parents")
        )
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = 'attachment; filename="samples.csv"'
        resp.write("﻿")  # so Excel reads the file as UTF-8
        w = csv.writer(resp)
        w.writerow(EXPORT_HEADER)
        count = 0
        for s in qs:
            owner = (s.owner.display_name or s.owner.email) if s.owner else ""
            row = [s.code, SampleKind(s.kind).label, s.name, s.description, s.status, owner]
            row += [s.backbone, s.insert, s.resistance, s.tag, s.species, s.genotype, s.sequence]
            row += [s.concentration, s.buffer, s.made_on]
            row += [" ".join(p.code for p in s.seen_parents)]
            row += [
                "; ".join(f"{t.box.unit.name} / {t.box.name} {t.position}" for t in s.tubes.all())
            ]
            w.writerow(_safe_cell(v) for v in row)
            count += 1
        record(
            AuditAction.SAMPLES_EXPORTED,
            actor=request.user,
            lab=request.lab,
            request=request,
            metadata={"rows": count},
        )
        return resp


class SampleImportView(SamplesMixin, generics.GenericAPIView):
    """Post a CSV to preview it; post the same file with commit=true to add every row."""

    parser_classes = [MultiPartParser, FormParser]
    perms = {"POST": Perm.MANAGE_SAMPLES}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(request=SampleImportInputSerializer, responses=SampleImportResultSerializer)
    def post(self, request, lab_id):
        data = _body(SampleImportInputSerializer, request)
        read = svc.read_file(request.lab, data["file"])
        ready = read.pop("_ready")
        if data["commit"]:
            if read["invalid"]:  # no partial import: fix the file and try again
                return Response(read, status=status.HTTP_400_BAD_REQUEST)
            read["imported"] = svc.import_samples(
                lab=request.lab, user=request.user, ready=ready, request=request
            )
        return Response(SampleImportResultSerializer(read).data)


class SampleFilesView(SampleMixin, generics.GenericAPIView):
    """Upload a map, gel image or other file onto the sample; every lab member can open it."""

    lookup_url_kwarg = "sample_id"
    parser_classes = [MultiPartParser, FormParser]
    perms = {"POST": Perm.MANAGE_SAMPLES}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, sample_id):
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attachment = svc.upload_file(
            self.get_object(),
            user=request.user,
            file=ser.validated_data.get("file"),
            drive_file_id=ser.validated_data.get("drive_file_id"),
            request=request,
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


class SampleFileView(SampleMixin, generics.GenericAPIView):
    """GET streams one of the sample's own uploads (audited); DELETE removes it (soft)."""

    lookup_url_kwarg = "sample_id"
    perms = {"GET": Perm.VIEW_LAB, "DELETE": Perm.MANAGE_SAMPLES}

    def attachment(self):
        a = (
            self.get_object()
            .attachments.filter(pk=self.kwargs["samplefile_id"], deleted_at__isnull=True)
            .first()
        )
        if a is None:
            raise Http404
        return a

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, lab_id, sample_id, samplefile_id):
        return download_response(request, self.attachment())

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, sample_id, samplefile_id):
        delete_attachment(self.attachment(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- storage


def _boxes(user, lab):
    return Prefetch(
        "boxes",
        queryset=StorageBox.objects.visible_to(user, lab)
        .annotate(filled=Count("tubes"))
        .order_by("name", "id"),
    )


class UnitMixin(SamplesMixin):
    model = StorageUnit
    serializer_class = UnitSerializer

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("equipment")
            .prefetch_related(_boxes(self.request.user, self.request.lab))
            .order_by("name", "id")
        )

    def out(self, unit, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=unit.pk)).data, status=code)


class UnitListCreateView(UnitMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_SAMPLES}

    @extend_schema(responses=UnitSerializer(many=True))
    def get(self, request, lab_id):
        return Response(self.get_serializer(self.get_queryset(), many=True).data)

    @extend_schema(request=UnitInputSerializer, responses={201: UnitSerializer})
    def post(self, request, lab_id):
        unit = svc.create_unit(
            lab=request.lab,
            user=request.user,
            data=_body(UnitInputSerializer, request),
            request=request,
        )
        return self.out(unit, status.HTTP_201_CREATED)


class UnitDetailView(UnitMixin, generics.GenericAPIView):
    lookup_url_kwarg = "storageunit_id"
    perms = {"PATCH": Perm.MANAGE_SAMPLES, "DELETE": Perm.MANAGE_SAMPLES}

    @extend_schema(request=UnitInputSerializer, responses=UnitSerializer)
    def patch(self, request, lab_id, storageunit_id):
        unit = svc.update_unit(
            self.get_object(),
            user=request.user,
            data=_body(UnitInputSerializer, request, True),
            request=request,
        )
        return self.out(unit)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, storageunit_id):
        svc.delete_unit(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BoxMixin(SamplesMixin):
    model = StorageBox
    serializer_class = BoxDetailSerializer

    def get_queryset(self):
        tubes = Tube.objects.visible_to(self.request.user, self.request.lab)
        tubes = tubes.select_related("sample", "owner")
        return (
            super()
            .get_queryset()
            .select_related("unit")
            .annotate(filled=Count("tubes"))
            .prefetch_related(Prefetch("tubes", queryset=tubes.order_by("row", "col")))
        )

    def out(self, box, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=box.pk)).data, status=code)


class BoxCreateView(BoxMixin, generics.GenericAPIView):
    perms = {"POST": Perm.MANAGE_SAMPLES}

    @extend_schema(request=BoxInputSerializer, responses={201: BoxDetailSerializer})
    def post(self, request, lab_id):
        box = svc.create_box(
            lab=request.lab,
            user=request.user,
            data=_body(BoxInputSerializer, request),
            request=request,
        )
        return self.out(box, status.HTTP_201_CREATED)


class BoxDetailView(BoxMixin, generics.GenericAPIView):
    """The grid: every tube in the box with its sample."""

    lookup_url_kwarg = "storagebox_id"
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_SAMPLES, "DELETE": Perm.MANAGE_SAMPLES}

    @extend_schema(responses=BoxDetailSerializer)
    def get(self, request, lab_id, storagebox_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=BoxInputSerializer, responses=BoxDetailSerializer)
    def patch(self, request, lab_id, storagebox_id):
        box = svc.update_box(
            self.get_object(),
            user=request.user,
            data=_body(BoxInputSerializer, request, True),
            request=request,
        )
        return self.out(box)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, storagebox_id):
        svc.delete_box(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TubeMixin(SamplesMixin):
    model = Tube
    serializer_class = TubeSerializer

    def get_queryset(self):
        return super().get_queryset().select_related("sample", "owner", "box")

    def out(self, tube, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=tube.pk)).data, status=code)


class TubeCreateView(TubeMixin, generics.GenericAPIView):
    perms = {"POST": Perm.MANAGE_SAMPLES}

    @extend_schema(request=TubeInputSerializer, responses={201: TubeSerializer})
    def post(self, request, lab_id):
        tube = svc.place_tube(
            lab=request.lab,
            user=request.user,
            data=_body(TubeInputSerializer, request),
            request=request,
        )
        return self.out(tube, status.HTTP_201_CREATED)


class TubeDetailView(TubeMixin, generics.GenericAPIView):
    """PATCH box, row or col to move it; DELETE takes it out of storage."""

    lookup_url_kwarg = "tube_id"
    perms = {"PATCH": Perm.MANAGE_SAMPLES, "DELETE": Perm.MANAGE_SAMPLES}

    @extend_schema(request=TubeInputSerializer, responses=TubeSerializer)
    def patch(self, request, lab_id, tube_id):
        tube = svc.update_tube(
            self.get_object(),
            user=request.user,
            data=_body(TubeInputSerializer, request, True),
            request=request,
        )
        return self.out(tube)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, tube_id):
        svc.remove_tube(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
