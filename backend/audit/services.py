import ipaddress

from django.conf import settings

from audit.models import AuditAction, AuditEvent
from core.tenancy import project_of


def _client_ip(request) -> str | None:
    raw = request.META.get("REMOTE_ADDR", "")
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies > 0:
        hops = [
            h.strip() for h in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if h.strip()
        ]
        if len(hops) >= proxies:
            raw = hops[-proxies]
    try:
        return str(ipaddress.ip_address(raw))
    except ValueError:
        return None


def record(
    action,
    *,
    actor,
    lab,
    target=None,
    request=None,
    metadata=None,
    actor_label="",
) -> AuditEvent:
    """Write one audit event. Call inside the caller's transaction (ARCHITECTURE §4)."""
    action = AuditAction(action)  # unknown action raises ValueError
    if lab is None and not action.value.startswith("auth."):
        raise ValueError("lab may be None only for auth.* actions")
    fields = {}
    if target is not None:
        project = project_of(target)
        fields = {
            "target_type": target._meta.label,
            "target_id": target.pk,
            "target_repr": str(target)[:200],
            "project_id": project.pk if project is not None else None,
        }
    if request is not None:
        fields["ip"] = _client_ip(request)
        fields["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:256]
    return AuditEvent.objects.create(
        action=action,
        actor=actor if actor is not None and actor.is_authenticated else None,
        lab=lab,
        actor_label=actor_label,
        metadata=metadata or {},
        **fields,
    )
