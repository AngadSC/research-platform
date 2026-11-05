# Architecture: data model, tenancy, permissions, audit

The design that implementation agents follow for phases 1 to 6. It refers to `SPEC.md` by section and to `DECISIONS.md` by D-number. If code disagrees with this file, fix the code or change this file on purpose. Don't let the two drift apart.

## 0. Ground rules

- Every PK is a UUID (D7). Every timestamp is timezone-aware UTC.
- **Lab data** means anything a lab creates. Every lab-data model inherits `LabScopedModel`, so it has a non-null `lab` FK.
- Users are never hard-deleted. They are deactivated instead (`is_active=False`). Every FK to `User` uses `PROTECT`. (D24)
- `Lab` and `Institution` are never deleted in this run. Every FK to them uses `PROTECT`.
- `Project` and `Document` are soft-deleted with `deleted_at`. Nothing is purged automatically (SPEC §2 phase 5). Their FKs to children use `CASCADE`, but that only runs on a manual purge.
- Business logic lives in `<app>/services.py`. Views validate input, call a service and serialize the result. Services write audit events.

## 1. Models

Notation: `name: Type [constraints]`. Every `LabScopedModel` also has `id`, `lab`, `created_at` and `updated_at` (see §2). `lab_parents` lists the FKs whose `lab_id` must equal `self.lab_id`. `project_path` is the ORM path to the owning `Project`, or `None` for lab-level objects.

### core
| Model | Fields | Notes |
|---|---|---|
| `User` (D16) | `id` UUID, `email` unique (case-insensitive unique index on `Lower(email)`), `display_name` char(120), plus AbstractUser fields without `username` | Not lab data. |
| `Institution` | `id`, `name` char(200) unique, `created_at` | A data migration creates one row, "Placeholder Institution". |

### labs
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Lab` (not LabScoped: it is the tenant) | `id`, `institution` FK PROTECT, `name` char(200), `created_by` FK User PROTECT, `created_at`, `updated_at` | index `(institution)` |
| `LabMembership` | `user` FK User PROTECT, `role` choice `pi\|lab_admin\|member\|viewer`, `invited_by` FK User PROTECT null | unique `(lab, user)`; index `(user)` |
| `Invite` | `email` (stored lower-cased), `role` lab-role choice, `token_hash` char(64) unique (sha256 hex), `invited_by` FK User PROTECT, `expires_at` (`created_at + 7 days`), `accepted_at` null, `accepted_by` FK User PROTECT null, `revoked_at` null | partial unique `(lab, email)` where `accepted_at IS NULL AND revoked_at IS NULL`; index `(expires_at)` |

The invite token is `secrets.token_urlsafe(32)` and appears only in the emailed link. The database stores only `sha256(token)`, and lookups hash the token they receive. An invite is usable only if it is not expired, not accepted and not revoked. Accepting it requires a logged-in user whose verified email matches `Invite.email` (D25). Accepting creates the `LabMembership` and sets `accepted_*` in one transaction. Only a PI can invite someone with the role `pi`.

### projects
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Project` | `name` char(200), `description` text, `status` choice `planning\|active\|paused\|completed\|archived`, `start_date` null, `created_by` FK User PROTECT, `retain_until` date null, `retention_note` text, `deleted_at` null | `project_path = ""` (itself); index `(lab, deleted_at)`, `(lab, retain_until)` |
| `ProjectMembership` | `project` FK CASCADE, `user` FK User PROTECT, `role` choice `lead\|contributor\|viewer` | `lab_parents=("project",)`; unique `(project, user)`; index `(lab, user)`. The service requires a `LabMembership` in the same lab. |
| `ProjectDeadline` | `project` FK CASCADE, `title` char(200), `due_date` date, `done` bool | `lab_parents=("project",)`; index `(project, due_date)` |
| `Task` | `project` FK CASCADE, `title` char(300), `description` text, `assignee` FK User PROTECT null, `due_date` null, `status` choice `todo\|in_progress\|done`, `position` int (board order), `created_by` FK User PROTECT | `lab_parents=("project",)`; index `(project, status, position)`, `(lab, assignee)` |
| `ChatMessage` | `project` FK CASCADE, `author` FK User PROTECT, `body` text | `lab_parents=("project",)`; index `(project, created_at)`; deleting is a real delete (D77) |
| `ChatReadState` | `project` FK CASCADE, `user` FK User PROTECT, `last_read_at` datetime | `lab_parents=("project",)`; unique `(project, user)` (D78) |

### documents
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Document` | `project` FK CASCADE, `title` char(300), `content` JSON (BlockNote blocks, max 2 MB), `version` int default 1 (D11), `created_by` FK User PROTECT (the owner), `updated_by` FK User PROTECT, `retain_until` date null, `retention_note` text, `deleted_at` null | `lab_parents=("project",)`; index `(project, deleted_at)`, `(lab, retain_until)` |
| `DocumentRevision` | `document` FK CASCADE, `version` int, `title`, `content` JSON, `created_by` FK User PROTECT, `restored_from` FK self SET_NULL null | `lab_parents=("document",)`, `project_path="document__project"`; unique `(document, version)` |
| `Attachment` | `project` FK CASCADE null, `ethics_approval` FK (Phase 5) null; DB check: exactly one of the two is set (D38), `storage_key` char(512) unique, `original_filename` char(255), `content_type` char(100), `size_bytes` bigint, `sha256` char(64), `uploaded_by` FK User PROTECT, `notice_acknowledged_at` datetime (non-null) | `lab_parents=("project",)`; `permission_domain="project"`, with ethics-owned files checked through their approval (`"lab"` domain, ethics perms); index `(project)`; max size 50 MB |

Every save goes through `documents.services.save_document(doc, *, title, content, base_version, user)`. It runs `select_for_update`, raises `Conflict` (HTTP 409) if `base_version != doc.version`, increments `version`, and writes a `DocumentRevision` with the new version. Creating a document writes revision 1. Restoring revision N saves N's content as a new revision with `restored_from` set. Restoring never rewrites history.

An upload is rejected (400) unless the form contains `acknowledged_notice=true`. The acknowledgement is stored on the row and in the audit metadata.

### provenance (every model is project-owned, D20)
| Model | Fields | Constraints / indexes |
|---|---|---|
| `DatasetRecord` | `project` FK CASCADE, `name` char(200), `location_text` text, `location_url` URL null, `controlled_by` FK User PROTECT null, `access_notes` text, `version_label` char(100), `checksum` char(140) blank (`sha256:<hex>` form), `created_by` | unique `(project, name, version_label)`. A new version is a new row. |
| `Analysis` | `project` FK CASCADE, `title`, `description`, `code_repo_url` URL blank, `code_commit` char(40) blank (hex), `code_attachment` FK Attachment PROTECT null, `datasets` M2M DatasetRecord, `ran_by` FK User PROTECT, `ran_at` datetime | check: (`code_repo_url` and `code_commit` are set) or `code_attachment` is set |
| `Result` | `project` FK CASCADE, `title`, `summary` text, `analysis` FK Analysis PROTECT, `attachments` M2M Attachment, `created_by` | `lab_parents=("project","analysis")` |
| `Decision` | `project` FK CASCADE, `title`, `rationale` text, `decided_on` date, `decided_by` FK User PROTECT, `supporting_documents` M2M Document, `supporting_attachments` M2M Attachment, `references` JSON list of `{title,url,doi}`, `analyses` M2M Analysis, `datasets` M2M DatasetRecord | |
| `ManuscriptLink` | `project` FK CASCADE, `title`, `url` URL, `status` choice `drafting\|submitted\|in_review\|accepted\|published`, `results` M2M Result, `created_by` | |

For all of these, `project_path="project"`. Every M2M target must be in the **same project**, not only the same lab. A `DatasetRecord` used by an `Analysis` cannot be deleted (409). Lineage edges come from the M2M and FK links above: dataset → analysis → result → manuscript, with decisions attached to analyses and datasets.

### ethics
| Model | Fields | Constraints / indexes |
|---|---|---|
| `EthicsApproval` | `approval_number` char(100), `board` char(200), `title`, `projects` M2M Project, `named_people` M2M User, `approval_date`, `expiry_date`, `status` choice `pending\|active\|expired\|withdrawn`, `attachments` M2M Attachment (with `project IS NULL`), `created_by` | `project_path=None` (lab-level, D27); unique `(lab, board, approval_number)`; index `(lab, status, expiry_date)` |

### notifications (in the `core` app)
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Notification` | `recipient` FK User PROTECT, `kind` choice `ethics_expiry\|retention_due\|invite_accepted\|task_assigned`, `title`, `body`, `target_type` char(64), `target_id` UUID null, `dedupe_key` char(200), `read_at` null | unique `(recipient, dedupe_key)`; index `(lab, recipient, read_at, created_at)` |

### audit
| Model | Fields | Constraints / indexes |
|---|---|---|
| `AuditEvent` (not LabScoped, see below) | `id`, `occurred_at` (db default `now()`), `lab` FK PROTECT **null** (null only for `auth.*`), `actor` FK User PROTECT null (null means system), `actor_label` char(100) (for example `job:ethics_reminders`), `action` char(64) from `AuditAction`, `target_type` char(64) (`app_label.Model`), `target_id` UUID null, `target_repr` char(200) (name at the time of the event), `project_id` UUID null (plain column, not an FK), `ip` inet null, `user_agent` char(256), `metadata` JSON | index `(lab, occurred_at DESC)`, `(lab, target_type, target_id)`, `(actor, occurred_at)` |

**Append-only enforcement (D23):** (1) `AuditEvent.save()` raises if `not self._state.adding`, and `delete()` raises. (2) `AuditQuerySet.update()` and `.delete()` raise. (3) A migration `RunSQL` installs a Postgres trigger that raises on `BEFORE UPDATE OR DELETE` and on `BEFORE TRUNCATE` for the table. It is skipped on SQLite (D15). (4) In production, the app's DB role gets only `INSERT, SELECT` on the table. Targets are plain UUIDs so audit rows never block a deletion and survive one.

### Keeping `lab` consistent (D31)
- `LabScopedModel.save()`: for each field in `lab_parents`, if `self.lab_id` is unset it is copied from the parent. If it is set and differs from the parent, the save raises `CrossLabError`. When `project_path` is set, the parent's project must also match the child's (for example, `Result.analysis.project_id == Result.project_id`).
- M2M: one `m2m_changed` receiver, registered for every M2M field between `LabScopedModel`s, rejects `pre_add` if any object in `pk_set` has a different `lab_id`, or a different `project_id` for provenance models.
- `LabScopedQuerySet.update()` raises if its kwargs include `lab` or any `lab_parents` field. `bulk_create` and `bulk_update` are banned for lab models outside services, and services validate the rows first.
- Serializer FK inputs use `ScopedPrimaryKeyRelatedField`, which resolves IDs through `visible_to(request.user, request.lab)`. An ID from another lab returns the same 400 "does not exist" as an ID that doesn't exist.
- **Database level (Postgres only, D15; migration `labs/0002_db_lab_consistency`).** `core/lab_db.py` holds two migration operations; any app adding lab-scoped models reuses them in its own migration:
  - `LabForeignKey(table, column, parent_table, on_delete)`: composite FK `(column, lab_id) → parent(id, lab_id)` (`DEFERRABLE INITIALLY DEFERRED`, like Django's), creating `UNIQUE (id, lab_id)` on the parent if absent. `on_delete` is `CASCADE`, `PROTECT` (NO ACTION) or `SET_NULL` (sets only the FK column). Nullable FKs stay nullable (MATCH SIMPLE).
  - `LabM2MTrigger(through_table, (left_table, left_col), (right_table, right_col), left_project, right_project)`: `BEFORE INSERT OR UPDATE` trigger on the through table calling `core_m2m_same_lab()`; it rejects a row whose sides differ in `lab_id`, and, when both project columns are given (`"project_id"`, or `"id"` for `projects_project`), in project (a NULL project fails, as in `_same_project`). Violations raise `check_violation`, which Django surfaces as `IntegrityError`.
  - Both first check existing rows and abort the migration naming the table, the row ids and both lab ids. Both are no-ops on SQLite. The trigger does not re-check links when a parent's `project_id` is later changed (the composite FKs already block a changed `lab_id`).
  - `tests/test_lab_db_constraints.py` introspects every FK and M2M between `LabScopedModel`s and fails if one has no composite FK or trigger, so a new model must add the operations. The app-level checks above stay.

## 2. Tenancy enforcement (`backend/core/tenancy.py`)

```
class LabScopedModel(models.Model):        # abstract
    id, lab = FK(Lab, PROTECT, related_name="+"), created_at, updated_at
    objects = LabScopedManager()           # default manager; raises unless scoped
    unscoped = models.Manager()            # explicit escape hatch
    lab_parents: ClassVar[tuple[str, ...]] = ()
    project_path: ClassVar[str | None] = None
    class Meta: abstract = True; base_manager_name = "unscoped"

class LabScopedQuerySet(QuerySet):
    def for_lab(self, lab: Lab | UUID) -> Self          # filter(lab=lab), marks scoped
    def visible_to(self, user, lab) -> Self             # for_lab + project visibility (permissions.visible_projects)
```

- **Unscoped queries raise (D18).** `LabScopedQuerySet` carries a `_scoped` flag through `_clone()`. Evaluating an unscoped queryset raises `UnscopedQueryError`. This covers `_fetch_all`, `count`, `exists`, `aggregate`, `iterator`, `in_bulk`, `contains`, `update`, `delete` and `explain`, so `get`, `first`, `values` and iteration are covered too. Raising beats returning `none()` because an empty list looks like a working feature, while an error fails the test.
- **Related managers:** `LabScopedManager.get_queryset()` detects a related manager (it has `self.instance`). If the parent instance has `lab_id`, the manager adds `filter(lab_id=instance.lab_id)` and marks itself scoped, so `project.tasks.all()` works. Reverse access from `User` (for example `user.task_set`) has no `lab_id` and still raises. `lab FK related_name="+"` removes `lab.<children>` accessors, so nothing can skip project visibility through the lab.
- `Manager.create()` is allowed, because `save()` validates the lab.
- **Where `unscoped` is allowed:** `core/tenancy.py`, `core/permissions.py`, `*/admin.py` (superuser only) and migrations. `use_in_migrations=False` on the scoped manager means historical models get a plain manager anyway. `tests/test_tenancy_lint.py` greps for `.unscoped` and `_base_manager` outside those files and fails. Celery jobs don't need `unscoped`: they loop over `Lab.objects.all()` and call `.for_lab(lab)`.
- **Known gap:** an unscoped queryset used as a subquery (`filter(x__in=Model.objects.filter(...))`) compiles without being evaluated, so the guard never fires. Review for it and let the matrix and cross-lab tests catch it.
- Lab model serializers inherit `LabModelSerializer`, which drops DRF's auto-generated unique validators (they would query `_default_manager` without a scope). Uniqueness comes from DB constraints, and services turn `IntegrityError` into a 400 (D33).

**Views.** Every lab endpoint lives under `/api/labs/<uuid:lab_id>/` (D22). `LabScopedViewMixin.initial()` runs after authentication:
1. Anonymous: 401. `core.auth.SessionAuthentication` sets `authenticate_header`, so DRF returns 401 instead of 403.
2. `request.lab = permissions.get_lab_or_404(user, lab_id)`. A lab that doesn't exist and a lab the user isn't a member of both return the same 404.
3. Collection routes nested under a project (`/projects/<uuid:project_id>/tasks/`) resolve `view.project = visible_projects(user, lab).get(pk=project_id)`, or 404.
4. `get_queryset()` is fixed by the mixin as `Model.objects.visible_to(user, request.lab)`, plus `filter(project=view.project)` on nested routes. Subclasses may only add filters on top.
5. Item routes are flat (`/api/labs/<lab_id>/tasks/<uuid:task_id>/`), so each URL has at most one parent to check. `get_object()` looks up the ID inside that scoped queryset, so an ID from another lab is a 404.

**404 vs 403 (D21):** 401 for anonymous users. 404 when the lab, project or object isn't visible to the user, including other labs and projects they aren't on, so existence never leaks. 403 when the object is visible but the action isn't allowed (for example, a project viewer editing a task). URL kwargs are always named `<model>_id`. Bare `pk` is never used, which lets the matrix fill in URLs automatically.

## 3. Permission module (`backend/core/permissions.py`)

```
class Perm(StrEnum):  # lab-level
    VIEW_LAB, MANAGE_LAB, MANAGE_MEMBERS, MANAGE_BILLING, VIEW_AUDIT_LOG,
    CREATE_PROJECT, VIEW_ETHICS, EDIT_ETHICS, VIEW_RETENTION,
    MANAGE_INTEGRATIONS, MANAGE_LAB_INTEGRATIONS          # section 9
                      # project-level
    VIEW_PROJECT, EDIT_PROJECT, EDIT_CONTENT, MANAGE_PROJECT_MEMBERS, EXPORT, DELETE_PROJECT
    # pseudo: PUBLIC, AUTHENTICATED

def lab_role(user, lab) -> LabRole | None
def project_role(user, project) -> ProjectRole | None       # effective role (see below)
def get_lab_or_404(user, lab_id) -> Lab
def can(user, perm: Perm, target: Lab | Project | LabScopedModel) -> bool
def require(user, perm, target) -> None   # Http404 if target not visible, PermissionDenied otherwise
def visible_projects(user, lab) -> QuerySet[Project]          # non-deleted, user may view
def scope(model, user, lab) -> QuerySet                       # == model.objects.visible_to(user, lab)
def users_with(perm, target) -> QuerySet[User]                # recipients for jobs
class HasPerm(BasePermission)   # DRF; reads view.perms
```

- **Resolving the target:** a `Lab` is checked against lab perms. A `Project` is checked against project perms. A `LabScopedModel` with a `project_path` resolves to its project. Every `LabScopedModel` declares `permission_domain = "project"` (with a `project_path`) or `"lab"` (`project_path=None`; `EDIT_CONTENT`/`VIEW_PROJECT` map to `EDIT_ETHICS`/`VIEW_ETHICS`). A null FK is never read as lab-level (D38): an undeclared domain, an unresolvable owner, a soft-deleted project or its children (D39), or a project from another lab is denied by `can`, `require` and `users_with`. Any target whose lab the user isn't in returns `False`.
- **`HasPerm`:** views declare `perms = {"list": Perm.VIEW_PROJECT, "create": Perm.EDIT_CONTENT, ...}`, keyed by viewset action or HTTP method. `has_permission` checks against `view.project`, or `request.lab` when there's no project. `has_object_permission` checks against the object. `REST_FRAMEWORK["DEFAULT_PERMISSION_CLASSES"] = ["core.permissions.HasPerm"]`, and a view with no `perms` entry for an action is **denied**, so the default is closed.
- Membership lookups are memoized per user object (`user._perm_cache`, which lasts one request or one job run).
- **Background jobs:** a user-initiated job (a future async export, for example) passes `user_id` and re-runs `require()` when it executes, because roles may have changed. System jobs (reminders, retention) act on no one's behalf. They scope with `for_lab(lab)` and choose recipients with `users_with()`.
- **Future search and AI:** candidates must come from `scope(model, user, lab)`, and each hit passes `can(user, VIEW_*, obj)` before it is returned. Index entries carry `lab_id` and `project_id`, and every query filters on both. Nothing reads lab data any other way.

**Lab roles:**

| Perm | pi | lab_admin | member | viewer |
|---|---|---|---|---|
| view_lab (lab, member list, own notifications) | Y | Y | Y | Y |
| manage_lab | Y | Y | - | - |
| manage_members (invite, role change, remove) | Y | Y | - | - |
| manage_billing (no endpoint this run) | Y | - | - | - |
| view_audit_log | Y | Y | - | - |
| create_project (the creator becomes lead) | Y | Y | Y | - |
| view_ethics | Y | Y | Y | Y |
| edit_ethics | Y | Y | Y | - |
| view_retention | Y | Y | - | - |
| delete_project | Y | Y | - | - |
| manage_integrations (connect and disconnect your own accounts, section 9) | Y | Y | Y | Y |
| manage_lab_integrations (see and revoke any member's connected account) | Y | Y | - | - |

Only a PI can grant, change or remove the `pi` role. A lab must always have at least one PI (the service rejects the change with 400).

**Project roles (effective):**

| Perm | lead | contributor | viewer |
|---|---|---|---|
| view_project | Y | Y | Y |
| edit_content (tasks, documents, attachments, provenance) | Y | Y | - |
| edit_project (fields, status, deadlines, retention) | Y | - | - |
| manage_project_members | Y | - | - |
| export | Y | - | - |

**How the roles combine (D19):** `pi` and `lab_admin` act as an implicit `lead` on every project in the lab. A `member` gets the role from their `ProjectMembership`, and has no access without one. A lab `viewer` gets the `ProjectMembership` role **capped at viewer**. Without a `LabMembership`, the user has no access at all, even if a `ProjectMembership` row exists. Removing a lab member deletes their project memberships in the same transaction.

**The sensitive permissions** are `manage_members`, `export`, `view_audit_log`, `manage_billing` and `delete_project`. Each one has its own audit action, and none is implied by an edit permission.

## 4. Audit API (`backend/audit/services.py`)

```
def record(action: AuditAction, *, actor: User | None, lab: Lab | None,
           target: models.Model | None = None, request: HttpRequest | None = None,
           metadata: dict | None = None, actor_label: str = "") -> AuditEvent
```
`record()` fills `target_type`, `target_id`, `target_repr` and `project_id` from the target, and `ip` and `user_agent` from the request. `X-Forwarded-For` is trusted only when `settings.TRUSTED_PROXY_COUNT > 0`. An unknown action raises. For write actions, the service calls `record()` inside the same transaction as the change. For read actions, the view calls it once the permission check has passed.

| Action | Called from |
|---|---|
| `auth.login`, `auth.login_failed`, `auth.logout`, `auth.password_changed`, `auth.mfa_enabled`, `auth.mfa_disabled` (lab null) | `core/auth.py` signal receivers (Django `user_logged_in`, `user_login_failed`, `user_logged_out`; allauth `password_changed`, mfa `authenticator_added` and `authenticator_removed`) |
| `lab.created`, `lab.updated` | `labs.services.create_lab`, `update_lab` |
| `membership.invited`, `membership.invite_revoked`, `membership.invite_accepted`, `membership.role_changed`, `membership.removed` | `labs.services` invite, revoke, accept, change_role, remove_member |
| `project_membership.added`, `project_membership.role_changed`, `project_membership.removed` | `projects.services` member functions |
| `project.created`, `project.updated`, `project.deleted` | `projects.services` |
| `project.exported` | `projects.services.export_project` |
| `document.viewed` | document detail view and revision detail view (GET) |
| `document.restored`, `document.deleted` | `documents.services` |
| `attachment.uploaded` (metadata `notice_acknowledged_at`), `attachment.downloaded`, `attachment.deleted` | `documents.services.upload_attachment`, download view, `delete_attachment` |
| `<model>.deleted` for `task`, `deadline`, `dataset`, `analysis`, `result`, `decision`, `manuscript`, `ethics_approval` | the delete service for each |
| `audit_log.viewed` | audit list view |
| `integration.connected`, `integration.disconnected` (own account), `integration.revoked` (someone else's, or lifecycle with actor null), `integration.refresh_failed` (actor null, `actor_label="integrations:refresh"`) | `integrations.services` (section 9) |
| `external_link.created`, `external_link.removed` | the external-link services (next phase, section 9) |
| `handover.generated` | handover views |

Creating and editing ordinary content is not audited, because revisions and `updated_by` already cover it. Role changes are the "permission changes" that SPEC §2 phase 2 asks for.

## 5. Endpoints (phases 1 to 6)

`L = /api/labs/<lab_id>`, `P = L/projects/<project_id>`. Where a row lists two perms, the first applies to GET and the second to POST, PATCH, PUT or DELETE.

| Ph | Method | Path | Perm |
|---|---|---|---|
| 1 | GET, PATCH | `/api/me/` | AUTHENTICATED |
| 1 | GET, POST | `/api/labs/` (lists own labs; creating a lab makes you PI) | AUTHENTICATED |
| 1 | GET / PATCH | `L/` | view_lab / manage_lab |
| 1 | GET | `L/members/` | view_lab |
| 1 | PATCH, DELETE | `L/members/<membership_id>/` | manage_members |
| 1 | GET, POST | `L/invites/` | manage_members |
| 1 | DELETE | `L/invites/<invite_id>/` | manage_members |
| 1 | POST | `/api/invites/preview/` (token in body; returns lab name and role) | PUBLIC |
| 1 | POST | `/api/invites/accept/` | AUTHENTICATED (email must match) |
| 2 | GET | `L/audit-events/` (filter by actor, action, target, date) | view_audit_log |
| 3 | GET / POST | `L/projects/` (GET lists visible projects only) | view_lab / create_project |
| 3 | GET / PATCH / DELETE | `P/` | view_project / edit_project / delete_project |
| 3 | GET / POST | `P/members/` | view_project / manage_project_members |
| 3 | PATCH, DELETE | `L/project-members/<projectmembership_id>/` | manage_project_members |
| 3 | GET / POST | `P/deadlines/` | view_project / edit_project |
| 3 | PATCH, DELETE | `L/deadlines/<projectdeadline_id>/` | edit_project |
| 3 | GET / POST | `P/tasks/` | view_project / edit_content |
| 3 | GET / PATCH, DELETE | `L/tasks/<task_id>/` | view_project / edit_content |
| 3 | GET, POST | `P/messages/` (`?before=<created_at>` pages back) | view_project (D77) |
| 3 | DELETE | `L/messages/<chatmessage_id>/` | view_project, then author or edit_project in `delete_message` |
| 3 | POST | `P/messages/read/` | view_project (D78) |
| 3 | GET | `L/chat/unread/` (only projects the user can see) | view_lab (D78) |
| 3 | GET / POST | `P/documents/` | view_project / edit_content |
| 3 | GET / PUT, DELETE | `L/documents/<document_id>/` (PUT takes `base_version`; a stale save gets 409) | view_project / edit_content |
| 3 | GET | `L/documents/<document_id>/revisions/` and `.../revisions/<int:version>/` | view_project |
| 3 | POST | `L/documents/<document_id>/revisions/<int:version>/restore/` | edit_content |
| 3 | GET / POST | `P/attachments/` (multipart, `acknowledged_notice=true`) | view_project / edit_content |
| 3 | GET / DELETE | `L/attachments/<attachment_id>/` | view_project / edit_content |
| 3 | GET | `L/attachments/<attachment_id>/download/` | view_project (ethics files: view_ethics) |
| 4 | GET / POST | `P/datasets/`, `P/analyses/`, `P/results/`, `P/decisions/`, `P/manuscripts/` | view_project / edit_content |
| 4 | GET / PATCH, DELETE | `L/datasets/<datasetrecord_id>/`, `L/analyses/<analysis_id>/`, `L/results/<result_id>/`, `L/decisions/<decision_id>/`, `L/manuscripts/<manuscriptlink_id>/` | view_project / edit_content |
| 4 | GET | `P/lineage/` (nodes and edges for React Flow) | view_project |
| 4 | POST | `P/export/` (JSON: metadata, tasks, latest documents, provenance; no file bytes) | export |
| 5 | GET / POST | `L/ethics-approvals/` | view_ethics / edit_ethics |
| 5 | GET / PATCH, DELETE | `L/ethics-approvals/<ethicsapproval_id>/` | view_ethics / edit_ethics |
| 5 | POST | `L/ethics-approvals/<ethicsapproval_id>/attachments/` | edit_ethics |
| 5 | GET | `L/notifications/` (own notifications only) | view_lab |
| 5 | POST | `L/notifications/<notification_id>/read/` (another user's notification returns 404), `L/notifications/read-all/` | view_lab |
| 5 | GET | `L/retention/due/` | view_retention |
| 6 | GET | `L/members/<membership_id>/handover/` | manage_members, or the target is the requester |
| 6 | GET | `P/handover/?user=<user_id>` | manage_project_members |

The handover report is built in `projects/handover.py` from `scope(..., requester, lab)`, so it never shows the requester anything they can't otherwise see. "No other owner" means projects where the person is the only lead, documents they created, and datasets they control where no other project member holds `edit_content`.

**Jobs (Celery beat, daily):**
- `ethics.jobs.mark_expired` sets `status=expired` once `expiry_date < today`.
- `ethics.jobs.send_expiry_reminders` notifies the leads of linked projects and the lab PIs. It sends only the tightest threshold crossed (60, 30 or 7 days), with `dedupe_key = ethics:<id>:<threshold>:<expiry_date>` (D29). So an approval expiring in 25 days gets the 30-day reminder only, and a renewal re-arms the reminders.
- `projects.jobs.retention_scan` notifies the PIs about each project or document past `retain_until`. Soft-deleted items are included and flagged. The job never deletes anything.

Emails go through the console backend (D14).

## 6. Permission matrix test (`backend/tests/test_permission_matrix.py`)

**Enumeration.** The test walks `get_resolver().url_patterns` recursively and collects `(method, url_name)` for each pattern. For ViewSets it uses `callback.actions`. For APIViews it uses `callback.cls.http_method_names` filtered to the methods the class actually implements. HEAD and OPTIONS are left out, and a separate test checks that OPTIONS on a lab URL returns 404 for outsiders. `EXEMPT_PREFIXES = ["/_allauth/", "/admin/"]`, each with a comment explaining the exemption. The schema and docs URLs are mounted only when `DEBUG` is on. Two assertions:
1. `discovered - MATRIX.keys()` is empty. Otherwise the test fails and lists the missing endpoints.
2. `MATRIX.keys() - discovered` is empty, so stale entries fail too.

**Fixtures** are built once per session (overriding `django_db_setup`), and each case runs in a rolled-back transaction:
- Lab A holds project `P1` and one of every model inside P1: a task, a deadline, a document with 2 revisions, a PDF attachment, a dataset, an analysis, a result, a decision and a manuscript. It also holds an ethics approval linked to P1 with its own attachment, a pending invite, and a notification addressed to `pi`. Lab A has a second project, `P2`, with no members.
- Lab B mirrors all of that, and its PI is the `outsider` persona.
- Personas (the order is fixed): `anon`, `outsider`, `pi`, `admin` (lab_admin), `lead` (member, lead on P1), `contrib` (member, contributor on P1), `pviewer` (member, viewer on P1), `nonproj` (member, not on P1), `lviewer` (lab viewer, contributor on P1, which gets capped to viewer).
- URL kwargs are filled from `OBJECTS[kwarg_name]`, which maps `lab_id` and `<model>_id` to the Lab A fixture IDs. `membership_id` is `contrib`'s membership.
- `PAYLOADS[(method, url_name)]` is a callable `(persona, objs) -> dict` that returns a **valid** body, so an allowed request returns 2xx rather than 400. It may create objects it needs, for example an invite in a fresh lab addressed to the persona's email.

**Expected-result format.** The expected codes are written by hand (D32). They are never derived from the role tables, so the matrix is an independent check on them:
```
MATRIX: dict[tuple[str, str], str] = {
  #                                     anon outsider pi admin lead contrib pviewer nonproj lviewer
  ("GET",    "projects:project-detail"): "401 404     2  2     2    2       2       404     2",
  ("PATCH",  "projects:project-detail"): "401 404     2  2     2    403     403     404     403",
  ("DELETE", "projects:project-detail"): "401 404     2  2     403  403     403     404     403",
  ("GET",    "audit:event-list"):        "401 404     2  2     403  403     403     403     403",
}
```
The tokens are `2` (any 2xx), `401`, `403` and `404`. One test is parametrized over every `(endpoint, persona)` pair.

**Cross-lab ID swap.** For every endpoint that has an object kwarg, the test acts as `pi` of Lab A twice. Once with Lab A's `lab_id` and Lab B's object ID, and once with Lab B's `lab_id`. Both must return 404. The response body must not contain any Lab B fixture name. This is the acceptance check for SPEC §2 phase 1.

## 7. Auth module boundary (`backend/core/auth.py`)

- **allauth headless, session mode** (D6): `HEADLESS_ONLY=True`, and the SPA calls `/_allauth/browser/v1/...`. Login is by email (`ACCOUNT_LOGIN_METHODS={"email"}`), and `ACCOUNT_EMAIL_VERIFICATION="mandatory"`. Invites rely on verified emails (D25). allauth's default rate limits stay on.
- `core/auth.py` holds the `AccountAdapter`, `HeadlessAdapter` and `SocialAccountAdapter`, the audit signal receivers, the `SessionAuthentication` subclass that returns 401, `has_verified_email(user, email)` (D25), and `login_methods_for_email(email)`. That last function returns `["password"]` for now and is the hook for SSO routing. **No other module imports allauth.** App code only reads `request.user`.
- **Google sign-in** (`allauth.socialaccount` + the Google provider, D62): scopes `openid email profile` only, with no provider tokens stored. The app comes from `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`. When those are unset there's no app, the headless config lists no provider, and the SPA hides the button. Provider callbacks are served under `/accounts/` (`allauth.urls`, which is only provider URLs when `HEADLESS_ONLY` is on), and Vite proxies `/accounts` like `/_allauth`. That makes the redirect URI `{FRONTEND_URL}/accounts/google/login/callback/`. The SPA starts the flow with a top-level form POST (not fetch) to `/_allauth/browser/v1/auth/provider/redirect` with `provider=google`, `process=login|connect`, `callback_url=/account/provider/callback` and `csrfmiddlewaretoken`. Google then redirects back through `/accounts/...` to `callback_url`, with `?error=...` on failure (`HEADLESS_FRONTEND_URLS["socialaccount_login_error"]` is the same route). The SPA then reads `GET /auth/session`, which returns either an authenticated session or a pending stage such as `verify_email`. Linking, in `SocialAccountAdapter.authenticate_by_email`, happens only when Google's email is verified and matches a *verified* local address, primary or secondary. Every other case creates a new account or goes through D62. Connected accounts are listed and disconnected at `/_allauth/browser/v1/account/providers` (GET, DELETE). allauth refuses to disconnect the last provider from an account without a usable password.
- **Extra email addresses:** allauth headless `/_allauth/browser/v1/account/email` handles list (GET), add (POST, which sends a verification mail), set primary (PATCH, verified addresses only), resend (PUT) and remove (DELETE). Verification goes through `/auth/email/verify`. A verified address belongs to one account at most (allauth's `unique_verified_email` constraint plus `can_set_verified`). Audit: `auth.email_added`/`auth.email_removed` and `auth.social_connected`/`auth.social_disconnected` (connect, or a new account created by Google).
- **Account-change hardening (D72 to D74):** added addresses confirm only when logged in as their account (`core.auth.VerifyEmailView`, routed before allauth's), and Google links by email only for gmail.com or a matching `hd` claim. Sensitive changes need reauthentication (401 with flows; the SPA's `useReauth` prompts and retries). Max 5 addresses; `manage_email` is 5 an hour. The One Tap token endpoint is not routed.
- **SSO and SAML later:** add the SAML provider to `allauth.socialaccount` (python3-saml and xmlsec are MIT; check the licenses when adding them). Add `Institution.sso_config` (JSON) and `Institution.email_domains`, and have `login_methods_for_email` route institutional domains to the IdP. Nothing outside `core/auth.py` and the settings needs to change.
- **MFA:** `allauth.mfa` with `MFA_SUPPORTED_TYPES=["totp","recovery_codes"]`. It is optional per user. A later per-lab "require MFA" setting would be a `Lab` field that `get_lab_or_404` checks.
- **Cookies:** session and CSRF cookies are `Secure` in production and `SameSite=Lax`. The session cookie is HttpOnly. The CSRF cookie is readable by the SPA. `SESSION_COOKIE_AGE` is 7 days.

## 8. File storage

- `STORAGES["lab_files"]`: `FileSystemStorage(location=/data/lab_files)` in dev and `S3Storage(default_acl="private", querystring_auth=False, bucket=env)` in production. It is a separate alias from static files and is never routed under `MEDIA_URL` or `static()`.
- **Key layout:** `labs/<lab_id>/attachments/<attachment_id>`. The original filename lives only in the database, so keys need no sanitizing. `storage_key` is set by `upload_attachment` and is never accepted from the client.
- **Download** goes only through `L/attachments/<attachment_id>/download/`: scoped `get_object()`, then `require(VIEW_*)`, then `audit.record("attachment.downloaded")`, then `FileResponse(storage.open(key))` (D26). Response headers:
  - `Content-Disposition: attachment`, except PDFs, which are `inline` for PDF.js.
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: sandbox`
  - `Cache-Control: private, no-store`

  No presigned or public URL is ever issued. The limit of this approach is that large files hold a worker while they stream. The upgrade path is `X-Accel-Redirect` or a presigned URL lasting 60 seconds or less, issued after the same checks.
- **Upload:** the server enforces the 50 MB limit, computes `sha256`, and stores the content type the client declared. The file is never executed or rendered on the server.

## 9. Integrations (`backend/integrations/`)

The framework for outside services: Google Drive first, then Microsoft, Overleaf, REDCap and Qualtrics. The security core (registry, models, crypto, HTTP client, OAuth flow services) exists. Endpoints, the permission-matrix rows, lifecycle hooks, the UI and Drive itself are the next phase and follow this section.

### Registry (`integrations/registry.py`)
Providers are code, not a database table. `Provider` is a frozen dataclass: `name` (the key stored on rows), `label`, `auth_type` (`oauth2 | api_key | link_only`), `scopes` (the **only** scopes that can ever be requested), `icon`, `authorize_url`, `token_url`, `revoke_url`, `identity_url` + `parse_identity(json) -> (external_id, email)`, `api_hosts` (the hosts a token may be sent to) and `authorize_params` (fixed extra authorize-URL params). Client credentials come from `settings.INTEGRATION_CLIENTS[name]`; a provider without them is "not configured" and can't be connected. `PROVIDERS` holds `google` today. Tests register `integrations/tests/fake.py::FAKE` with `monkeypatch.setitem(PROVIDERS, ...)` and swap `integrations.http._session` for `FakeTransport`.

### Models
| Model | Fields | Constraints / notes |
|---|---|---|
| `ConnectedAccount` | `user` FK User PROTECT, `provider` char(40), `external_account_id`, `external_email`, `granted_scopes` JSON list, `status` `active\|expired\|revoked\|error`, `access_token_ct`, `refresh_token_ct` (Fernet ciphertext, `editable=False`), `token_expires_at`, `connected_at`, `last_used_at` (last successful provider call) | `permission_domain="lab"`. Unique `(lab, user, provider, external_account_id)`; partial unique `(lab, user, provider)` where active (D69). `visible_rows`: own rows, or all with `manage_lab_integrations` (D54 pattern). Never deleted: a revoked row keeps its links' history, tokens wiped. |
| `ExternalLink` | `project` FK CASCADE; at most one of `document`, `dataset`, `analysis`, `result`, `manuscript` (FKs SET_NULL, DB check `externallink_at_most_one_target`); `provider`, `connected_account` FK PROTECT null (the linker's account, used for freshness; null for link_only), `external_id`, `url` (http/https only), `title`, `mime_type`, `linked_by` FK User PROTECT, `linked_modified_at`/`linked_version` (baseline at link time), `remote_modified_at`/`remote_version`/`remote_checksum` (last seen), `last_checked_at`, `unavailable_since` | `permission_domain="project"`, `project_path="project"`, `lab_parents` = project, the five targets, `connected_account`, so the target is in the same project and the account in the same lab (D31). Composite `(fk, lab_id)` FKs via `core.lab_db.LabForeignKey` in `integrations/0001`. `changed_since_linked`: versions differ, or (no versions) remote modified time is later than the baseline. "No longer available" = `unavailable_since` set. |

Statuses: `expired` means the provider refused a refresh (`invalid_grant`, or no refresh token): the user must reconnect. `revoked` means we wiped the tokens (disconnect, admin revoke, lifecycle). `error` means our side is wrong (client rejected, provider not configured). Only `active` accounts are ever used.

### Token storage and rotation (D63)
- Tokens are encrypted with `MultiFernet` over `INTEGRATION_ENCRYPTION_KEYS` (comma-separated, newest first). New ciphertext uses the first key; any listed key decrypts.
- Outside DEBUG a missing value refuses startup. In DEBUG a random dev key comes from the git-ignored `backend/.dev_integration_key` (the D49 pattern). `IntegrationsConfig.ready()` builds the MultiFernet, so a malformed key fails at startup, and the error never echoes key material.
- Rotation: put the new key first, deploy, run `manage.py rotate_integration_keys` (re-encrypts every token under the first key), then drop the old key.
- Plaintext exists only in the return value of `account.access_token()` / `refresh_token()`. Ciphertext lives in `editable=False` fields, so ModelForms, the admin and generic serializers never get even the ciphertext. `__str__` is `provider: email`.
- Tokens never appear in API responses, logs, audit metadata, notification text, exception messages, reprs or the admin. Functions that hold tokens use `@sensitive_variables`, so Django error reports mask them. `integrations/tests/test_token_leaks.py` enforces this (below). The one planned exception is the Picker token (D70).

### HTTP client (`integrations/http.py`, D67)
`send(method, url, *, provider, account=None, **requests_kwargs) -> Response` is the only way out:
- HTTPS only, and only to a host in `provider.api_hosts`; anything else raises before a socket opens. Redirects are never followed automatically: a redirect to another scheme, host or port raises, and same-origin redirects are followed (max 3) for GET and HEAD only.
- Timeouts `(5, 20)` seconds. GET, HEAD, OPTIONS, PUT and DELETE retry up to 3 attempts on network errors and 429/500/502/503/504, backing off 0.5 s doubling, honouring `Retry-After`, capped at 8 s. POST is never retried.
- With `account`: it must be `active` (else `AccountUnavailable`). A token expiring within 60 s is refreshed first; a 401 triggers one refresh and one retry. Refresh runs under `select_for_update`, so concurrent callers refresh once. Successful calls update `last_used_at`.
- Refresh outcomes: success stores the new access token (and a rotated refresh token if the provider sends one). `invalid_grant` or no refresh token: `expired`. Other 4xx: `error`. Either way the tokens are wiped, `integration.refresh_failed` is audited (metadata `provider`, `reason`, `status`) and the owner gets an `integration_issue` notification (deduped per connection). Network errors, 429 and 5xx are transient: nothing changes and `IntegrationError` is raised.
- Logs carry method, host, path and status. Never headers, bodies or query strings. Exceptions carry a fixed message; provider error codes are passed on only if they match `^[a-z_]{1,40}$`, and requests' exceptions (which hold the prepared request) are dropped with `from None`.
- Callers get the response for any status and decide what it means (for Drive, 404 means "no longer available").

### OAuth2 connect flow (`integrations/services.py`, D65, D66)
Separate from Google sign-in (allauth, `openid email profile` only, section 7). Callback: **`/api/integrations/oauth/callback/`** for every provider, under `/api/` so the Vite proxy covers it. `settings.INTEGRATION_OAUTH_REDIRECT_URI = FRONTEND_URL + that path`, so the local redirect URI to register is **`http://localhost:5173/api/integrations/oauth/callback/`**.
1. `start_connect(request, lab, provider_name, scopes=None) -> authorization_url`: `require(manage_integrations, lab)`; scopes must be a subset of the registry's (default: all of them). Creates a 256-bit `state` and a PKCE verifier and stores `{user, lab, provider, scopes, verifier, at}` under `session["integrations.oauth"][state]` (at most 5 pending, 10 minute lifetime). The URL carries `code_challenge` (S256), the redirect URI, the scopes, the provider's fixed params (Google: `access_type=offline`, `prompt=consent`, `include_granted_scopes=true` for incremental authorization) and `login_hint` = the email of the user's current account, so a scope upgrade lands on the same account.
2. `complete_connect(request, *, state, code, error) -> ConnectedAccount`: pops the state (single use, even on failure). It fails with `invalid_state` unless the state exists in **this session**, is fresh, and belongs to `request.user`. Then it re-runs `get_lab_or_404` and `require(manage_integrations)`, because the role may have changed. It exchanges the code with the verifier and client secret, checks every requested scope was granted (`scope_not_granted` otherwise), and fetches the identity. Then, under a row lock: if another external account of this provider is active for the user in this lab, it refuses (`other_account_connected`: disconnect first). The same external account reuses its row (tokens, scopes, status active); otherwise a new row is created. Audits `integration.connected` with metadata `provider` and `scopes`.
3. `OAuthError.code` is one of `invalid_state`, `access_denied`, `provider_error`, `invalid_request`, `invalid_scope`, `unknown_provider`, `provider_not_configured`, `scope_not_granted`, `identity_failed`, `other_account_connected`. It is safe to put in a redirect query string.
4. A token from a failed connect is discarded, never stored, and not revoked (D68).

Security properties: state is unguessable, single-use, short-lived and bound to the server-side session, the user, the lab and the provider (login CSRF and code injection fail). PKCE binds the code to the browser that started the flow. The provider (so the token endpoint) comes from the stored state, never from the callback request (no mix-up). The redirect URI is fixed in settings. Scopes come only from the registry. The SPA never sees a code or a token. The PKCE verifier sits in the server-side session until the callback consumes it.

### Disconnect and revoke
`disconnect(account, *, actor, request=None, actor_label="")`: the owner needs `manage_integrations` (audit `integration.disconnected`); anyone else needs `manage_lab_integrations` (audit `integration.revoked`); `actor=None` is a system revoke with `actor_label`. Under a row lock it calls the provider's revoke URL with the refresh token (or the access token), best effort. It then marks the row `revoked` and wipes the tokens whatever the provider said, and audits with metadata `provider_revoked: bool`. The provider call is skipped when the same external account is active for this user in another lab, because Google revokes the whole grant (D68). It is idempotent.

### Lifecycle
- **Member removed from a lab, or user deactivated:** call `integrations.services.revoke_member_accounts(lab, user, reason="member_removed" | "user_deactivated")` for each affected lab, via `transaction.on_commit` (it makes HTTP calls). Their `ExternalLink`s stay. Freshness checks for them stop, because the linker's account is revoked.
- **Handover** (section 5, phase 6) lists the person's external links (`linked_by = user`) in that lab, so someone else can re-link them under their own account.

### Endpoints (next phase)
`L = /api/labs/<lab_id>`, `P = L/projects/<project_id>`. Rows go into the permission matrix by hand (D32). Responses use the serializers in `integrations/serializers.py` (explicit field lists, no token fields).

| Method | Path | Perm |
|---|---|---|
| GET | `L/integrations/providers/` (registry: name, label, auth_type, icon, scopes, configured, plus my account's status) | view_lab |
| GET | `L/integrations/accounts/` (own rows; all members' with manage_lab_integrations) | manage_integrations |
| POST | `L/integrations/<provider>/connect/` (body `{scopes?}`, returns `{authorization_url}`) | manage_integrations |
| GET | `/api/integrations/oauth/callback/?state&code\|error` redirects to `FRONTEND_URL/labs/<lab_id>/settings/integrations?connected=<provider>` or `?error=<OAuthError.code>` (`/integrations/error?code=` when the state, and so the lab, is unknown) | AUTHENTICATED (state check inside) |
| DELETE | `L/integrations/accounts/<connectedaccount_id>/` (own: disconnect; another member's: revoke; invisible: 404) | manage_integrations / manage_lab_integrations |
| GET | `L/integrations/google/picker-token/` (D70) | manage_integrations, own active account only |
| GET / POST | `P/external-links/` (POST validates via the provider, records the baseline, audits `external_link.created`) | view_project / edit_content |
| GET / DELETE | `L/external-links/<externallink_id>/` (DELETE audits `external_link.removed`) | view_project / edit_content |
| POST | `L/external-links/<externallink_id>/check/` (freshness check now, with the linker's account) | view_project |
| POST | `L/external-links/<externallink_id>/accept-change/` (copy `remote_*` to `linked_*`) | edit_content |

When a service accepts `connected_account` for a link, it must be the requester's own **active** account in this lab. `external_link.*` audit metadata holds `provider` and `external_id`, never a URL query string.

### Google Drive specifics
- Scope **`https://www.googleapis.com/auth/drive.file` only** (D64): per-file access to files the user picks in the Google Picker. Identity comes from `GET drive/v3/about?fields=user(permissionId,emailAddress)`, which works with `drive.file`, so no `openid`/`email` scope is requested. External account id = `permissionId`.
- **Picker:** the SPA loads the Google Picker with the integration client's API key and the access token from `picker-token`. Picked file ids come back to `P/external-links/`. The server then reads metadata with the linker's token: `files.get?fields=id,name,mimeType,modifiedTime,version,md5Checksum,webViewLink,trashed`.
- **Metadata only:** never download, export or cache file contents (`alt=media` and `files.export` are never called). Store `version` and `md5Checksum` (as `md5:<hex>`) when given.
- **Freshness:** a daily Celery job loops over labs and checks each link with its linker's active account, at a bounded rate. 404, or `trashed=true`, sets `unavailable_since`; a later success clears it. A changed `version` or `modifiedTime` shows "changed since linked". Links whose account isn't active are skipped, and the UI says "can't check: the linker's connection is inactive".
- **Incremental authorization:** a later feature needing another Drive scope adds it to `GOOGLE.scopes` (with a DECISIONS entry) and calls `start_connect(..., scopes=[new])`. `include_granted_scopes=true` merges it into the existing grant.

### Token-leak test (`integrations/tests/test_token_leaks.py`)
It seeds canary tokens, the client secret, the auth code and the PKCE verifiers. They go through connect, refresh with rotation, a refused refresh that echoes the token, a network error carrying the token, a token-endpoint error code equal to the token, reconnect, and a disconnect whose revoke response echoes the token. Each `@surface` function returns text that must contain no canary: model reprs and `__dict__`, admin changelist and change pages, captured logs, audit events, notifications, raised exceptions (with their chains), serializer output and `dumpdata`. **Each new endpoint adds a surface** that returns its response body (`w.client(user).get(...)`).
