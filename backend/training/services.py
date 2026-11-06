"""Training business logic (D175-D179): records, verification, certificates, compliance status.
Writes audit in the same transaction."""

import calendar
import datetime

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied, ValidationError

from audit.models import AuditAction as A
from audit.services import record as audit
from core.permissions import Perm, can
from documents import services as document_services
from labs.models import LabMembership
from projects.models import Project, ProjectMembership
from training.models import AppliesTo, ComplianceStatus, TrainingRecord, TrainingRequirement

EXPIRING_DAYS = 60  # D177: "expiring" means within 60 days
DONE, EXPIRING, EXPIRED, MISSING = (
    ComplianceStatus.DONE,
    ComplianceStatus.EXPIRING,
    ComplianceStatus.EXPIRED,
    ComplianceStatus.MISSING,
)


class InUse(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "People have records for this training, so it can't be deleted."
    default_code = "in_use"


def add_months(d: datetime.date, months: int) -> datetime.date:
    total = d.month - 1 + months
    year, month = d.year + total // 12, total % 12 + 1
    return d.replace(year=year, month=month, day=min(d.day, calendar.monthrange(year, month)[1]))


def computed_expiry(requirement, completed_on):
    if requirement.validity_months is None:
        return None
    return add_months(completed_on, requirement.validity_months)


# ---------------------------------------------------------------- requirements


def get_requirement(lab, pk):
    req = TrainingRequirement.objects.for_lab(lab).filter(pk=pk).first()
    if req is None:
        raise ValidationError({"requirement": "This training does not exist."})
    return req


def _projects(lab, ids):
    found = list(Project.objects.for_lab(lab).filter(pk__in=ids, deleted_at__isnull=True))
    if len(found) != len(set(ids)):
        raise ValidationError({"projects": "A project does not exist."})
    return found


def _save_requirement(req, data, lab):
    project_ids = data.pop("projects", None)
    for k, v in data.items():
        setattr(req, k, v)
    if req.applies_to == AppliesTo.ROLES and not req.roles:
        raise ValidationError({"roles": "Choose at least one role."})
    try:
        with transaction.atomic():
            req.save()
    except IntegrityError as exc:  # D33: unique (lab, name)
        raise ValidationError({"name": "A training with this name already exists."}) from exc
    if project_ids is not None:
        req.projects.set(_projects(lab, project_ids))
    if req.applies_to == AppliesTo.PROJECTS and not req.projects.exists():
        raise ValidationError({"projects": "Choose at least one project."})
    return req


@transaction.atomic
def create_requirement(*, lab, user, data, request=None):
    req = _save_requirement(TrainingRequirement(lab=lab), dict(data), lab)
    audit(A.TRAINING_REQUIREMENT_CREATED, actor=user, lab=lab, target=req, request=request)
    return req


@transaction.atomic
def update_requirement(req, *, user, data, request=None):
    data = dict(data)
    changed = sorted(data)
    _save_requirement(req, data, req.lab)
    audit(
        A.TRAINING_REQUIREMENT_UPDATED,
        actor=user,
        lab=req.lab,
        target=req,
        request=request,
        metadata={"changed": changed},
    )
    return req


def delete_requirement(req, *, user, request=None):
    try:
        with transaction.atomic():
            audit(
                A.TRAINING_REQUIREMENT_DELETED, actor=user, lab=req.lab, target=req, request=request
            )  # before: the name survives in target_repr
            req.projects.clear()
            req.delete()
    except ProtectedError as exc:  # records exist (D175)
        raise InUse() from exc


# ---------------------------------------------------------------- records


def _is_manager(actor, lab) -> bool:
    return can(actor, Perm.MANAGE_TRAINING, lab)


def _check_dates(rec):
    if rec.expires_on is not None and rec.expires_on < rec.completed_on:
        raise ValidationError({"expires_on": "Expiry can't be before the completion date."})


def _unverify(rec):
    rec.verified_by, rec.verified_at = None, None


@transaction.atomic
def create_record(*, lab, actor, data, request=None):
    data = dict(data)
    target = data.pop("user", None) or actor
    if target.pk != actor.pk and not _is_manager(actor, lab):
        raise PermissionDenied
    if not LabMembership.objects.for_lab(lab).filter(user=target).exists():
        raise ValidationError({"user": "This person is not a member of the lab."})
    req = get_requirement(lab, data.pop("requirement"))
    if data.get("expires_on") is None:
        data["expires_on"] = computed_expiry(req, data["completed_on"])
    rec = TrainingRecord(lab=lab, requirement=req, user=target, **data)
    _check_dates(rec)
    rec.save()
    audit(
        A.TRAINING_RECORD_CREATED,
        actor=actor,
        lab=lab,
        target=rec,
        request=request,
        metadata={"member": str(target.pk), "training": req.name},
    )
    return rec


@transaction.atomic
def update_record(rec, *, actor, data, request=None):
    """Changing the dates or the certificate voids a verification: it vouched for the old ones."""
    data = dict(data)
    dates_changed = False
    if "completed_on" in data and data["completed_on"] != rec.completed_on:
        dates_changed = True
        if "expires_on" not in data:  # the expiry follows the completion date
            data["expires_on"] = computed_expiry(rec.requirement, data["completed_on"])
    if "expires_on" in data and data["expires_on"] != rec.expires_on:
        dates_changed = True
    for k, v in data.items():
        setattr(rec, k, v)
    _check_dates(rec)
    if dates_changed:
        _unverify(rec)
    rec.save()
    audit(
        A.TRAINING_RECORD_UPDATED,
        actor=actor,
        lab=rec.lab,
        target=rec,
        request=request,
        metadata={"changed": sorted(data), "verification_cleared": dates_changed},
    )
    return rec


@transaction.atomic
def verify_record(rec, *, actor, request=None):
    rec.verified_by, rec.verified_at = actor, timezone.now()
    rec.save(update_fields=["verified_by", "verified_at", "updated_at"])
    audit(A.TRAINING_RECORD_VERIFIED, actor=actor, lab=rec.lab, target=rec, request=request)
    return rec


@transaction.atomic
def delete_record(rec, *, actor, request=None):
    """Soft delete. Owners may remove their own unverified records; a verified one needs a
    manager, so a member can't erase what a PI signed off."""
    if rec.verified_at is not None and not _is_manager(actor, rec.lab):
        raise PermissionDenied
    rec.deleted_at = timezone.now()
    rec.save(update_fields=["deleted_at", "updated_at"])
    audit(A.TRAINING_RECORD_DELETED, actor=actor, lab=rec.lab, target=rec, request=request)


def live_certificate(rec):
    return rec.attachments.filter(deleted_at__isnull=True).order_by("-created_at").first()


@transaction.atomic
def upload_certificate(rec, *, actor, file, request=None):
    """One live certificate per record: a new upload replaces the old one (kept, soft-deleted)."""
    for old in rec.attachments.filter(deleted_at__isnull=True):
        document_services.delete_attachment(old, user=actor, request=request)
    attachment = document_services.upload_attachment(
        training_record=rec, user=actor, file=file, request=request
    )
    if rec.verified_at is not None:
        _unverify(rec)
        rec.save(update_fields=["verified_by", "verified_at", "updated_at"])
    return attachment


# ---------------------------------------------------------------- compliance


def status_of(rec, today, window=EXPIRING_DAYS) -> str:
    if rec is None:
        return MISSING
    if rec.expires_on is None:
        return DONE
    if rec.expires_on < today:
        return EXPIRED
    return EXPIRING if (rec.expires_on - today).days <= window else DONE


def latest_records(lab, *, user=None):
    """The record that counts for each (user, requirement): the most recent completion."""
    qs = TrainingRecord.objects.for_lab(lab).filter(deleted_at__isnull=True)
    if user is not None:
        qs = qs.filter(user=user)
    latest = {}
    for rec in qs.order_by("-completed_on", "-created_at", "id"):
        latest.setdefault((rec.user_id, rec.requirement_id), rec)
    return latest


def applies(req, membership, project_ids) -> bool:
    if req.applies_to == AppliesTo.ALL:
        return True
    if req.applies_to == AppliesTo.ROLES:
        return membership.role in req.roles
    return bool(project_ids & {p.pk for p in req.projects.all()})


def compliance(lab, *, today=None, window=EXPIRING_DAYS, user=None):
    """{requirements, members: [{user, role, cells}], summary}. `cells` maps a requirement id to
    None (does not apply) or {status, record, completed_on, expires_on, days_left, verified}."""
    today = today or timezone.localdate()
    reqs = list(
        TrainingRequirement.objects.for_lab(lab).prefetch_related("projects").order_by("name", "id")
    )
    memberships = LabMembership.objects.for_lab(lab).select_related("user")
    memberships = memberships.filter(user__is_active=True)
    if user is not None:
        memberships = memberships.filter(user=user)
    memberships = list(memberships.order_by("user__display_name", "user__email"))
    projects = {}
    for pm in ProjectMembership.objects.for_lab(lab).filter(user__in=[m.user for m in memberships]):
        projects.setdefault(pm.user_id, set()).add(pm.project_id)
    latest = latest_records(lab, user=user)
    summary = {DONE: 0, EXPIRING: 0, EXPIRED: 0, MISSING: 0}
    rows = []
    for m in memberships:
        cells = {}
        for req in reqs:
            if not applies(req, m, projects.get(m.user_id, set())):
                cells[str(req.pk)] = None
                continue
            rec = latest.get((m.user_id, req.pk))
            st = status_of(rec, today, window)
            summary[st] += 1
            cells[str(req.pk)] = {
                "status": st,
                "record": str(rec.pk) if rec else None,
                "completed_on": rec.completed_on if rec else None,
                "expires_on": rec.expires_on if rec else None,
                "days_left": (rec.expires_on - today).days if rec and rec.expires_on else None,
                "verified": bool(rec and rec.verified_at),
            }
        rows.append({"user": m.user, "role": m.role, "cells": cells})
    return {"requirements": reqs, "members": rows, "summary": summary}


def expiring(lab, days=EXPIRING_DAYS, *, today=None):
    """Items needing attention: expired, or expiring within `days`. Used by the PI dashboard."""
    today = today or timezone.localdate()
    data = compliance(lab, today=today, window=days)
    by_id = {str(r.pk): r for r in data["requirements"]}
    items = [
        {
            "user": row["user"],
            "requirement": by_id[rid],
            "status": cell["status"],
            "expires_on": cell["expires_on"],
            "days_left": cell["days_left"],
        }
        for row in data["members"]
        for rid, cell in row["cells"].items()
        if cell and cell["status"] in (EXPIRING, EXPIRED)
    ]
    items.sort(key=lambda i: (i["expires_on"], i["user"].display_name or i["user"].email))
    return items


def done_user_ids(lab, requirement) -> list[str]:
    """People whose current record for `requirement` is not expired (D179: ticks onboarding)."""
    today = timezone.localdate()
    return sorted(
        str(uid)
        for (uid, rid), rec in latest_records(lab).items()
        if rid == requirement.pk and status_of(rec, today) in (DONE, EXPIRING)
    )
