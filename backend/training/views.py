"""Training endpoints (D175-D179), all under /api/labs/<lab_id>/training/.

Requirements are readable by every lab member (so "My training" can name them) and managed with
manage_training. Records are scoped by `TrainingRecord.visible_rows`: the owner's own, or all of
them for manage_training; anyone else gets 404 (D21, D176)."""

import uuid

from django.http import Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm
from core.views import LabScopedViewMixin
from documents.serializers import AttachmentSerializer, AttachmentUploadSerializer
from documents.views import download_response
from training import services
from training.models import TrainingRecord, TrainingRequirement
from training.serializers import (
    ExpiringSerializer,
    TrainingComplianceSerializer,
    TrainingRecordCreateSerializer,
    TrainingRecordSerializer,
    TrainingRecordUpdateSerializer,
    TrainingRequirementInputSerializer,
    TrainingRequirementSerializer,
)


def _body(serializer_class, request, partial=False):
    ser = serializer_class(data=request.data, partial=partial)
    ser.is_valid(raise_exception=True)
    return ser.validated_data


# ---------------------------------------------------------------- requirements


class RequirementMixin(LabScopedViewMixin):
    model = TrainingRequirement
    serializer_class = TrainingRequirementSerializer
    pagination_class = None

    def get_queryset(self):
        return super().get_queryset().prefetch_related("projects")

    def out(self, req, code=status.HTTP_200_OK):
        fresh = self.get_queryset().get(pk=req.pk)  # re-read: prefetched links are stale
        return Response(self.get_serializer(fresh).data, status=code)


class RequirementListCreateView(RequirementMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.MANAGE_TRAINING}

    @extend_schema(responses=TrainingRequirementSerializer(many=True))
    def get(self, request, lab_id):
        qs = self.get_queryset().order_by("name", "id")
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        request=TrainingRequirementInputSerializer, responses={201: TrainingRequirementSerializer}
    )
    def post(self, request, lab_id):
        req = services.create_requirement(
            lab=request.lab,
            user=request.user,
            data=_body(TrainingRequirementInputSerializer, request),
            request=request,
        )
        return self.out(req, status.HTTP_201_CREATED)


class RequirementDetailView(RequirementMixin, generics.GenericAPIView):
    lookup_url_kwarg = "trainingrequirement_id"
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.MANAGE_TRAINING, "DELETE": Perm.MANAGE_TRAINING}

    @extend_schema(responses=TrainingRequirementSerializer)
    def get(self, request, lab_id, trainingrequirement_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(
        request=TrainingRequirementInputSerializer, responses=TrainingRequirementSerializer
    )
    def patch(self, request, lab_id, trainingrequirement_id):
        req = services.update_requirement(
            self.get_object(),
            user=request.user,
            data=_body(TrainingRequirementInputSerializer, request, True),
            request=request,
        )
        return self.out(req)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, trainingrequirement_id):
        services.delete_requirement(self.get_object(), user=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------- records


class RecordMixin(LabScopedViewMixin):
    model = TrainingRecord
    serializer_class = TrainingRecordSerializer
    pagination_class = None

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(deleted_at__isnull=True)
            .select_related("user", "requirement", "verified_by")
            .prefetch_related("attachments")
        )

    def out(self, rec, code=status.HTTP_200_OK):
        return Response(self.get_serializer(self.get_queryset().get(pk=rec.pk)).data, status=code)


def _uuid_or_none(value):
    try:
        return uuid.UUID(value)
    except (TypeError, ValueError):
        return None


class RecordListCreateView(RecordMixin, generics.GenericAPIView):
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}  # the service checks "for someone else"

    @extend_schema(
        parameters=[
            OpenApiParameter("user", OpenApiTypes.UUID, description="Only this member's records"),
            OpenApiParameter("requirement", OpenApiTypes.UUID),
        ],
        responses=TrainingRecordSerializer(many=True),
    )
    def get(self, request, lab_id):
        qs = self.get_queryset().order_by("-completed_on", "-created_at", "id")
        for param in ("user", "requirement"):
            if value := request.query_params.get(param):
                qs = qs.filter(**{f"{param}_id": _uuid_or_none(value)})
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        request=TrainingRecordCreateSerializer, responses={201: TrainingRecordSerializer}
    )
    def post(self, request, lab_id):
        rec = services.create_record(
            lab=request.lab,
            actor=request.user,
            data=_body(TrainingRecordCreateSerializer, request),
            request=request,
        )
        return self.out(rec, status.HTTP_201_CREATED)


class RecordDetailView(RecordMixin, generics.GenericAPIView):
    lookup_url_kwarg = "trainingrecord_id"
    perms = {"GET": Perm.VIEW_LAB, "PATCH": Perm.VIEW_LAB, "DELETE": Perm.VIEW_LAB}

    @extend_schema(responses=TrainingRecordSerializer)
    def get(self, request, lab_id, trainingrecord_id):
        return Response(self.get_serializer(self.get_object()).data)

    @extend_schema(request=TrainingRecordUpdateSerializer, responses=TrainingRecordSerializer)
    def patch(self, request, lab_id, trainingrecord_id):
        rec = services.update_record(
            self.get_object(),
            actor=request.user,
            data=_body(TrainingRecordUpdateSerializer, request, True),
            request=request,
        )
        return self.out(rec)

    @extend_schema(responses={204: None})
    def delete(self, request, lab_id, trainingrecord_id):
        services.delete_record(self.get_object(), actor=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RecordVerifyView(RecordMixin, generics.GenericAPIView):
    lookup_url_kwarg = "trainingrecord_id"
    perms = {"POST": Perm.MANAGE_TRAINING}

    @extend_schema(request=None, responses=TrainingRecordSerializer)
    def post(self, request, lab_id, trainingrecord_id):
        rec = services.verify_record(self.get_object(), actor=request.user, request=request)
        return self.out(rec)


class RecordCertificateView(RecordMixin, generics.GenericAPIView):
    """The certificate is served through its record (D175), never the project attachment routes:
    the same scoping as the record, so only its owner and managers can reach it."""

    lookup_url_kwarg = "trainingrecord_id"
    parser_classes = [MultiPartParser, FormParser]
    perms = {"GET": Perm.VIEW_LAB, "POST": Perm.VIEW_LAB}
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"

    def get_throttles(self):
        return super().get_throttles() if self.request.method == "POST" else []

    @extend_schema(responses={(200, "application/octet-stream"): bytes})
    def get(self, request, lab_id, trainingrecord_id):
        attachment = services.live_certificate(self.get_object())
        if attachment is None:
            raise Http404
        return download_response(request, attachment)

    @extend_schema(request=AttachmentUploadSerializer, responses={201: AttachmentSerializer})
    def post(self, request, lab_id, trainingrecord_id):
        ser = AttachmentUploadSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attachment = services.upload_certificate(
            self.get_object(), actor=request.user, file=ser.validated_data["file"], request=request
        )
        return Response(AttachmentSerializer(attachment).data, status=status.HTTP_201_CREATED)


# ---------------------------------------------------------------- compliance


class ComplianceView(LabScopedViewMixin, generics.GenericAPIView):
    """Members by required trainings (D177). Only people who manage training see everyone."""

    serializer_class = TrainingComplianceSerializer
    perms = {"GET": Perm.MANAGE_TRAINING}

    @extend_schema(responses=TrainingComplianceSerializer)
    def get(self, request, lab_id):
        return Response(TrainingComplianceSerializer(services.compliance(request.lab)).data)


class MyTrainingView(LabScopedViewMixin, generics.GenericAPIView):
    """The same shape, for the requester alone."""

    serializer_class = TrainingComplianceSerializer
    perms = {"GET": Perm.VIEW_LAB}

    @extend_schema(responses=TrainingComplianceSerializer)
    def get(self, request, lab_id):
        data = services.compliance(request.lab, user=request.user)
        return Response(TrainingComplianceSerializer(data).data)


class ExpiringView(LabScopedViewMixin, generics.GenericAPIView):
    """Expired items plus those expiring within `days` (default 60): the PI dashboard's
    "Training expiring" card (D178)."""

    serializer_class = ExpiringSerializer
    perms = {"GET": Perm.MANAGE_TRAINING}

    @extend_schema(
        parameters=[OpenApiParameter("days", OpenApiTypes.INT, description="1 to 365, default 60")],
        responses=ExpiringSerializer,
    )
    def get(self, request, lab_id):
        raw = request.query_params.get("days", str(services.EXPIRING_DAYS))
        if not raw.isdigit() or not 1 <= int(raw) <= 365:
            raise ValidationError({"days": "Enter a number of days from 1 to 365."})
        items = services.expiring(request.lab, int(raw))
        body = {
            "days": int(raw),
            "count": len(items),
            "expired_count": sum(i["status"] == services.EXPIRED for i in items),
            "items": items,
        }
        return Response(ExpiringSerializer(body).data)
