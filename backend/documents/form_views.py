from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import generics, serializers
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from core.permissions import Perm
from core.views import LabScopedViewMixin
from documents import form_reader
from papers.pdftext import PdfTextError


class FormReadInputSerializer(serializers.Serializer):
    file = serializers.FileField()


class FormReadSerializer(serializers.Serializer):
    fields = serializers.DictField(child=serializers.CharField())


class FormReaderView(LabScopedViewMixin, generics.GenericAPIView):
    """Suggests the fields of an ethics or funding record from a form's text. Stateless: the file
    is read and dropped, nothing is saved, and no outside service sees it. The person checks the
    suggestions on the form before saving. Same permission as creating that record."""

    serializer_class = FormReadInputSerializer
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "uploads"
    kind = ""

    @extend_schema(request=FormReadInputSerializer, responses=FormReadSerializer)
    def post(self, request, lab_id):
        ser = FormReadInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        file = ser.validated_data["file"]
        if file.size > settings.ATTACHMENT_MAX_BYTES:
            raise serializers.ValidationError({"file": "File is too large (50 MB maximum)."})
        try:
            out = form_reader.read_form(file.read(), file.name, self.kind)
        except (PdfTextError, ValueError) as e:
            raise serializers.ValidationError({"file": str(e)}) from None
        return Response(out)


class EthicsFormReaderView(FormReaderView):
    kind = "ethics"
    perms = {"POST": Perm.EDIT_ETHICS}


class FundingFormReaderView(FormReaderView):
    kind = "funding"
    perms = {"POST": Perm.ACCESS_FUNDING}  # D226: funding is for PIs only
