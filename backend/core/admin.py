"""Django admin (DEBUG only, D41). Institution SSO is superuser-only (D153); production uses
`manage.py configure_sso`, which runs the same validation."""

from django.contrib import admin
from django.utils.html import format_html_join

from core.auth import sp_urls
from core.models import InstitutionSSO


@admin.register(InstitutionSSO)
class InstitutionSSOAdmin(admin.ModelAdmin):
    list_display = ("institution", "slug", "enabled", "require_sso", "updated_at")
    readonly_fields = ("service_provider",)

    @admin.display(description="Send these to the institution's IT (D155)")
    def service_provider(self, obj):
        if not obj.slug:
            return "Save first."
        return format_html_join("", "<div>{}: <code>{}</code></div>", sp_urls(obj.slug).items())

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    has_add_permission = has_view_permission
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission
