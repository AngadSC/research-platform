from django.apps import AppConfig, apps


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        from core import auth  # noqa: F401  (connects the audit receivers)
        from core.tenancy import connect_m2m_checks

        connect_m2m_checks(apps.get_models())
