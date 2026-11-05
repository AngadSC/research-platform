from django.views.debug import SafeExceptionReporterFilter


class AlwaysCleanse(SafeExceptionReporterFilter):
    """Cleanse settings, `sensitive_variables` and `sensitive_post_parameters` even when DEBUG
    is on (Django's own filter switches itself off then)."""

    def is_active(self, request):
        return True
