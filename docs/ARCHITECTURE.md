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

### documents
| Model | Fields | Constraints / indexes |
|---|---|---|
| `Document` | `project` FK CASCADE, `title` char(300), `content` JSON (BlockNote blocks, max 2 MB), `version` int default 1 (D11), `created_by` FK User PROTECT (the owner), `updated_by` FK User PROTECT, `retain_until` date null, `retention_note` text, `deleted_at` null | `lab_parents=("project",)`; index `(project, deleted_at)`, `(lab, retain_until)` |
| `DocumentRevision` | `document` FK CASCADE, `version` int, `title`, `content` JSON, `created_by` FK User PROTECT, `restored_from` FK self SET_NULL null | `lab_parents=("document",)`, `project_path="document__project"`; unique `(document, version)` |
| `Attachment` | `project` FK CASCADE **null** (null means the file belongs to an ethics approval), `storage_key` char(512) unique, `original_filename` char(255), `content_type` char(100), `size_bytes` bigint, `sha256` char(64), `uploaded_by` FK User PROTECT, `notice_acknowledged_at` datetime (non-null) | `lab_parents=("project",)`; index `(project)`; max size 50 MB |

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
- Upgrade path, deferred: composite FKs `(lab_id, project_id) → project(lab_id, id)` via `RunSQL`.

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
    CREATE_PROJECT, VIEW_ETHICS, EDIT_ETHICS, VIEW_RETENTION
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

- **Resolving the target:** a `Lab` is checked against lab perms. A `Project` is checked against project perms. A `LabScopedModel` with a `project_path` resolves to its project. One without a `project_path` is checked at lab level, with `EDIT_CONTENT`/`VIEW_PROJECT` mapped to `EDIT_ETHICS`/`VIEW_ETHICS`. An `Attachment` with `project IS NULL` uses the ethics perms. Any target whose lab the user isn't in returns `False`.
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
- `core/auth.py` holds the `AccountAdapter` and `HeadlessAdapter`, the audit signal receivers, the `SessionAuthentication` subclass that returns 401, and `login_methods_for_email(email)`. That last function returns `["password"]` for now and is the hook for SSO routing. **No other module imports allauth.** App code only reads `request.user`.
- **SSO and SAML later:** add `allauth.socialaccount` with the SAML provider (python3-saml and xmlsec are MIT; check the licenses when adding them). Add `Institution.sso_config` (JSON) and `Institution.email_domains`, and have `login_methods_for_email` route institutional domains to the IdP. Nothing outside `core/auth.py` and the settings needs to change.
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
