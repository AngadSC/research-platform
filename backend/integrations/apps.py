from django.apps import AppConfig


class IntegrationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "integrations"

    def ready(self):
        from integrations import crypto, webhooks  # noqa: F401 - webhooks connects its signal

        crypto.fernet()  # fail at startup, not at first use, if the keys are missing or malformed
