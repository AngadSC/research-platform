from django.apps import AppConfig
from django.db.models.signals import post_save


def _on_user_saved(sender, instance, **kwargs):
    """Deactivation, however it happens (admin, shell, a future endpoint), unassigns their
    open tasks. Bulk `QuerySet.update(is_active=False)` skips signals; use save()."""
    if not instance.is_active:
        from integrations.services import revoke_member_accounts
        from labs.models import Lab
        from projects.services import unassign_lost_access

        # ponytail: one indexed query per lab; add a cross-lab lookup if labs get numerous.
        for lab in Lab.objects.all():
            unassign_lost_access(instance, lab=lab, reason="user_deactivated")
            # D68: their connected accounts go too, in this transaction.
            revoke_member_accounts(lab, instance, reason="user_deactivated")


class ProjectsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "projects"

    def ready(self):
        from django.conf import settings

        from projects import activity

        activity.connect()
        post_save.connect(
            _on_user_saved, sender=settings.AUTH_USER_MODEL, dispatch_uid="unassign_on_deactivate"
        )
