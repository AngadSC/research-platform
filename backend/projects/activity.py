"""D139: `Project.last_activity_at/by`, the "Last edited" line on the overview.

Any save of a project or of lab data that belongs to one, made while a signed-in user's request
is being served, stamps that project. Jobs, imports and shell saves carry no request and leave
it alone. Project content is visible to everyone who can see the project, so the stored value
needs no per-viewer filtering. ponytail: deletes are not stamped (post_delete has no cheap
"who"); add a post_delete receiver if "removed a task" should count."""

from contextvars import ContextVar

from django.db.models.signals import post_save
from django.utils import timezone

from core.tenancy import LabScopedModel

_request: ContextVar = ContextVar("activity_request", default=None)


class ActivityMiddleware:
    """Remembers the request for the duration of the response. Must follow authentication."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        token = _request.set(request)
        try:
            return self.get_response(request)
        finally:
            _request.reset(token)


def _project_id(instance):
    from projects.models import Project

    if isinstance(instance, Project):
        return instance.pk
    path = getattr(instance, "project_path", None)
    if not path:
        return None
    obj = instance
    for part in path.split("__"):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj.pk


def stamp(sender, instance, **kwargs):
    if not isinstance(instance, LabScopedModel) or getattr(instance, "not_an_edit", False):
        return
    request = _request.get()
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return
    project_id = _project_id(instance)
    if project_id is None:
        return
    from projects.models import Project

    Project.objects.for_lab(instance.lab_id).filter(pk=project_id).update(
        last_activity_at=timezone.now(), last_activity_by=user
    )


def connect():
    post_save.connect(stamp, dispatch_uid="project_last_activity")
