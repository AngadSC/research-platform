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
| `Lab` (not LabScoped: it is the tenant) | `id`, `institution` FK PROTECT, `name` char(200), `department`, `description`, `address`, `contact_email`, `website` (blank allowed, D146), `created_by` FK User PROTECT, `created_at`, `updated_at` | index `(institution)` |
| `LabMembership` | `user` FK User PROTECT, `role` choice `pi\|lab_admin\|member\|viewer`, `invited_by` FK User PROTECT null | unique `(lab, user)`; index `(user)` |
| `Invite` | `email` (stored lower-cased), `role` lab-role choice, `token_hash` char(64) unique (sha256 hex), `invited_by` FK User PROTECT, `expires_at` (`created_at + 7 days`), `accepted_at` null, `accepted_by` FK User PROTECT null, `revoked_at` null | partial unique `(lab, email)` where `accepted_at IS NULL AND revoked_at IS NULL`; index `(expires_at)` |

Admin area (Run 4, D146-D151), all lab-level (`permission_domain = "lab"`):

| Model | Fields | Constraints / indexes |
|---|---|---|
| `InventoryItem` | `name`, `category` choice `equipment`, `reagent`, `consumable`, `software_licence`, `other`; `location`, `quantity` decimal >= 0, `unit`, `owner` FK User PROTECT null (a lab member, checked in the service), `serial_number`, `purchase_date` null, `due_date` null (calibration or maintenance), `status` choice `active`, `in_repair`, `retired`, `lost`; `notes` | index `(lab, category)`; check `quantity >= 0` |
| `OnboardingItem` | `kind` choice `new_member`, `departing`; `title`, `description`, `url` (https), `required` bool, `order` | index `(lab, kind, order)` |
| `OnboardingCompletion` | `item` FK CASCADE, `user` FK User PROTECT, `completed_by` FK User PROTECT | `lab_parents=("item",)`; composite lab FK via `LabForeignKey`; unique `(item, user)` |
| `InstitutionResource` | `category` choice `ethics`, `funding`, `data_management`, `other`; `title`, `url` (https only, no credentials), `description`, `order` | unique `(lab, url)`; index `(lab, category, order)` |

The invite token is `secrets.token_urlsafe(32)` and appears only in the emailed link. The database stores only `sha256(token)`, and lookups hash the token they receive. An invite is usable only if it is not expired, not accepted and not revoked. Accepting it requires a logged-in user whose verified email matches `Invite.email` (D25). Accepting creates the `LabMembership` and sets `accepted_*` in one transaction. Only a PI can invite someone with the role `pi`.

### projects
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Project` | `name` char(200), `description` text, `status` choice `planning\|active\|paused\|completed\|archived`, `start_date` null, `created_by` FK User PROTECT, `retain_until` date null, `retention_note` text, `deleted_at` null | `project_path = ""` (itself); index `(lab, deleted_at)`, `(lab, retain_until)` |
| `ProjectMembership` | `project` FK CASCADE, `user` FK User PROTECT, `role` choice `lead\|contributor\|viewer` | `lab_parents=("project",)`; unique `(project, user)`; index `(lab, user)`. The service requires a `LabMembership` in the same lab. |
| `ProjectDeadline` | `project` FK CASCADE, `title` char(200), `due_date` date, `done` bool | `lab_parents=("project",)`; index `(project, due_date)` |
| `Task` | `project` FK CASCADE, `title` char(300), `description` text, `assignee` FK User PROTECT null, `due_date` null, `status` choice `todo\|in_progress\|done`, `position` int (board order), `created_by` FK User PROTECT, `documents` M2M Document, `attachments` M2M Attachment (same project, D141) | `lab_parents=("project",)`; index `(project, status, position)`, `(lab, assignee)` |
| `TaskPost` (D142) | `task` FK CASCADE, `author` FK User PROTECT, `body` text (max 5,000 in the API), `edited_at` null | `lab_parents=("task",)`, `project_path="task__project"`; composite `(task_id, lab_id)` FK; index `(task, created_at)` |

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

### training (Run 5, D175-D179; lab-level)
| Model | Fields | Constraints / indexes |
|---|---|---|
| `TrainingRequirement` | `name`, `category` choice `ethics\|safety\|biosafety\|chemical\|data_privacy\|equipment\|other`, `validity_months` null (never expires), `applies_to` choice `all\|roles\|projects`, `roles` JSON list, `projects` M2M Project, `url` (https), `notes` | unique `(lab, name)`; M2M trigger via `LabM2MTrigger` |
| `TrainingRecord` | `requirement` FK PROTECT, `user` FK User PROTECT, `completed_on`, `expires_on` null, `notes`, `verified_by` FK User PROTECT null, `verified_at` null, `deleted_at` null | `lab_parents=("requirement",)`; composite lab FK; check `expires_on >= completed_on`; index `(lab, user)`, `(lab, expires_on)`; readable by its owner and `manage_training` only |

A certificate is an `Attachment` whose owner is `training_record` (the D38 check is now exactly one of project, ethics approval, training record).

### notifications (in the `core` app)
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Notification` | `recipient` FK User PROTECT, `kind` choice `ethics_expiry\|retention_due\|invite_accepted\|task_assigned\|task_post\|training_expiry\|training_digest`, `title`, `body`, `target_type` char(64), `target_id` UUID null, `dedupe_key` char(200), `read_at` null | unique `(recipient, dedupe_key)`; index `(lab, recipient, read_at, created_at)` |

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
    MANAGE_INTEGRATIONS, MANAGE_LAB_INTEGRATIONS,         # section 9
    MANAGE_INVENTORY,                                     # Run 4, D147
    MANAGE_TRAINING                                       # Run 5, D176
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
| manage_inventory (add, edit, delete inventory items; every member reads them, D147) | Y | Y | Y | - |
| manage_training (requirements, verify, see everyone's records; members see only their own, D176) | Y | Y | - | - |

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
| `integration.connected` (OAuth or API key), `integration.disconnected` (own account), `integration.revoked` (someone else's, or lifecycle with actor null), `integration.refresh_failed` (actor null, `actor_label="integrations:refresh"`; also an API key answered with 401) | `integrations.services` (section 9) |
| `external_link.created`, `external_link.removed`, `external_link.change_accepted` | the external-link services (section 9) |
| `integration.picker_token_issued`, `integration.searched` (provider, target, result count; never the query) | the picker-token view; `integrations.services.search_items` (section 9) |
| `task_post.deleted` | `projects.services.delete_post` |
| `handover.generated` | handover views |
| `inventory_item.created`, `.updated`, `.deleted`, `inventory.exported` | `labs.admin_services`, inventory export view (D147) |
| `onboarding_item.created`, `.updated`, `.deleted`, `onboarding.completion_changed` | `labs.admin_services` (D148) |
| `institution_resource.created`, `.updated`, `.deleted` | `labs.admin_services`; starter loads use `actor_label job:institution_resources` (D149) |

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
| 4 | GET / POST | `L/tasks/<task_id>/posts/` (the task's update thread, D142) | view_project / edit_content |
| 4 | PATCH, DELETE | `L/task-posts/<taskpost_id>/` (PATCH: author only; DELETE: author or edit_project; deletion is audited) | edit_content |
| 4 | POST | `L/tasks/<task_id>/documents/`, `L/tasks/<task_id>/attachments/` (body `{id}`, same project, idempotent, D141) | edit_content |
| 4 | DELETE | `L/tasks/<task_id>/documents/<document_id>/`, `L/tasks/<task_id>/attachments/<attachment_id>/` | edit_content |
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
| R4 | PATCH | `L/` also takes `department`, `description`, `address`, `contact_email`, `website`, `institution_name` (D146) | manage_lab |
| R4 | GET / POST | `L/institution-resources/?category=` | view_lab / manage_lab |
| R4 | PATCH, DELETE | `L/institution-resources/<institutionresource_id>/` | manage_lab |
| R4 | GET / POST | `L/onboarding-items/` | manage_lab |
| R4 | PATCH, DELETE | `L/onboarding-items/<onboardingitem_id>/` | manage_lab |
| R4 | POST | `L/onboarding-items/<onboardingitem_id>/completions/` (`{user, done}`) | manage_lab |
| R4 | GET / POST | `L/inventory/?q=&category=&ordering=` | view_lab / manage_inventory |
| R4 | GET | `L/inventory/export/` (CSV) | view_lab |
| R4 | GET / PATCH, DELETE | `L/inventory/<inventoryitem_id>/` | view_lab / manage_inventory |
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
- **Institutional SSO (SAML 2.0, D152 to D159):** allauth's SAML provider. Each enabled `core.InstitutionSSO` row (superuser-only: dev admin or `manage.py configure_sso`) becomes an in-memory allauth app in `SocialAccountAdapter.list_apps`, provider id `saml:<slug>`, URLs `/accounts/saml/<slug>/{metadata,acs,sls}/`, SP entity ID `{FRONTEND_URL}/accounts/saml/<slug>/metadata/`. `login_methods_for_email` routes the configured domains (exact match), served to the SPA's email-first login by `POST /api/auth/login-methods/`. Signed assertions, audience, destination, time window and one-use `InResponseTo` are enforced; IdP-initiated logins are refused. An SSO login must assert an email in the institution's domains, arrives verified, and links only to a verified matching address (D154). `require_sso` refuses password sign-in and signup for those domains. IdP metadata URLs are fetched only on save, through `integrations.http`.
- **Review fixes (D194, D195, D201, D202):** `core.auth.recent_auth_required(request)` returns allauth's 401-with-flows body unless the session signed in or re-checked its password in the last 5 minutes (used for AI consent and token creation). A password change or reset, TOTP removal and deactivation revoke every AI grant (`assistant.services.revoke_all`). `AccountAdapter.authenticate` and `pre_login` refuse any login (password, Google, another institution's SSO) for a person with a verified address at a require-SSO institution unless it is through that institution's SSO. SAML single logout (`/accounts/saml/<slug>/sls/`) is a 404.
- **MFA:** `allauth.mfa` with `MFA_SUPPORTED_TYPES=["totp","recovery_codes"]`. It is optional per user. A later per-lab "require MFA" setting would be a `Lab` field that `get_lab_or_404` checks.
- **Cookies:** session and CSRF cookies are `Secure` in production and `SameSite=Lax`. The session cookie is HttpOnly. The CSRF cookie is readable by the SPA. `SESSION_COOKIE_AGE` is 7 days.

## 8. File storage

- `STORAGES["lab_files"]`: `FileSystemStorage(location=/data/lab_files)` in dev and `S3Storage(default_acl="private", querystring_auth=False, bucket=env)` in production. It is a separate alias from static files and is never routed under `MEDIA_URL` or `static()`.
- **Key layout:** `labs/<lab_id>/attachments/<attachment_id>`. The original filename lives only in the database, so keys need no sanitizing. `storage_key` is set by `upload_attachment` and is never accepted from the client.
- **Download** goes only through `L/attachments/<attachment_id>/download/`: scoped `get_object()`, then `require(VIEW_*)`, then `audit.record("attachment.downloaded")`, then, on filesystem storage, `FileResponse(storage.open(key))` (D26). With `LAB_FILES_BUCKET` set, forced downloads answer a 302 to a presigned URL instead and PDFs still stream (D90, D123, below). Streamed response headers:
  - `Content-Disposition: attachment`, except PDFs, which are `inline` for PDF.js (and so always stream, D123).
  - `X-Content-Type-Options: nosniff`
  - `Content-Security-Policy: sandbox`
  - `Cache-Control: private, no-store`

  No public URL is ever issued.
- **S3 mode (D90, D123):** after the same scoped lookup, permission check (ethics files keep their own rule) and `attachment.downloaded` audit event, the view splits by how the file is shown:
  - **Shown inline (PDFs) stream through Django**, exactly as above (`nosniff`, `CSP: sandbox`, `no-store`). A presigned response carries none of those headers, and a PDF served from the bucket origin would render there, so nothing inline is ever presigned.
  - **Everything else** answers `302` to a presigned GET that lives 60 seconds at most (`LAB_FILES_PRESIGN_SECONDS`, capped at 60 in the view), always `ResponseContentDisposition: attachment` (filename encoded by Django's RFC 6266/5987 helper), `ResponseContentType` (the stored type) and `ResponseCacheControl` (`private, no-store`). The redirect itself carries `Cache-Control: no-store` and `Referrer-Policy: no-referrer`.
  - **Object metadata:** `documents.storage.LabFilesS3Storage` writes every object with `ContentType: application/octet-stream`, `ContentDisposition: attachment` and `CacheControl: private, no-store` (never the client's declared type), so a provider that ignores the `response-*` overrides still forces a download. Objects written before D123 get the metadata from a one-off copy (docs/DEPLOY.md).
  - A denied request never reaches the signing call. `LAB_FILES_STREAM_DOWNLOADS=True` streams everything, for providers that ignore response overrides.
- **PDF viewer (D91, D123):** `PdfViewerPage` calls `fetch(url, { credentials: "same-origin" })` and now gets the bytes from the app origin, so the bucket needs no CORS rule and the app CSP needs no bucket in `connect-src`.
- **Upload:** the server enforces the 50 MB limit, computes `sha256`, and stores the content type the client declared. The file is never executed or rendered on the server.

## 9. Integrations (`backend/integrations/`)

The framework for outside services. Google Drive is the first provider; Run 3 adds the D79 list, each as one backend module, with a generic UI driven by registry metadata (D80). Every provider reads metadata only (D64, D84).

### Providers and the registry (`integrations/providers/`, `integrations/registry.py`, D80)
Providers are code, not a database table. Each is one module `integrations/providers/<name>.py` exporting `PROVIDER`, a frozen `Provider` dataclass (defined in `providers/__init__.py`). `registry.ENABLED` is the one explicit list of modules; `registry.PROVIDERS` maps `name` (the key stored on rows, equal to the module name) to the provider. Adding a provider is a module plus one line; `providers/README.md` has the steps and the security checklist.

`Provider` fields, by purpose:
- **Identity and UI:** `name`, `label`, `auth_type` (`oauth2 | api_key | link_only | public`), `category` (`storage | code | writing | data_capture | protocols | references | repository`), `icon` (a key), `metadata_only` (must be `True`), `link_targets` (subset of `project, document, dataset, analysis, result, manuscript, decision`; `project` is the Files tab), `link_methods` (subset of `picker, search, paste_url`).
- **oauth2:** `scopes` (the **only** scopes that can ever be requested), `authorize_url`, `token_url`, `revoke_url`, `identity_url` + `parse_identity(json) -> (external_id, email)`, `authorize_params`. Client credentials come from `settings.INTEGRATION_CLIENTS[name]` (Drive: `GOOGLE_DRIVE_*`; any other: `INTEGRATION_<NAME>_CLIENT_ID/_SECRET`, D87). Without them the provider is "not configured".
- **api_key (D81):** `connect_fields` (`api_key`, optional `secret`, `instance_url` iff `needs_instance_url`; label, help text, required), `needs_instance_url`, `instance_host_pattern`, `identify(account)` (default: GET `identity_url`, a path joined to the instance URL, then `parse_identity`), `sign(kwargs, key, secret)` (how credentials go on a request; default a bearer header, also used for oauth2).
- **Hosts:** `api_hosts` (where credentials may be sent), `link_hosts` (where an item's web link may point; self-hosted providers are pinned to the account's instance host instead).
- **Items:** `fetch_item(account | None, external_id) -> dict | None` (title, url, mime_type, modified_at, version, checksum; None = gone), `search_items(account | None, query, target_kind) -> [dict]` (id, title, subtitle, modified, url), `external_id_pattern` (D75), `url_pattern` (a regex with an `id` group: a pasted address to an id, D83), `apply_to_target(kind, meta) -> {field: value}` (D86).

`GET L/integrations/providers/` returns all of that except the hooks and secrets, plus `configured`, `public_config` (D77), `can_check` (has `fetch_item`) and the requester's own account (`id`, `status`, `external_email`, `instance_url`). Tests register the fakes in `integrations/tests/fake.py` (`FAKE` oauth2, `FAKE_KEY` api_key self-hosted, `FAKE_LINK` link_only, `FAKE_PUBLIC` public) with `monkeypatch.setitem(PROVIDERS, ...)` and swap `integrations.http._session` for `FakeTransport` and `http._resolve` for a stub.

### Models
| Model | Fields | Constraints / notes |
|---|---|---|
| `ConnectedAccount` | `user` FK User PROTECT, `provider` char(40), `external_account_id` (self-hosted: `<host>:<id>`), `external_email` (email or user name), `granted_scopes` JSON list, `status` `active\|expired\|revoked\|error`, `access_token_ct`, `refresh_token_ct` (Fernet ciphertext, `editable=False`; for API keys the key and the optional secret), `token_expires_at`, `instance_url` (self-hosted base URL, D82), `connected_at`, `last_used_at` (last successful provider call) | `permission_domain="lab"`. Unique `(lab, user, provider, external_account_id)`; partial unique `(lab, user, provider)` where active (D69). `visible_rows`: own rows, or all with `manage_lab_integrations` (D54 pattern). Never deleted: a revoked row keeps its links' history, credentials wiped. |
| `ExternalLink` | `project` FK CASCADE; at most one of `document`, `dataset`, `analysis`, `result`, `manuscript`, `decision` (FKs SET_NULL, DB check `externallink_at_most_one_target`); `provider`, `connected_account` FK PROTECT null (the linker's account, used for freshness; null for link_only and public), `external_id`, `url` (http/https only), `title`, `mime_type`, `linked_by` FK User PROTECT, `linked_modified_at`/`linked_version`/`linked_checksum` (baseline at link time), `remote_modified_at`/`remote_version`/`remote_checksum` (last seen), `last_checked_at`, `unavailable_since` | `permission_domain="project"`, `project_path="project"`, `lab_parents` = project, the six targets, `connected_account`, so the target is in the same project and the account in the same lab (D31). Composite `(fk, lab_id)` FKs via `core.lab_db.LabForeignKey` in `integrations/0001` and `0003`. `changed_since_linked`: checksums or versions differ, or (none) remote modified time is later than the baseline. "No longer available" = `unavailable_since` set. |

Statuses: `expired` means the provider refused a refresh (`invalid_grant`, or no refresh token) or answered 401 to an API key: the user must reconnect. `revoked` means we wiped the credentials (disconnect, admin revoke, lifecycle). `error` means our side is wrong (client rejected, provider not configured, an unexpected scope). Only `active` accounts are ever used.

### Token storage and rotation (D63)
- Tokens and API keys are encrypted with `MultiFernet` over `INTEGRATION_ENCRYPTION_KEYS` (comma-separated, newest first). New ciphertext uses the first key; any listed key decrypts.
- Outside DEBUG a missing value refuses startup. In DEBUG a random dev key comes from the git-ignored `backend/.dev_integration_key` (the D49 pattern). `IntegrationsConfig.ready()` builds the MultiFernet, so a malformed key fails at startup, and the error never echoes key material.
- Rotation: put the new key first, deploy, run `manage.py rotate_integration_keys` (re-encrypts every credential under the first key), then drop the old key.
- Plaintext exists only in the return value of `account.access_token()` / `refresh_token()`. Ciphertext lives in `editable=False` fields, so ModelForms, the admin and generic serializers never get even the ciphertext. `__str__` is `provider: email`.
- Credentials never appear in API responses, logs, audit metadata, notification text, exception messages, reprs, the admin or the DEBUG 500 page. Functions that hold them use `@sensitive_variables`; the connect view also uses `sensitive_post_parameters("api_key", "secret")`. `integrations/tests/test_token_leaks.py` enforces this (below). The one exception is the Picker token (D70).

### HTTP client (`integrations/http.py`, D67, D82)
`send(method, url, *, provider, account=None, **requests_kwargs) -> Response` is the only way out:
- HTTPS only, port 443, no userinfo, and only to a host in `provider.api_hosts` or the account's own instance host (still inside `INTEGRATION_ALLOWED_INSTANCE_HOSTS`); anything else raises before a socket opens. Redirects are never followed automatically: a redirect to another scheme, host or port raises, and same-origin redirects are followed (max 3) for GET and HEAD only.
- **SSRF and DNS pinning (D82):** the session mounts `PinnedAdapter`, which on every request resolves the host, refuses unless every address is globally routable unicast (`is_public_ip`: private, loopback, link-local, multicast, reserved, unspecified, CGNAT, site-local and cloud-metadata addresses are refused, IPv4 and IPv6, and so is every IPv6 form that embeds an IPv4 address: mapped, 6to4, Teredo, NAT64), and connects to the address it checked, with SNI, certificate verification and the `Host` header on the hostname. A name that resolves to a public address at check time and a private one a moment later can't win. The session ignores proxy and `.netrc` settings from the environment (`trust_env=False`). Any unexpected exception from the HTTP stack becomes a plain `IntegrationError`.
- **Time and size (D120):** a per-socket timeout `(5, 20)` is not a limit (a server can send one byte every 19 s forever), so every request is streamed under a total wall-clock deadline and a body cap, and the connection is always closed.
  - `INTEGRATION_HTTP_DEADLINE` (15 s) covers one request, connect to last byte, all attempts and backoff included. A watchdog timer shuts the socket at the deadline, so a body dripped in single bytes or a server that stalls is cut on time. A retry is skipped if its backoff would pass the deadline (the last answer is returned instead).
  - `INTEGRATION_HTTP_MAX_BYTES` (2 MB): `Content-Length` is checked first, then the bytes actually received (decoded, so a compression bomb counts); past the cap the read is aborted. Both raise `IntegrationError` ("too large" / "did not respond in time"); a timeout or an oversize body is never retried.
  - `http.budget(seconds, per_request=None)` is a context manager bounding everything sent inside it, and nested budgets can only tighten. `http.interactive` gives a service function the endpoint budget `INTEGRATION_ENDPOINT_BUDGET` (25 s): `complete_connect`, `connect_with_key`, `create_link`, `search_items`, the provider revoke call; the freshness-check view uses `budget` directly. The daily job gives each link `INTEGRATION_JOB_LINK_BUDGET` (60 s) with a per-request deadline of `INTEGRATION_JOB_HTTP_DEADLINE` (30 s).
  - GET, HEAD, OPTIONS, PUT and DELETE retry up to 3 attempts on network errors and 429/500/502/503/504, backing off 0.5 s doubling, honouring `Retry-After`, capped at 8 s. POST is never retried. Each attempt resolves again.
- Without `account` nothing secret is attached (public providers, the OAuth token exchange).
- With `account`: it must be `active` (else `AccountUnavailable`), and `provider.sign` attaches the credentials. OAuth: a token expiring within 60 s is refreshed first; a 401 triggers one refresh and one retry. Refresh runs under `select_for_update`, so concurrent callers refresh once. API key: a 401 means the key was revoked at the provider (`services.key_rejected`: `expired`, wiped, audited, notified; skipped for a key still being validated on connect), and `AccountUnavailable` is raised. Successful calls update `last_used_at`.
- Refresh outcomes: success stores the new access token (and a rotated refresh token if the provider sends one). `invalid_grant` or no refresh token: `expired`. Other 4xx: `error`. Either way the tokens are wiped, `integration.refresh_failed` is audited (metadata `provider`, `reason`, `status`) and the owner gets an `integration_issue` notification (deduped per connection). Network errors, 429 and 5xx are transient: nothing changes and `IntegrationError` is raised.
- Logs carry method, host, path and status. Never headers, bodies or query strings. Exceptions carry a fixed message; provider error codes are passed on only if they match `^[a-z_]{1,40}$`, and requests' exceptions (which hold the prepared request) are dropped with `from None`.
- Callers get the response for any status and decide what it means (for Drive, 404 means "no longer available").

### Instance URLs (self-hosted providers, D82)
`http.validate_instance_url(url, provider)` runs when an API-key account is connected: https, port 443, no userinfo, query or fragment, a plain path, a DNS name (`dns_name_ok`: two or more labels, the last starting with a letter, so no IP literal in any spelling), allowed by `INTEGRATION_ALLOWED_INSTANCE_HOSTS` (comma-separated exact hosts or `*.domain`; empty = any public host) and the provider's `instance_host_pattern`, and resolving only to public addresses. It returns `https://host/path` without a trailing slash. Failures raise `InstanceURLError` with `instance_not_allowed` (the allowlist) or `invalid_instance_url` (everything else, one code so the API is no DNS oracle). Every later request re-resolves and re-checks (`PinnedAdapter`) and re-checks the allowlist.

### Connecting accounts (`integrations/services.py`)
`POST L/integrations/<provider>/connect/` starts an OAuth flow or connects an API key, by the provider's `auth_type`; link_only and public providers have no account (`unknown_provider`).

**OAuth2 (D65, D66).** Separate from Google sign-in (allauth, `openid email profile` only, section 7). Callback: **`/api/integrations/oauth/callback/`** for every provider, under `/api/` so the Vite proxy covers it. `settings.INTEGRATION_OAUTH_REDIRECT_URI = FRONTEND_URL + that path`, so the local redirect URI to register is **`http://localhost:5173/api/integrations/oauth/callback/`**.
1. `start_connect(request, lab, provider_name, scopes=None) -> authorization_url`: `require(manage_integrations, lab)`; scopes must be a subset of the registry's (default: all of them). Creates a 256-bit `state` and a PKCE verifier and stores `{user, lab, provider, scopes, verifier, at}` under `session["integrations.oauth"][state]` (at most 5 pending, 10 minute lifetime). The URL carries `code_challenge` (S256), the redirect URI, the scopes, the provider's fixed params (Google: `access_type=offline`, `prompt=consent`, `include_granted_scopes=true` for incremental authorization) and `login_hint` = the email of the user's current account, so a scope upgrade lands on the same account.
2. `complete_connect(request, *, state, code, error) -> ConnectedAccount`: pops the state (single use, even on failure). It fails with `invalid_state` unless the state exists in **this session**, is fresh, and belongs to `request.user`. Then it re-runs `get_lab_or_404` and `require(manage_integrations)`, because the role may have changed. It exchanges the code with the verifier and client secret, checks every requested scope was granted (`scope_not_granted`) and nothing more (`unexpected_scope`, D78), and fetches the identity. Then `_store_account` (below).
3. A token from a failed connect is discarded, never stored, and not revoked (D68).

Security properties: state is unguessable, single-use, short-lived and bound to the server-side session, the user, the lab and the provider (login CSRF and code injection fail). PKCE binds the code to the browser that started the flow. The provider (so the token endpoint) comes from the stored state, never from the callback request (no mix-up). The redirect URI is fixed in settings. Scopes come only from the registry. The SPA never sees a code or a token.

**API key (D81).** `connect_with_key(request, lab, provider_name, *, api_key, secret, instance_url)`: `require(manage_integrations, lab)`, required form fields present, the instance URL validated (above), then one cheap provider call with an unsaved account (`provider.identify_account`): a 401 is `invalid_key`, a network failure `provider_error`, an unreadable answer `identity_failed`. Nothing is stored before that call succeeds. Then `_store_account`. Throttled per user (`integration_connect`, 30 an hour).

**Storing (both).** `_store_account`, under a row lock: if another external account of this provider is active for the user in this lab, it refuses (`other_account_connected`: disconnect first). The same external account reuses its row (credentials, scopes, instance URL, status active); otherwise a new row is created. Audits `integration.connected` with metadata `provider`, `scopes` and, for self-hosted, `instance_host`.

`OAuthError.code` (safe to return and to put in a redirect query string) is one of `invalid_state`, `access_denied`, `provider_error`, `invalid_request`, `invalid_scope`, `unknown_provider`, `provider_not_configured`, `scope_not_granted`, `unexpected_scope`, `identity_failed`, `other_account_connected`, `invalid_key`, `invalid_instance_url`, `instance_not_allowed`.

### Disconnect and revoke
`disconnect(account, *, actor, request=None)`: the owner needs `manage_integrations` (audit `integration.disconnected`); anyone else needs `manage_lab_integrations` (audit `integration.revoked`). Under a row lock it marks the row `revoked`, wipes the credentials and, for OAuth only, calls the provider's revoke URL with the refresh token (or the access token), best effort; it audits with metadata `provider_revoked: bool`. The provider call is skipped when the same external account is active for anyone in any lab, because Google revokes the whole grant (D68). API keys are never sent to a revoke endpoint: the person deletes the key at the provider. It is idempotent.

### Lifecycle
- **Member removed from a lab, or user deactivated:** `integrations.services.revoke_member_accounts(lab, user, reason="member_removed" | "user_deactivated")` runs inside the membership transaction (local revoke, actor null, label `lifecycle:<reason>`), with the provider calls after commit. The daily `revoke_orphans` job (01:30) catches any missed hook. Their `ExternalLink`s stay; freshness checks for them stop, because the linker's account is revoked. API-key accounts follow the same path.
- **Handover** (section 5, phase 6) lists the person's external links (`linked_by = user`) in that lab, so someone else can re-link them under their own account.

### Links, search and freshness
- **Create** (`create_link`, D83, D85): the item is named by `external_id` (picker or search result) or by a pasted `url`, which the provider parses (`url_pattern` fullmatched on a pinned host: `link_hosts`, or the account's instance host). The target kind must be in `link_targets`. oauth2 and api_key read the item with the requester's own **active** account in this lab; public providers read it with no credentials; in both cases the metadata comes only from the provider, never from the client. link_only stores the pasted URL, the parsed id and the person's own title. The stored `url` must pass the provider's host rules and `validate_web_url`. `external_link.*` audit metadata holds `provider` and `external_id` (and `version_copy`), never a URL query string.
- **Apply to target** (D76, D86): `apply_to_target(kind, meta)` proposes values for a linked dataset, analysis, result, manuscript or decision. Each is written only into an empty field whose validators accept it, audited `<kind>.updated` (`source: external_link`); the response's `version_note` is `copied`, `kept`, `same` or `none`. Fields that only make sense together (`services.PAIRED_FIELDS`: an analysis' `code_repo_url` and `code_commit`) are written in one step and only while both are empty, and the repository address must pass `link_url_ok` for the provider's hosts or the account's instance host (D121). List fields a provider appends to (`APPEND_FIELDS`, Zotero) are locked with `select_for_update` and re-read first, so a concurrent edit is not lost (D122). A later change to the item updates only the link.
- **Search** (`search_items`, D85): `GET P/integrations/<provider>/search/?q=&target=` asks the provider (own account, or none for public) for at most 20 candidates (`id`, `title`, `subtitle`, `modified`, `url`), each checked (valid id, link only on the provider's hosts). Nothing is stored or cached; the response is `Cache-Control: no-store`. Audited `integration.searched` (provider, target, result count; never the query). Throttled (`integration_search`, 30 a minute).
- **Freshness:** `check_link` reads the item with the linker's account (none for public and link_only providers that offer `fetch_item`). It is skipped when `check_blocked` gives a reason (`linker_inactive`, `linker_access_lost`, D78). A miss sets `unavailable_since`; a later success clears it; link_only titles are never overwritten. The daily entry point (`jobs.check_links_by_lab`, 02:00, D120) queues one Celery task per lab (`check_lab_links_task`, soft limit 20 min, hard 21 min); each checks every link with an account plus every account-less link whose provider offers `fetch_item`, pausing between calls, each link under its own time budget, stopping at `INTEGRATION_JOB_LAB_BUDGET` (15 min; the rest wait for tomorrow). A slow link costs that link and a slow lab costs that lab. `jobs.check_links` (all labs in turn, with its own limits) remains for manual runs. `POST check` is limited to once a minute per link plus a per-user throttle.
- The lineage response adds `meta.external_links` (id, provider, title, url, status, last_checked_at) to dataset, analysis, result, manuscript and decision nodes.

### Endpoints
`L = /api/labs/<lab_id>`, `P = L/projects/<project_id>`. Rows go into the permission matrix by hand (D32). Responses use the serializers in `integrations/serializers.py` (explicit field lists, no credential fields).

| Method | Path | Perm |
|---|---|---|
| GET | `L/integrations/providers/` (registry metadata for the generic UI, D80, plus my account) | view_lab |
| GET | `L/integrations/accounts/` (own rows; `?all=true` adds all members' with manage_lab_integrations) | manage_integrations |
| POST | `L/integrations/<provider>/connect/` (oauth2: body `{scopes?}`; api_key: `{api_key, secret?, instance_url?}`, validated with the provider first; returns `{authorization_url, account}`; throttled `integration_connect`; audits `integration.connected` for api_key) | manage_integrations |
| GET | `/api/integrations/oauth/callback/?state&code\|error` redirects to `FRONTEND_URL/labs/<lab_id>/settings/integrations?connected=<provider>` or `?error=<OAuthError.code>` (`/integrations/error?code=` when the state, and so the lab, is unknown) | AUTHENTICATED (state check inside) |
| DELETE | `L/integrations/accounts/<connectedaccount_id>/` (own: disconnect; another member's: revoke; invisible: 404) | manage_integrations / manage_lab_integrations |
| GET | `L/integrations/google/picker-token/` (D70; audits `integration.picker_token_issued`) | manage_integrations, own active account only |
| GET | `P/integrations/<provider>/search/?q=&target=` (D85; own account only; throttled; `no-store`; audits `integration.searched`) | edit_content |
| GET / POST | `P/external-links/` (POST: by id or pasted URL, the provider is read server-side, records the baseline, may fill the target (D86), audits `external_link.created`) | view_project / edit_content |
| GET / DELETE | `L/external-links/<externallink_id>/` (DELETE audits `external_link.removed`) | view_project / edit_content |
| POST | `L/external-links/<externallink_id>/check/` (freshness check now, with the linker's account; 502 on a transient provider failure) | view_project |
| POST | `L/external-links/<externallink_id>/accept-change/` (copy `remote_*` to `linked_*`, audits `external_link.change_accepted`) | edit_content |

### Google Drive specifics (`providers/google_drive.py`)
- Scope **`https://www.googleapis.com/auth/drive.file` only** (D64): per-file access to files the user picks in the Google Picker. Identity comes from `GET drive/v3/about?fields=user(permissionId,emailAddress)`, which works with `drive.file`, so no `openid`/`email` scope is requested. External account id = `permissionId`. `link_methods = ("picker",)`: `drive.file` cannot search or open a pasted URL.
- **Picker:** the SPA loads Google's script only on click, then opens the Picker with the public API key and app id (`public_config` on the providers endpoint, D77) and the access token from `picker-token`. Picked file ids come back to `P/external-links/`. The server then reads metadata with the linker's token: `files.get?fields=id,name,mimeType,modifiedTime,version,md5Checksum,webViewLink,trashed`.
- **Metadata only:** never download, export or cache file contents (`alt=media` and `files.export` are never called). Store `version` and `md5Checksum` (as `md5:<hex>`) when given. 404, 403 (access lost) or `trashed=true` is "no longer available"; a 403 rate-limit reason is transient.
- **Dataset records:** `apply_to_target` fills an empty `checksum` with `md5:<hex>`, else `drive-version:<n>` (D76).
- **Incremental authorization:** a later feature needing another Drive scope adds it to the provider's `scopes` (with a DECISIONS entry) and calls `start_connect(..., scopes=[new])`. `include_granted_scopes=true` merges it into the existing grant.

### Tests every provider shares
- **Contract** (`integrations/tests/provider_contract.py`, D88): a `ProviderContract` subclass with the provider, an item id, its pasted URL and title, a target and mocked replies per stage runs connect (and a refused key), search, fetch and link (by id and URL), untrusted client metadata, changed then gone, revoke, a 401 on use and a leak scan, against the real endpoints. `test_fake_contract.py` runs it for all four auth types.
- **Registry** (`test_registry.py`, D84): every enabled provider passes `provider_problems` (metadata, auth-type rules, hosts) and `content_paths` (no content-download path in its code or hosts), and every module in `providers/` is enabled under its own name.
- **SSRF** (`test_ssrf.py`, D82): each defence is isolated by its own test, including DNS rebinding against the real adapter with DNS and sockets stubbed.

### Token-leak test (`integrations/tests/test_token_leaks.py`)
It seeds canary tokens, API keys and secrets, the client secret, the auth code and the PKCE verifiers. They go through OAuth connect, refresh with rotation, a refused refresh that echoes the token, a network error carrying the token, a token-endpoint error code equal to the token, reconnect, and a disconnect whose revoke response echoes the token; and API-key connect, a refused key echoed back, a 401 on use, a network error and an HTTP-stack error carrying the key, reconnect and a member removal. Each `@surface` function returns text that must contain no canary: model reprs and `__dict__`, admin changelist and change pages, captured logs, audit events, notifications, raised exceptions (with their chains), serializer output, `dumpdata`, every integration endpoint's responses (errors included) and the DEBUG 500 page (OAuth callback, link create, and API-key connect posted as JSON and as a form). **Each new endpoint adds a surface** that returns its response body (`w.client(user).get(...)`).

## 10. AI access: tool layer and remote MCP server (`backend/assistant/`, Run 5, D160-D169)

- **Tool layer** (`assistant/tools.py`): `definitions()` and `call(Context, name, args)`, transport-neutral. Every candidate comes from `scope()` and every result passes `can()`; the lab must be named by the grant and still be one of the user's labs on every call. Writes call the existing services inside one transaction and record `ai_tool.write` (`tool`, `via`, `client`, `grant_id`). Details in D160.
- **MCP endpoint** (`assistant/mcp.py`): `POST /mcp`, Streamable HTTP, stateless, JSON responses, dual-era (2026-07-28 per-request `_meta`; 2025-03-26 to 2025-11-25 `initialize`). Bearer token only; `Origin` checked. D161, D166.
- **Authorization server** (`assistant/oauth.py`, `assistant/views.py`): issuer `MCP_BASE_URL`; `/.well-known/oauth-protected-resource[/mcp]` (RFC 9728), `/.well-known/oauth-authorization-server` (RFC 8414), `POST /api/oauth/register/` (RFC 7591), `POST /api/oauth/token/` (code with PKCE S256, rotating refresh), the SPA consent page `/oauth/authorize` backed by `POST /api/oauth/authorize/`. Client ID Metadata Documents from allowed hosts only. D161, D165, D167.
- **Models** (not lab-scoped; a grant belongs to a user and names labs): `OAuthClient` (client_id, kind dcr|cimd, name, redirect_uris), `AIGrant` (user, kind oauth|pat, client, name, labs M2M, access read|write, last_used_at, expires_at, revoked_at/by), `AIToken` (grant, kind code|access|refresh|pat, `token_hash` sha256, expires_at, used_at, data). D162.
- **Endpoints for the SPA** (in the permission matrix): `POST /api/oauth/authorize/` and `GET, POST /api/ai/grants/`, `DELETE /api/ai/grants/<aigrant_id>/` (AUTHENTICATED, own grants only); `GET L/ai-grants/`, `DELETE L/ai-grants/<aigrant_id>/` (manage_lab_integrations). `/mcp`, `/.well-known/`, `/api/oauth/token/` and `/api/oauth/register/` are exempt from the matrix (protocol endpoints for AI clients, covered by `assistant/tests/test_mcp.py` and `test_token_leaks.py`).
- **Review fixes (D193, D195-D200, D203):** redirect URIs are exact (`MCP_ALLOWED_REDIRECT_URIS`, loopback any port); consent and token creation need a recent sign-in; read results wrap record text as `untrusted_content`; consent defaults to one lab and read only; grants ended by a security event keep `revoked_reason` and show in Settings; `assistant.jobs.prune_unused_clients` runs daily; the lab's AI-grant list shows only that lab.
- **Audit actions:** `ai_access.granted`, `ai_access.revoked` (one event per lab named), `ai_tool.write`. `get_document` records `document.viewed` with `via` and `client`.

### In-app assistant (`assistant/ai/`, `assistant/ai_views.py`, D187-D192)

- **Same tool layer, different transport.** `ai/chat.py` runs a provider-neutral loop over `assistant/tools.py` (`via="in_app"`, one lab per context). `ai/claude.py` (Anthropic Messages API, official SDK) and `ai/openai_responses.py` (OpenAI Responses API, official SDK) each build their own requests and keep their own content format; `ai/types.py` is only the shape of a finished turn.
- **Models:** `AIProviderKey` (per user, MultiFernet ciphertext, `last4`, Anthropic `refusal_fallback`), `Conversation` (user, lab, project, provider, model, frozen system prompt), `Message` (append-only, provider-native content, model that answered, usage, `in_context`). Owner-only: every query filters on user and lab.
- **Endpoints:** `GET /api/ai/keys/`, `PUT, PATCH, DELETE /api/ai/keys/<ai_provider>/`; per lab `GET, PATCH ai-policy/`, `GET assistant/config/`, `GET, POST assistant/conversations/`, `GET, DELETE assistant/conversations/<conversation_id>/`, `POST .../messages/` and `POST .../approvals/` (server-sent events). Lab policy `Lab.ai_policy` (off, mcp, full) gates both this and `/mcp`.
- **Write approval:** a write tool call ends the stream with `approval_required`; the call has no result until the person posts a decision. Audit `ai_tool.write` (via `in_app`), `ai_key.saved`, `ai_key.removed`.
- **Stream limits (D196):** cache slots cap streams per conversation (1), person (3) and server (`ASSISTANT_MAX_STREAMS`, default 10 of 24 threads); a stream stops after `ASSISTANT_STREAM_DEADLINE` (300 s) and a 10 s heartbeat refreshes its slots (`ASSISTANT_LOCK_TTL`, 600 s). The approval payload carries resolved `resolved` names and a text `preview` (D198).
- **Streaming deployment:** gunicorn gthread workers with a long timeout and Caddy `flush_interval -1` for the stream routes (see `deploy/`).
