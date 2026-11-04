"""D50: reject an oversize upload from Content-Length, before anything reads the body."""

from django.conf import settings
from django.http import JsonResponse
from django.urls import Resolver404, resolve

UPLOAD_URL_NAMES = {"documents:attachment-list", "ethics:approval-attachments"}
MULTIPART_ALLOWANCE = 64 * 1024  # boundaries and form fields around the file


class UploadSizeLimitMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST":
            try:
                match = resolve(request.path_info)
            except Resolver404:
                match = None
            if match and f"{match.app_name}:{match.url_name}" in UPLOAD_URL_NAMES:
                try:
                    length = int(request.META.get("CONTENT_LENGTH") or 0)
                except ValueError:
                    length = 0
                if length > settings.ATTACHMENT_MAX_BYTES + MULTIPART_ALLOWANCE:
                    limit = settings.ATTACHMENT_MAX_BYTES // (1024 * 1024)
                    return JsonResponse(
                        {"detail": f"File is too large ({limit} MB maximum)."}, status=413
                    )
        return self.get_response(request)
