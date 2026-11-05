"""Lab business logic (ARCHITECTURE section 0). Views validate and call these;
write actions record their audit event in the same transaction."""

import datetime

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import Throttled, ValidationError

from audit.models import AuditAction
from audit.services import record
from core.auth import has_verified_email
from core.email import send_email
from core.models import PLACEHOLDER_INSTITUTION, Institution
from core.permissions import LAB_ROLE_PERMS, Perm, forget, lab_role
from core.tenancy import by_secret
from labs.models import Invite, Lab, LabMembership, LabRole, hash_token
from projects.models import ProjectMembership
from projects.services import unassign_lost_access


def _require_pi_for_pi_role(actor, lab, *roles):
    if LabRole.PI in roles and lab_role(actor, lab) != LabRole.PI:
        raise PermissionDenied("Only a PI can grant, change or remove the PI role.")


def _inviter_may_grant(lab, inviter, role) -> bool:
    """D40: can `inviter` still manage members, and grant `role` (PI only by a PI)?"""
    r = lab_role(inviter, lab)
    return Perm.MANAGE_MEMBERS in LAB_ROLE_PERMS.get(r, ()) and (
        role != LabRole.PI or r == LabRole.PI
    )


def _revoke_stale_invites(*, lab, user, by, request, new_role=None) -> None:
    """D40: revoke open invites `user` sent that they could no longer issue as `new_role`
    (None means they left the lab)."""
    open_ = Invite.objects.for_lab(lab).filter(
        invited_by=user, accepted_at__isnull=True, revoked_at__isnull=True
    )
    for invite in open_:
        if new_role is None or not (
            Perm.MANAGE_MEMBERS in LAB_ROLE_PERMS[new_role]
            and (invite.role != LabRole.PI or new_role == LabRole.PI)
        ):
            _revoke(invite=invite, by=by, request=request)


@transaction.atomic
def create_lab(*, user, name, request=None) -> Lab:
    institution, _ = Institution.objects.get_or_create(name=PLACEHOLDER_INSTITUTION)
    lab = Lab.objects.create(institution=institution, name=name, created_by=user)
    LabMembership.objects.create(lab=lab, user=user, role=LabRole.PI)
    record(AuditAction.LAB_CREATED, actor=user, lab=lab, request=request)
    forget(user)
    return lab


@transaction.atomic
def update_lab(*, lab, user, name, request=None) -> Lab:
    lab.name = name
    lab.save(update_fields=["name", "updated_at"])
    record(AuditAction.LAB_UPDATED, actor=user, lab=lab, request=request, metadata={"name": name})
    return lab


def create_invite(*, lab, by, email, role, request=None) -> Invite:
    _require_pi_for_pi_role(by, lab, role)
    since = timezone.now() - datetime.timedelta(days=1)  # D50; revoked invites count too
    if Invite.objects.for_lab(lab).filter(created_at__gte=since).count() >= (
        settings.INVITES_PER_LAB_PER_DAY
    ):
        raise Throttled(detail="This lab has sent too many invites today. Try again tomorrow.")
    if LabMembership.objects.for_lab(lab).filter(user__email__iexact=email).exists():
        raise ValidationError({"email": "This person is already a member of the lab."})
    try:
        with transaction.atomic():
            invite, token = Invite.issue(lab=lab, email=email, role=role, invited_by=by)
            record(
                AuditAction.MEMBERSHIP_INVITED,
                actor=by,
                lab=lab,
                target=invite,
                request=request,
                metadata={"email": invite.email, "role": role},
            )
    except IntegrityError as exc:  # partial unique index: one open invite per email (D33)
        raise ValidationError({"email": "An invite for this email is already open."}) from exc
    # D37: the raw token exists only in this emailed link.
    link = f"{settings.FRONTEND_URL}/invite/{token}"
    send_email(
        "invite",
        invite.email,
        {"inviter": by.display_name or by.email, "lab": lab.name, "role": role, "url": link},
    )
    return invite


@transaction.atomic
def revoke_invite(*, invite, by, request=None) -> None:
    _require_pi_for_pi_role(by, invite.lab, invite.role)
    _revoke(invite=invite, by=by, request=request)


def _revoke(*, invite, by, request=None) -> None:
    invite.revoked_at = timezone.now()
    invite.save(update_fields=["revoked_at", "updated_at"])
    record(
        AuditAction.MEMBERSHIP_INVITE_REVOKED,
        actor=by,
        lab=invite.lab,
        target=invite,
        request=request,
        metadata={"email": invite.email, "role": invite.role},
    )


def usable_invite_for_token(token, *, lock=False) -> Invite:
    """404 for any token that is unknown, expired, revoked or already used."""
    qs = by_secret(Invite).select_related("lab")
    if lock:
        qs = qs.select_for_update(of=("self",))
    invite = qs.filter(token_hash=hash_token(token)).first()
    if invite is None or not invite.is_usable:
        raise Http404
    return invite


@transaction.atomic
def accept_invite(*, user, token, request=None) -> Lab:
    invite = usable_invite_for_token(token, lock=True)
    # D25: the invited address must be any verified address of the logged-in user.
    if not has_verified_email(user, invite.email):
        raise PermissionDenied("Verify the email address this invite was sent to, then retry.")
    lab = invite.lab
    if not _inviter_may_grant(lab, invite.invited_by, invite.role):  # D40
        raise Http404
    if LabMembership.objects.for_lab(lab).filter(user=user).exists():
        raise ValidationError({"detail": "You are already a member of this lab."})
    LabMembership.objects.create(lab=lab, user=user, role=invite.role, invited_by=invite.invited_by)
    invite.accepted_at, invite.accepted_by = timezone.now(), user
    invite.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
    record(
        AuditAction.MEMBERSHIP_INVITE_ACCEPTED,
        actor=user,
        lab=lab,
        target=invite,
        request=request,
        metadata={"role": invite.role},
    )
    forget(user)
    return lab


def _pi_count(lab) -> int:
    return len(LabMembership.objects.for_lab(lab).select_for_update().filter(role=LabRole.PI))


@transaction.atomic
def change_role(*, membership, by, role, request=None) -> LabMembership:
    lab, old = membership.lab, membership.role
    if role == old:
        return membership
    _require_pi_for_pi_role(by, lab, old, role)
    if old == LabRole.PI and _pi_count(lab) < 2:
        raise ValidationError({"detail": "A lab must keep at least one PI."})
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    record(
        AuditAction.MEMBERSHIP_ROLE_CHANGED,
        actor=by,
        lab=lab,
        target=membership,
        request=request,
        metadata={"user_id": str(membership.user_id), "old_role": old, "new_role": role},
    )
    _revoke_stale_invites(lab=lab, user=membership.user, by=by, request=request, new_role=role)
    unassign_lost_access(
        membership.user, lab=lab, by=by, request=request, reason="lab_role_changed"
    )
    return membership


@transaction.atomic
def remove_member(*, membership, by, request=None) -> None:
    lab = membership.lab
    _require_pi_for_pi_role(by, lab, membership.role)
    if membership.role == LabRole.PI and _pi_count(lab) < 2:
        raise ValidationError({"detail": "A lab must keep at least one PI."})
    record(
        AuditAction.MEMBERSHIP_REMOVED,
        actor=by,
        lab=lab,
        target=membership,
        request=request,
        metadata={"user_id": str(membership.user_id), "role": membership.role},
    )
    # D19: a removed lab member loses their project memberships too.
    ProjectMembership.objects.for_lab(lab).filter(user_id=membership.user_id).delete()
    membership.delete()
    _revoke_stale_invites(lab=lab, user=membership.user, by=by, request=request)
    unassign_lost_access(
        membership.user, lab=lab, by=by, request=request, reason="removed_from_lab"
    )
