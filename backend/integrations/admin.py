"""Read-only admin (DEBUG only, superuser). Token ciphertext fields are `editable=False` and
listed nowhere here, so neither plaintext nor ciphertext is ever rendered."""

from django.contrib import admin

from integrations.models import ConnectedAccount, ExternalLink


class _ReadOnly(admin.ModelAdmin):
    def get_queryset(self, request):
        return self.model.unscoped.all()  # admin.py may use unscoped (D18)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ConnectedAccount)
class ConnectedAccountAdmin(_ReadOnly):
    list_display = ("provider", "external_email", "user", "lab", "status", "last_used_at")
    list_filter = ("provider", "status")
    fields = (
        "lab",
        "user",
        "provider",
        "external_account_id",
        "external_email",
        "instance_url",
        "granted_scopes",
        "status",
        "token_expires_at",
        "connected_at",
        "last_used_at",
    )


@admin.register(ExternalLink)
class ExternalLinkAdmin(_ReadOnly):
    list_display = ("title", "provider", "project", "lab", "linked_by", "last_checked_at")
    list_filter = ("provider",)
