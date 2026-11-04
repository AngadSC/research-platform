"""D53: enforce the attachment size limit while the body streams, so it does not depend on
Content-Length (a chunked upload has none). Runs before Django's spooling handlers."""

from django.conf import settings
from django.core.files.uploadhandler import FileUploadHandler
from rest_framework import status
from rest_framework.exceptions import APIException


class PayloadTooLarge(APIException):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    default_code = "payload_too_large"


class SizeLimitUploadHandler(FileUploadHandler):
    def new_file(self, *args, **kwargs):
        super().new_file(*args, **kwargs)
        self.received = 0

    def receive_data_chunk(self, raw_data, start):
        self.received += len(raw_data)
        if self.received > settings.ATTACHMENT_MAX_BYTES:
            limit = settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)
            raise PayloadTooLarge(f"File is too large ({limit} MB maximum).")
        return raw_data

    def file_complete(self, file_size):
        return None
