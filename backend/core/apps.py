from django.apps import AppConfig, apps


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from django.db import models
        from rest_framework.serializers import ModelSerializer

        from core import auth  # noqa: F401  (connects the audit receivers)
        from core.serializers import SaneDateTimeField
        from core.tenancy import connect_m2m_checks

        connect_m2m_checks(apps.get_models())
        ModelSerializer.serializer_field_mapping[models.DateTimeField] = SaneDateTimeField
