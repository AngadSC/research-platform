"""Project business logic (ARCHITECTURE section 0). Views validate and call these; write
actions record their audit event in the same transaction."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from audit.models import AuditAction
from audit.services import record
from core.models import User
from core.permissions import Perm, can, forget
from core.retention import audit_retention, guard_retention, retention_changes
from labs.models import LabMembership
from projects.models import (
    Project,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    Task,
    TaskStatus,
)

# ---------------------------------------------------------------- projects


@transaction.atomic
def create_project(*, lab, user, data, request=None) -> Project:
    changes = retention_changes(Project(), data)
    guard_retention(user, lab, changes)
    project = Project.objects.create(lab=lab, created_by=user, **data)
    audit_retention(user, lab, project, changes, request)
    ProjectMembership.objects.create(lab=lab, project=project, user=user, role=ProjectRole.LEAD)
    forget(user)
    record(AuditAction.PROJECT_CREATED, actor=user, lab=lab, target=project, request=request)
    return project


@transaction.atomic
def update_project(*, project, user, data, request=None) -> Project:
    changes = retention_changes(project, data)
    guard_retention(user, project.lab, changes)
    for key, value in data.items():
        setattr(project, key, value)
    project.save()
    record(
        AuditAction.PROJECT_UPDATED,
        actor=user,
        lab=project.lab,
        target=project,
        request=request,
        metadata={"fields": sorted(data)},
    )
    audit_retention(user, project.lab, project, changes, request)
    return project


@transaction.atomic
def delete_project(*, project, user, request=None) -> None:
    """Soft delete (D24, D28). Children stay; D39 hides them with the project."""
    project.deleted_at = timezone.now()
    project.save(update_fields=["deleted_at", "updated_at"])
    record(
        AuditAction.PROJECT_DELETED, actor=user, lab=project.lab, target=project, request=request
    )


# ---------------------------------------------------------------- members


@transaction.atomic
def add_member(*, project, by, user_id, role, request=None) -> ProjectMembership:
    lab = project.lab
    if not LabMembership.objects.for_lab(lab).filter(user_id=user_id).exists():
        raise ValidationError({"user": "This person is not a member of the lab."})
    if ProjectMembership.objects.for_lab(lab).filter(project=project, user_id=user_id).exists():
        raise ValidationError({"user": "This person is already on the project."})
    try:
        with transaction.atomic():
            membership = ProjectMembership.objects.create(
                lab=lab, project=project, user_id=user_id, role=role
            )
    except IntegrityError as exc:  # unique (project, user) under a race (D33)
        raise ValidationError({"user": "This person is already on the project."}) from exc
    record(
        AuditAction.PROJECT_MEMBERSHIP_ADDED,
        actor=by,
        lab=lab,
        target=membership,
        request=request,
        metadata={"user_id": str(user_id), "role": role},
    )
    return membership


@transaction.atomic
def change_member_role(*, membership, by, role, request=None) -> ProjectMembership:
    old = membership.role
    if role == old:
        return membership
    membership.role = role
    membership.save(update_fields=["role", "updated_at"])
    record(
        AuditAction.PROJECT_MEMBERSHIP_ROLE_CHANGED,
        actor=by,
        lab=membership.lab,
        target=membership,
        request=request,
        metadata={"user_id": str(membership.user_id), "old_role": old, "new_role": role},
    )
    return membership


@transaction.atomic
def remove_member(*, membership, by, request=None) -> None:
    record(
        AuditAction.PROJECT_MEMBERSHIP_REMOVED,
        actor=by,
        lab=membership.lab,
        target=membership,
        request=request,
        metadata={"user_id": str(membership.user_id), "role": membership.role},
    )
    membership.delete()


# ---------------------------------------------------------------- deadlines


@transaction.atomic
def create_deadline(*, project, data) -> ProjectDeadline:
    return ProjectDeadline.objects.create(lab=project.lab, project=project, **data)


@transaction.atomic
def update_deadline(*, deadline, data) -> ProjectDeadline:
    for key, value in data.items():
        setattr(deadline, key, value)
    deadline.save()
    return deadline


@transaction.atomic
def delete_deadline(*, deadline, by, request=None) -> None:
    record(
        AuditAction.DEADLINE_DELETED, actor=by, lab=deadline.lab, target=deadline, request=request
    )
    deadline.delete()


# ---------------------------------------------------------------- tasks


def _resolve_assignee(project, assignee_id):
    """The assignee must be able to view the project (checked through core.permissions)."""
    if assignee_id is None:
        return None
    user = User.objects.filter(pk=assignee_id, is_active=True).first()
    if user is None or not can(user, Perm.VIEW_PROJECT, project):
        raise ValidationError({"assignee": "The assignee must be able to view this project."})
    return user


def _place(task, status, position) -> None:
    """Put `task` at index `position` (None = end) of the `status` column and renumber it."""
    column = list(
        Task.objects.for_lab(task.lab_id)
        .select_for_update()
        .filter(project_id=task.project_id, status=status)
        .exclude(pk=task.pk)
        .order_by("position", "created_at", "id")
    )
    index = len(column) if position is None else max(0, min(position, len(column)))
    column.insert(index, task)
    for i, item in enumerate(column):
        if item.pk == task.pk:
            task.position = i
        elif item.position != i:
            Task.objects.for_lab(task.lab_id).filter(pk=item.pk).update(position=i)
    task.status = status


@transaction.atomic
def create_task(*, project, by, data) -> Task:
    data = dict(data)
    assignee = _resolve_assignee(project, data.pop("assignee", None))
    status = data.pop("status", TaskStatus.TODO)
    position = data.pop("position", None)
    task = Task(lab=project.lab, project=project, created_by=by, assignee=assignee, **data)
    _place(task, status, position)
    task.save()
    return task


@transaction.atomic
def update_task(*, task, data) -> Task:
    data = dict(data)
    if "assignee" in data:
        task.assignee = _resolve_assignee(task.project, data.pop("assignee"))
    status, position = data.pop("status", None), data.pop("position", None)
    for key, value in data.items():
        setattr(task, key, value)
    if status is not None or position is not None:
        _place(task, status or task.status, position)  # reorder within, or move across, columns
    task.save()
    return task


@transaction.atomic
def delete_task(*, task, by, request=None) -> None:
    record(AuditAction.TASK_DELETED, actor=by, lab=task.lab, target=task, request=request)
    task.delete()


# ---------------------------------------------------------------- retention (SPEC phase 5)


def retention_due(lab, today=None):
    """Projects and documents past `retain_until`, soft-deleted ones included (flag them with
    `deleted_at`). Read-only: nothing is ever deleted or changed because of retention.
    The caller holds view_retention on the lab, which sees every project in it."""
    from documents.models import Document

    today = today or timezone.localdate()
    projects = Project.objects.for_lab(lab).filter(retain_until__lt=today).order_by("retain_until")
    documents = (
        Document.objects.for_lab(lab)
        .filter(retain_until__lt=today)
        .select_related("project")
        .order_by("retain_until")
    )
    return list(projects), list(documents)
