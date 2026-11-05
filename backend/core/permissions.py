"""Permission module (ARCHITECTURE section 3, D19, D21). `.unscoped` is allowed here.

Background jobs (digests, reminders, notifications) must not re-implement role logic. A job
re-checks permissions when it runs, never at enqueue time, and per recipient:

    for user in users_with(Perm.VIEW_PROJECT, project):   # or candidates from the job payload
        if can(user, Perm.VIEW_PROJECT, obj):             # obj: the Project or lab-data object
            notify(user, obj)

Use `can(user, perm, obj)` for each recipient before sending anything about `obj`; use
`users_with(perm, target)` only to find candidates. Never compare roles in a job.

Role lookups are cached on the user object. A job must re-fetch each user per item (never reuse
a user across items), or call `forget(user)` after anything that changes their memberships.
`forget` also works on a lazy `request.user`.
"""

from enum import StrEnum

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import Http404
from django.utils.functional import empty
from rest_framework.permissions import BasePermission

from core.models import User
from core.tenancy import LabScopedModel, project_of
from labs.models import Lab, LabMembership, LabRole
from projects.models import Project, ProjectMembership, ProjectRole


class Perm(StrEnum):
    # lab-level
    VIEW_LAB = "view_lab"
    MANAGE_LAB = "manage_lab"
    MANAGE_MEMBERS = "manage_members"
    MANAGE_BILLING = "manage_billing"
    VIEW_AUDIT_LOG = "view_audit_log"
    CREATE_PROJECT = "create_project"
    VIEW_ETHICS = "view_ethics"
    EDIT_ETHICS = "edit_ethics"
    VIEW_RETENTION = "view_retention"
    DELETE_PROJECT = "delete_project"  # granted by lab role, checked on a Project
    MANAGE_INTEGRATIONS = "manage_integrations"  # connect/disconnect your own accounts
    MANAGE_LAB_INTEGRATIONS = "manage_lab_integrations"  # see and revoke any member's
    MANAGE_INVENTORY = "manage_inventory"  # Run 4, D147: add, edit and delete inventory items
    MANAGE_TRAINING = "manage_training"  # Run 5, D176: requirements, everyone's records
    # project-level
    VIEW_PROJECT = "view_project"
    EDIT_PROJECT = "edit_project"
    EDIT_CONTENT = "edit_content"
    MANAGE_PROJECT_MEMBERS = "manage_project_members"
    EXPORT = "export"
    # pseudo
    PUBLIC = "public"
    AUTHENTICATED = "authenticated"


SENSITIVE_PERMS = frozenset(
    {
        Perm.MANAGE_MEMBERS,
        Perm.EXPORT,
        Perm.VIEW_AUDIT_LOG,
        Perm.MANAGE_BILLING,
        Perm.DELETE_PROJECT,
    }
)

_P = Perm
_ALL_LAB = frozenset(
    {
        _P.VIEW_LAB,
        _P.MANAGE_LAB,
        _P.MANAGE_MEMBERS,
        _P.VIEW_AUDIT_LOG,
        _P.CREATE_PROJECT,
        _P.VIEW_ETHICS,
        _P.EDIT_ETHICS,
        _P.VIEW_RETENTION,
        _P.DELETE_PROJECT,
        _P.MANAGE_INTEGRATIONS,
        _P.MANAGE_LAB_INTEGRATIONS,
        _P.MANAGE_INVENTORY,
        _P.MANAGE_TRAINING,
    }
)
LAB_ROLE_PERMS: dict[str, frozenset[Perm]] = {
    LabRole.PI: _ALL_LAB | {_P.MANAGE_BILLING},
    LabRole.LAB_ADMIN: _ALL_LAB,
    LabRole.MEMBER: frozenset(
        {
            _P.VIEW_LAB,
            _P.CREATE_PROJECT,
            _P.VIEW_ETHICS,
            _P.EDIT_ETHICS,
            _P.MANAGE_INTEGRATIONS,
            _P.MANAGE_INVENTORY,
        }
    ),
    LabRole.VIEWER: frozenset({_P.VIEW_LAB, _P.VIEW_ETHICS, _P.MANAGE_INTEGRATIONS}),
}
PROJECT_ROLE_PERMS: dict[str, frozenset[Perm]] = {
    ProjectRole.LEAD: frozenset(
        {_P.VIEW_PROJECT, _P.EDIT_CONTENT, _P.EDIT_PROJECT, _P.MANAGE_PROJECT_MEMBERS, _P.EXPORT}
    ),
    ProjectRole.CONTRIBUTOR: frozenset({_P.VIEW_PROJECT, _P.EDIT_CONTENT}),
    ProjectRole.VIEWER: frozenset({_P.VIEW_PROJECT}),
}
PROJECT_PERMS = frozenset().union(*PROJECT_ROLE_PERMS.values())
_ETHICS_MAP = {_P.VIEW_PROJECT: _P.VIEW_ETHICS, _P.EDIT_CONTENT: _P.EDIT_ETHICS}
_IMPLICIT_LEADS = (LabRole.PI, LabRole.LAB_ADMIN)


def _lab_id(lab):
    return getattr(lab, "pk", lab)


def forget(user) -> None:
    """Drop the cached roles on the real user object, wrapped (`request.user`) or not."""
    real = getattr(user, "_wrapped", user)  # SimpleLazyObject keeps the real user here
    if real is not empty:
        real.__dict__.pop("_perm_cache", None)


def _ethics_mapped(perm, target):
    """Only an ethics-domain object maps project perms onto the ethics perms (D27, D38);
    on any other lab-level object project perms are denied."""
    if getattr(target, "permission_domain", None) == "ethics":
        return _ETHICS_MAP.get(perm, perm)
    return perm


def _cache(user) -> dict:
    if not hasattr(user, "_perm_cache"):
        user._perm_cache = {}
    return user._perm_cache


def _active(user) -> bool:
    return bool(user is not None and user.is_authenticated and user.is_active)


def lab_role(user, lab) -> str | None:
    if not _active(user):
        return None
    lab_id = _lab_id(lab)
    cache = _cache(user)
    key = ("lab", lab_id)
    if key not in cache:
        cache[key] = (
            LabMembership.unscoped.filter(user=user, lab_id=lab_id)
            .values_list("role", flat=True)
            .first()
        )
    return cache[key]


def _effective_project_role(lab_r, project_r) -> str | None:
    """D19: pi and lab_admin act as lead; others use their ProjectMembership;
    a lab viewer is capped at viewer."""
    if lab_r in _IMPLICIT_LEADS:
        return ProjectRole.LEAD
    if lab_r is None or project_r is None:
        return None
    return ProjectRole.VIEWER if lab_r == LabRole.VIEWER else project_r


def project_role(user, project) -> str | None:
    if project.deleted_at is not None:  # D39
        return None
    lab_r = lab_role(user, project.lab_id)
    if lab_r is None:
        return None
    if lab_r in _IMPLICIT_LEADS:
        return ProjectRole.LEAD
    cache = _cache(user)
    key = ("project", project.pk)
    if key not in cache:
        cache[key] = (
            ProjectMembership.unscoped.filter(user=user, project=project)
            .values_list("role", flat=True)
            .first()
        )
    return _effective_project_role(lab_r, cache[key])


def can_view_ethics_files(user, approval, visible=None) -> bool:
    """D48: an approval's files need view_ethics plus visibility of at least one linked project,
    or the pi/lab_admin role. `visible` is an optional precomputed set of visible project ids."""
    if not can(user, Perm.VIEW_ETHICS, approval):
        return False
    if lab_role(user, approval.lab_id) in _IMPLICIT_LEADS:
        return True
    if visible is None:
        visible = set(visible_projects(user, approval.lab_id).values_list("pk", flat=True))
    return any(p.pk in visible for p in approval.projects.all())


def can_edit_ethics(user, approval) -> bool:
    """D52: editing or deleting an approval needs edit_ethics plus visibility of every linked
    project, unless the user is a pi or lab_admin."""
    if approval.deleted_at is not None or not can(user, Perm.EDIT_ETHICS, approval):
        return False
    if lab_role(user, approval.lab_id) in _IMPLICIT_LEADS:
        return True
    visible = set(visible_projects(user, approval.lab_id).values_list("pk", flat=True))
    return all(p.pk in visible for p in approval.projects.all())


def get_lab_or_404(user, lab_id) -> Lab:
    try:
        if lab_role(user, lab_id) is None:
            raise Http404
        return Lab.objects.get(pk=lab_id)
    except (ValidationError, ValueError, Lab.DoesNotExist) as exc:
        raise Http404 from exc


def _resolve(target):
    """Return (lab_id, project or None). `(None, None)` means unresolvable: every check on it
    denies. Deleted projects (D39) and project-typed objects without an owner (D38) are
    unresolvable; a null FK is never read as "lab-level"."""
    if isinstance(target, Lab):
        return target.pk, None
    if isinstance(target, Project):
        return (None, None) if target.deleted_at is not None else (target.lab_id, target)
    if isinstance(target, LabScopedModel):
        domain = target.permission_domain
        if domain == "lab" and target.project_path is None:
            return target.lab_id, None
        project = project_of(target) if domain == "project" else None
        if domain == "ethics" and target.project_path is None:
            return target.lab_id, None
        if project is None or project.deleted_at is not None or project.lab_id != target.lab_id:
            return None, None
        return target.lab_id, project
    raise TypeError(f"cannot check permissions on {type(target).__name__}")


def _sees_restricted(user, approval) -> bool:
    """D56: a restricted approval is seen by pi, lab_admin and anyone who sees a linked project."""
    if lab_role(user, approval.lab_id) in _IMPLICIT_LEADS:
        return True
    ids = [p.pk for p in approval.projects.all()]
    return visible_projects(user, approval.lab_id).filter(pk__in=ids).exists()


def can(user, perm: Perm, target=None) -> bool:
    perm = Perm(perm)
    if perm == Perm.PUBLIC:
        return True
    if perm == Perm.AUTHENTICATED:
        return _active(user)
    lab_id, project = _resolve(target)
    if lab_id is None:
        return False
    if getattr(target, "restricted", False) and not _sees_restricted(user, target):
        return False
    if project is not None and perm in PROJECT_PERMS:
        return perm in PROJECT_ROLE_PERMS.get(project_role(user, project), ())
    if project is None:
        perm = _ethics_mapped(perm, target)
    elif project_role(user, project) is None:  # lab perm on a project's object needs visibility
        return False
    if perm in PROJECT_PERMS:
        return False
    return perm in LAB_ROLE_PERMS.get(lab_role(user, lab_id), ())


def _visible(user, target) -> bool:
    lab_id, project = _resolve(target)
    if lab_id is None:
        return False
    if project is not None:
        return project_role(user, project) is not None
    return lab_role(user, lab_id) is not None


def require(user, perm: Perm, target=None) -> None:
    if Perm(perm) in (Perm.PUBLIC, Perm.AUTHENTICATED):
        if not can(user, perm, target):
            raise PermissionDenied
        return
    if not _visible(user, target):
        raise Http404
    if not can(user, perm, target):
        raise PermissionDenied


def visible_projects(user, lab):
    lab_id = _lab_id(lab)
    base = Project.unscoped.filter(lab_id=lab_id, deleted_at__isnull=True)
    role = lab_role(user, lab_id)
    if role is None:
        return base.none()
    if role in _IMPLICIT_LEADS:
        return base
    return base.filter(memberships__user=user)


def labs_for(user):
    """Labs the user belongs to."""
    if not _active(user):
        return Lab.objects.none()
    mine = LabMembership.unscoped.filter(user=user).values("lab_id")
    return Lab.objects.filter(pk__in=mine).select_related("institution").order_by("name")


def scope(model, user, lab):
    return model.objects.visible_to(user, lab)


def users_with(perm: Perm, target):
    """Active users holding `perm` on `target` (for jobs)."""
    perm = Perm(perm)
    lab_id, project = _resolve(target)
    if lab_id is None:
        return User.objects.none()
    lm = LabMembership.unscoped.filter(lab_id=lab_id)
    if project is not None and perm in PROJECT_PERMS:
        q = Q(pk__in=lm.filter(role__in=_IMPLICIT_LEADS).values("user"))
        members = ProjectMembership.unscoped.filter(project=project)
        for lab_r in (LabRole.MEMBER, LabRole.VIEWER):
            roles = [
                r
                for r in ProjectRole
                if perm in PROJECT_ROLE_PERMS[_effective_project_role(lab_r, r)]
            ]
            q |= Q(
                pk__in=members.filter(
                    role__in=roles, user__in=lm.filter(role=lab_r).values("user")
                ).values("user")
            )
    else:
        if project is None:
            perm = _ethics_mapped(perm, target)
        roles = [r for r, perms in LAB_ROLE_PERMS.items() if perm in perms]
        q = Q(pk__in=lm.filter(role__in=roles).values("user"))
        if project is not None:  # must also see the project
            seen = ProjectMembership.unscoped.filter(
                project=project, user__in=lm.values("user")
            ).values("user")
            q &= Q(pk__in=lm.filter(role__in=_IMPLICIT_LEADS).values("user")) | Q(pk__in=seen)
    if getattr(target, "restricted", False):  # D56
        seen = ProjectMembership.unscoped.filter(
            project__in=target.projects.filter(deleted_at__isnull=True)
        ).values("user")
        q &= Q(pk__in=lm.filter(role__in=_IMPLICIT_LEADS).values("user")) | Q(pk__in=seen)
    return User.objects.filter(q, is_active=True)


class HasPerm(BasePermission):
    """DRF permission. Views declare `perms = {action_or_METHOD: Perm}`; missing means denied."""

    def _perm(self, request, view):
        perms = getattr(view, "perms", {})
        action = getattr(view, "action", None)
        return perms.get(action) or perms.get(request.method)

    def has_permission(self, request, view):
        perm = self._perm(request, view)
        if perm is None:
            return False
        target = getattr(view, "project", None) or getattr(request, "lab", None)
        if target is None and perm not in (Perm.PUBLIC, Perm.AUTHENTICATED):
            return False
        return can(request.user, perm, target)

    def has_object_permission(self, request, view, obj):
        perm = self._perm(request, view)
        return perm is not None and can(request.user, perm, obj)
