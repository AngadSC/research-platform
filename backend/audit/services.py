import ipaddress
import re

from django.conf import settings

from audit.models import AuditAction, AuditEvent
from core.tenancy import project_of


def _client_ip(request) -> str | None:
    """The caller's address, for rate limits only. Never stored (D266)."""
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
    if lab is None and not action.value.startswith(("auth.", "site.")):
        raise ValueError("lab may be None only for auth.* and site.* actions")
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
        fields["user_agent"] = request.META.get("HTTP_USER_AGENT", "")[:256]
    return AuditEvent.objects.create(
        action=action,
        actor=actor if actor is not None and actor.is_authenticated else None,
        lab=lab,
        actor_label=actor_label,
        metadata=metadata or {},
        **fields,
    )


UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


# The only labels the server writes with a user id in them (TrainingRecord and chat __str__);
# anything else, such as a task title, is user-typed and never resolved.
_LABEL_ID_RE = re.compile(
    rf"^(?:(?P<a>{UUID_RE.pattern}):|Message from (?P<b>{UUID_RE.pattern})$)", re.S
)
_LABEL_ID_TARGETS = {"training.TrainingRecord", "projects.ChatMessage", "labs.LabChatMessage"}


def label_user_id(e) -> str | None:
    if e.target_type not in _LABEL_ID_TARGETS:
        return None
    m = _LABEL_ID_RE.match(e.target_repr or "")
    return (m.group("a") or m.group("b")) if m else None


def person_id(e):
    m = e.metadata if isinstance(e.metadata, dict) else {}
    return m.get("user_id") or m.get("person")


def label_context(events, user, lab) -> dict:
    """Names for one page of events, limited to what `user` may see: projects they can open, and
    no PI-only file names unless they are a PI (D226, D244)."""
    from core.models import User  # imported here: most apps import this module
    from core.permissions import can_access_funding, visible_projects
    from documents.models import Attachment

    # Only ids this lab's own events stored, so everyone named was in the lab at the time.
    people = {str(pid) for e in events if (pid := person_id(e))}
    names = {str(u.pk): u.display_name or u.email for u in User.objects.filter(pk__in=people)}
    # Ids that server-written labels embed: resolved only for people in this lab.
    embedded = {i for e in events if (i := label_user_id(e))}
    names |= {
        str(u.pk): u.display_name or u.email
        for u in User.objects.filter(pk__in=embedded, labmembership__lab=lab)
    }
    project_ids = {e.project_id for e in events if e.project_id}
    projects = {
        p.pk: p.name for p in visible_projects(user, lab).filter(pk__in=project_ids).only("name")
    }
    hidden = set()
    if not can_access_funding(user, lab):
        files = {e.target_id for e in events if e.target_type == "documents.Attachment"}
        hidden = set(
            Attachment.objects.for_lab(lab)
            .filter(pk__in=files, pi_only=True)
            .values_list("pk", flat=True)
        )
    return {"names": names, "projects": projects, "hidden_files": hidden}
