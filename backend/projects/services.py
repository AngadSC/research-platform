"""Project business logic (ARCHITECTURE section 0). Views validate and call these; write
actions record their audit event in the same transaction."""

from collections import Counter

from django.db import IntegrityError, transaction
from django.db.models import Count, F, OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from audit.models import AuditAction
from audit.services import record
from core.models import NotificationKind, User
from core.notifications import notify
from core.permissions import Perm, can, forget, users_with
from core.retention import audit_retention, guard_retention, retention_changes
from labs.models import LabChatMessage, LabChatReadState, LabMembership
from projects import templates
from projects.models import (
    ChatMessage,
    ChatReadState,
    Project,
    ProjectColor,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    Task,
    TaskPost,
    TaskStatus,
)

# ---------------------------------------------------------------- projects


def next_project_color(lab) -> str:
    """The colour least used by the lab's live projects, so neighbours differ."""
    used = Counter(
        Project.objects.for_lab(lab).filter(deleted_at__isnull=True).values_list("color", flat=True)
    )
    return min(ProjectColor.values, key=lambda color: used[color])


@transaction.atomic
def create_project(*, lab, user, data, request=None) -> Project:
    data = dict(data)
    template = data.pop("template", "")
    changes = retention_changes(Project(), data)
    guard_retention(user, lab, changes)
    data = {"color": next_project_color(lab), **data}
    project = Project.objects.create(lab=lab, created_by=user, **data)
    audit_retention(user, lab, project, changes, request)
    ProjectMembership.objects.create(lab=lab, project=project, user=user, role=ProjectRole.LEAD)
    forget(user)
    if template:
        templates.apply(template, project, user)
    record(
        AuditAction.PROJECT_CREATED,
        actor=user,
        lab=lab,
        target=project,
        request=request,
        metadata={"template": template} if template else None,
    )
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
    forget(membership.user)
    record(
        AuditAction.PROJECT_MEMBERSHIP_ROLE_CHANGED,
        actor=by,
        lab=membership.lab,
        target=membership,
        request=request,
        metadata={"user_id": str(membership.user_id), "old_role": old, "new_role": role},
    )
    unassign_lost_access(
        membership.user, lab=membership.lab, by=by, request=request, reason="project_role_changed"
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
    unassign_lost_access(
        membership.user, lab=membership.lab, by=by, request=request, reason="removed_from_project"
    )


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
    if user is None or not can(user, Perm.EDIT_CONTENT, project):
        raise ValidationError({"assignee": "The assignee must be able to edit this project."})
    return user


def unassign_lost_access(user, *, lab, by=None, reason, request=None) -> int:
    """Unassign `user`'s open tasks (status not done) in every project of `lab`
    where they can no longer edit content. Call after the access change, in its transaction.
    `by=None` records a system actor. Notifies the project's leads, never `user`."""
    forget(user)
    tasks = (
        Task.objects.for_lab(lab)
        .filter(assignee=user, project__deleted_at__isnull=True)
        .exclude(status=TaskStatus.DONE)
    )
    count = 0
    for task in tasks.select_related("project", "lab").order_by("created_at", "id"):
        if can(user, Perm.EDIT_CONTENT, task.project):
            continue
        task.assignee = None
        task.save(update_fields=["assignee", "updated_at"])
        event = record(
            AuditAction.TASK_UNASSIGNED,
            actor=by,
            actor_label="" if by else "system",
            lab=task.lab,
            target=task,
            request=request,
            metadata={"previous_assignee_id": str(user.pk), "reason": reason},
        )
        for lead in users_with(Perm.EDIT_PROJECT, task.project).exclude(pk=user.pk):
            notify(
                lab=task.lab,
                recipient=lead,
                kind=NotificationKind.TASK_UNASSIGNED,
                title=f"Task unassigned: {task.title}",
                body=f"{user.display_name or user.email} lost access to {task.project.name}.",
                target=task,
                dedupe_key=f"task_unassigned:{event.pk}",
            )
        count += 1
    return count


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


# ---------------------------------------------------------------- chat


def post_message(*, project, by, body) -> ChatMessage:
    return ChatMessage.objects.create(lab=project.lab, project=project, author=by, body=body)


@transaction.atomic
def delete_message(*, message, by, request=None) -> None:
    """D206: authors remove their own messages; project leads remove anyone's. The text is really
    deleted, so something posted by mistake (a participant identifier) is gone. The audit event
    keeps who and when, never the text."""
    if message.author_id != by.pk and not can(by, Perm.EDIT_PROJECT, message):
        raise PermissionDenied
    record(
        AuditAction.CHAT_MESSAGE_DELETED,
        actor=by,
        lab=message.lab,
        target=message,
        request=request,
        metadata={"author": str(message.author_id)},
    )
    message.delete()


def mark_chat_read(*, project, user, read_to) -> None:
    """D207: `read_to` is the newest message the person saw, so a message that arrives while this
    request is on its way stays unread. It only moves forward (an older tab can't undo a newer
    one) and never past now."""
    read_to = min(read_to, timezone.now())
    states = ChatReadState.objects.for_lab(project.lab_id).filter(project=project, user=user)
    _, created = states.get_or_create(
        lab=project.lab, project=project, user=user, defaults={"last_read_at": read_to}
    )
    if not created:
        states.filter(last_read_at__lt=read_to).update(
            last_read_at=read_to, updated_at=timezone.now()
        )


def unread_chat_counts(*, user, lab) -> list[dict]:
    """Per project the user can see, plus the lab chat as a row with `project` None: messages from
    other people newer than their read position. Chats with nothing unread are left out."""
    read_at = (
        ChatReadState.objects.for_lab(lab)
        .filter(user=user, project=OuterRef("project"))
        .values("last_read_at")[:1]
    )
    rows = list(
        ChatMessage.objects.visible_to(user, lab)
        .exclude(author=user)
        .annotate(read_at=Subquery(read_at))
        .filter(Q(read_at__isnull=True) | Q(created_at__gt=F("read_at")))
        .order_by()
        .values("project")
        .annotate(count=Count("id"))
    )
    lab_read = LabChatReadState.objects.for_lab(lab).filter(user=user).first()
    lab_unread = LabChatMessage.objects.visible_to(user, lab).exclude(author=user)
    if lab_read:
        lab_unread = lab_unread.filter(created_at__gt=lab_read.last_read_at)
    if count := lab_unread.count():
        rows.append({"project": None, "count": count})
    return rows


# ---------------------------------------------------------------- task links and thread (Run 4)


def link_to_task(*, task, kind, obj) -> None:
    """Attach a document or attachment of the same project (D141). Idempotent. The ORM refuses
    a different lab or project, and the DB trigger backs that up."""
    if obj.project_id != task.project_id or obj.lab_id != task.lab_id:
        raise ValidationError({kind: "That item is not in this project."})
    if kind == "documents" and obj.deleted_at is not None:
        raise ValidationError({kind: "That document was deleted."})
    getattr(task, kind).add(obj)


def unlink_from_task(*, task, kind, obj) -> None:
    getattr(task, kind).remove(obj)


@transaction.atomic
def create_post(*, task, author, body) -> TaskPost:
    post = TaskPost.objects.create(lab=task.lab, task=task, author=author, body=body)
    assignee = task.assignee  # D142: in-app only; nobody is told about their own post
    if assignee is not None and assignee.pk != author.pk and assignee.is_active:
        notify(
            lab=task.lab,
            recipient=assignee,
            kind=NotificationKind.TASK_POST,
            title=f"New update on: {task.title}"[:200],
            body=f"{author.display_name or author.email}: {body[:200]}",
            target=task,
            dedupe_key=f"task_post:{post.pk}",
        )
    return post


@transaction.atomic
def edit_post(*, post, by, body) -> TaskPost:
    if post.author_id != by.pk:
        raise PermissionDenied("Only the author can edit a post.")
    post.body, post.edited_at = body, timezone.now()
    post.save()
    return post


@transaction.atomic
def delete_post(*, post, by, request=None) -> None:
    if post.author_id != by.pk and not can(by, Perm.EDIT_PROJECT, post.task.project):
        raise PermissionDenied("Only the author or a project lead can delete a post.")
    record(AuditAction.TASK_POST_DELETED, actor=by, lab=post.lab, target=post, request=request)
    post.delete()


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
