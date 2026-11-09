"""Admin-area business logic (D146-D151). Writes audit in the same transaction."""

from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction as A
from audit.services import record
from core.institution_starters import NATIONAL_RESOURCES, STARTER_RESOURCES, match_institution
from core.models import Institution, User
from labs.models import (
    InstitutionResource,
    InventoryItem,
    LabMembership,
    OnboardingCompletion,
    OnboardingItem,
)

DETAIL_FIELDS = ["name", "department", "description", "address", "contact_email", "website"]


def _members_only_owner(lab, owner_id):
    if owner_id is None:
        return None
    if not LabMembership.objects.for_lab(lab).filter(user_id=owner_id).exists():
        raise ValidationError({"owner": "This person is not a member of the lab."})
    return User.objects.get(pk=owner_id)


def _save(obj):
    try:
        with transaction.atomic():
            obj.save()
    except IntegrityError as exc:  # D33
        raise ValidationError({"url": "This link is already in the list."}) from exc


# ---------------------------------------------------------------- lab details


@transaction.atomic
def update_lab_details(*, lab, user, data, request=None):
    changed = [f for f in DETAIL_FIELDS if f in data and getattr(lab, f) != data[f]]
    for f in changed:
        setattr(lab, f, data[f])
    new_name = data.get("institution_name")
    if new_name is not None:
        inst = institution_for(new_name)
        if inst.pk != lab.institution_id:
            lab.institution = inst
            changed.append("institution")
    if changed:
        lab.save()
    record(
        A.LAB_UPDATED,
        actor=user,
        lab=lab,
        request=request,
        metadata={"name": lab.name, "changed": changed},
    )
    if "institution" in changed:
        apply_starter_resources(lab, user=user, request=request)
    return lab


def institution_for(name):
    """The Institution for a typed name; a recognised name takes its canonical spelling."""
    name = match_institution(name) or name.strip()
    return Institution.objects.filter(name__iexact=name).first() or Institution.objects.create(
        name=name
    )


def apply_starter_resources(lab, *, user=None, request=None) -> int:
    """Idempotent: adds the institution's starter links and the national links that the lab does
    not have yet, matched by URL, and leaves existing rows alone so a lab's edits survive.
    ponytail: deletions are not tracked, so a link the lab removed comes back the next time
    this runs; add a dismissed-URL list if labs complain."""
    rows = [
        *STARTER_RESOURCES.get(match_institution(lab.institution.name), []),
        *NATIONAL_RESOURCES,
    ]
    added = 0
    for i, row in enumerate(rows):
        res, created = InstitutionResource.objects.for_lab(lab).get_or_create(
            url=row["url"], defaults={**row, "lab": lab, "order": i}
        )  # get_or_create, not a prior read: two clicks at once must not hit the unique constraint
        if not created:
            continue
        record(
            A.INSTITUTION_RESOURCE_CREATED,
            actor=user,
            lab=lab,
            target=res,
            request=request,
            metadata={"source": "starter"},
            actor_label="" if user else "job:institution_resources",
        )
        added += 1
    return added


@transaction.atomic
def load_starter_resources(lab, *, user, request=None) -> dict:
    """The "Get my university's forms" action (D149)."""
    return {
        "added": apply_starter_resources(lab, user=user, request=request),
        "institution": lab.institution.name,
        "curated_institution": match_institution(lab.institution.name),
    }


# ---------------------------------------------------------------- generic CRUD


def _create(model, created, *, lab, user, data, request):
    obj = model(lab=lab, **data)
    _save(obj)
    record(created, actor=user, lab=lab, target=obj, request=request)
    return obj


def _update(obj, updated, *, user, data, request):
    for k, v in data.items():
        setattr(obj, k, v)
    _save(obj)
    record(
        updated,
        actor=user,
        lab=obj.lab,
        target=obj,
        request=request,
        metadata={"changed": sorted(data)},
    )
    return obj


def _delete(obj, deleted, *, user, request):
    record(deleted, actor=user, lab=obj.lab, target=obj, request=request)  # before: repr survives
    obj.delete()


@transaction.atomic
def create_resource(*, lab, user, data, request=None):
    return _create(
        InstitutionResource,
        A.INSTITUTION_RESOURCE_CREATED,
        lab=lab,
        user=user,
        data=data,
        request=request,
    )


@transaction.atomic
def update_resource(obj, *, user, data, request=None):
    return _update(obj, A.INSTITUTION_RESOURCE_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_resource(obj, *, user, request=None):
    _delete(obj, A.INSTITUTION_RESOURCE_DELETED, user=user, request=request)


def _with_training(lab, data):
    """Swap the requirement id for the lab's own requirement (a foreign id reads as unknown)."""
    if "training_requirement" not in data:
        return data
    data = dict(data)
    if (rid := data["training_requirement"]) is not None:
        from training.models import TrainingRequirement

        req = TrainingRequirement.objects.for_lab(lab).filter(pk=rid).first()
        if req is None:
            raise ValidationError({"training_requirement": "This training does not exist."})
        data["training_requirement"] = req
    return data


@transaction.atomic
def create_onboarding_item(*, lab, user, data, request=None):
    data = _with_training(lab, data)
    return _create(
        OnboardingItem, A.ONBOARDING_ITEM_CREATED, lab=lab, user=user, data=data, request=request
    )


@transaction.atomic
def update_onboarding_item(obj, *, user, data, request=None):
    data = _with_training(obj.lab, data)
    return _update(obj, A.ONBOARDING_ITEM_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_onboarding_item(obj, *, user, request=None):
    _delete(obj, A.ONBOARDING_ITEM_DELETED, user=user, request=request)


@transaction.atomic
def set_completion(item, *, member, done, by, request=None):
    lab = item.lab
    if not LabMembership.objects.for_lab(lab).filter(user=member).exists():
        raise ValidationError({"user": "This person is not a member of the lab."})
    qs = OnboardingCompletion.objects.for_lab(lab).filter(item=item, user=member)
    if done and not qs.exists():
        OnboardingCompletion.objects.create(lab=lab, item=item, user=member, completed_by=by)
    elif not done:
        qs.delete()
    else:
        return
    record(
        A.ONBOARDING_COMPLETION_CHANGED,
        actor=by,
        lab=lab,
        target=item,
        request=request,
        metadata={"user": str(member.pk), "done": done},
    )


@transaction.atomic
def create_inventory_item(*, lab, user, data, request=None):
    data = {**data, "owner": _members_only_owner(lab, data.pop("owner", None))}
    return _create(
        InventoryItem, A.INVENTORY_ITEM_CREATED, lab=lab, user=user, data=data, request=request
    )


@transaction.atomic
def update_inventory_item(obj, *, user, data, request=None):
    data = dict(data)
    if "owner" in data:
        data["owner"] = _members_only_owner(obj.lab, data["owner"])
    return _update(obj, A.INVENTORY_ITEM_UPDATED, user=user, data=data, request=request)


@transaction.atomic
def delete_inventory_item(obj, *, user, request=None):
    _delete(obj, A.INVENTORY_ITEM_DELETED, user=user, request=request)
