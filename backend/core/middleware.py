"""D50: reject an oversize upload from Content-Length, before anything reads the body.
D291: dates follow the signed-in person's own time zone."""

import datetime
import zoneinfo

from django.conf import settings
from django.http import JsonResponse
from django.urls import Resolver404, resolve
from django.utils import timezone

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


def user_zone(user):
    """The time zone the person's browser last reported (`preferences.time_zone`), else UTC."""
    try:
        return zoneinfo.ZoneInfo((getattr(user, "preferences", None) or {}).get("time_zone"))
    except (TypeError, ValueError, KeyError):  # unset, malformed or unknown
        return datetime.UTC


class TimeZoneMiddleware:
    """A session request runs in its user's zone, so `timezone.localdate()` is their today and
    DRF writes datetimes in their offset. Must follow authentication. The connector (assistant.mcp)
    and the streamed in-app assistant set the zone themselves: neither runs inside this."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        with timezone.override(user_zone(request.user)):
            return self.get_response(request)
