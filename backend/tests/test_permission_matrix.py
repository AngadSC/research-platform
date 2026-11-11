"""Permission matrix (ARCHITECTURE section 6, D32, D36). Gates every phase.

To add an endpoint in a later phase: add its model to `build_world` (for Lab A and Lab B),
its URL kwargs to `build_world().a` / `.b`, a `PAYLOADS` entry for each write method, and one
hand-written `MATRIX` row. The expected codes are never derived from the code or the role tables.
"""

import dataclasses  # integrations (Run 2)
import datetime  # integrations (Run 2)
import uuid  # inventory protocols
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from django.core.files.uploadedfile import SimpleUploadedFile  # documents/attachments (Phase 3)
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APIClient

from assistant.ai import keys as ai_keys  # in-app assistant (Run 5)
from assistant.models import AIGrant, AIProviderKey, Conversation, Message  # AI access (Run 5)
from assistant.services import register_client  # AI access (Run 5)
from assistant.tests.reauth import sign_in  # AI access (Run 5)
from core.models import Institution, Notification, NotificationKind, User
from documents import services as document_services  # documents/attachments (Phase 3)
from ethics.models import EthicsApproval  # ethics (Phase 5)
from integrations import http as integrations_http  # integrations (Run 2)
from integrations import registry, webhooks
from integrations.models import ConnectedAccount, ExternalLink, Webhook  # integrations (Run 2)
from integrations.providers import zotero as zotero_provider  # Zotero import (D242)
from integrations.tests.fake import FAKE  # integrations (Run 2)
from labs.models import (  # admin area (Run 4)
    CalendarFeedToken,
    InstitutionResource,
    InventoryItem,
    InventoryOrder,
    InventoryUsage,
    Invite,
    Lab,
    LabChatMessage,
    LabEvent,
    LabMembership,
    LabRole,
    Meeting,
    OnboardingItem,
    Protocol,
    ProtocolReagent,
)
from papers import services as paper_services  # paper library
from projects.models import (  # projects/tasks (Phase 3)
    ChatMessage,
    Project,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    Task,
    TaskPost,
)
from provenance.models import (  # provenance (Phase 4)
    Analysis,
    DataManagementPlan,
    DatasetRecord,
    Decision,
    ExternalOutput,
    FundingRecord,
    ManuscriptLink,
    RecruitmentEntry,
    Result,
    ReviewItem,
)
from training import services as training_services  # training (Run 5)
from training.models import TrainingRecord, TrainingRequirement  # training (Run 5)

# Fixed order. Lab roles: outsider is the PI of Lab B and not in Lab A; pi, admin (lab_admin),
# lead, contrib, pviewer and nonproj (members); lviewer is a lab viewer. Project roles on P1:
# lead, contrib, pviewer; nonproj has none; lviewer is a contributor, capped to viewer (D19).
PERSONAS = ["anon", "outsider", "pi", "admin", "lead", "contrib", "pviewer", "nonproj", "lviewer"]

# Each exemption needs a reason.
EXEMPT_PREFIXES = [
    "/_allauth/",  # allauth headless: its own views, covered by core/tests/test_auth.py
    "/accounts/",  # allauth provider URLs: Google (test_google_auth.py), SAML (test_saml_auth.py)
    "/admin/",  # Django admin: staff only, not part of the API
    "/healthz",  # load-balancer probe: checks only, no data (core/tests/test_healthz.py)
    # AI access (Run 5, D161): MCP protocol endpoints for AI clients, not the SPA API. Bearer
    # tokens only, covered by assistant/tests/test_mcp.py and test_token_leaks.py.
    "/mcp",
    "/.well-known/",  # public OAuth metadata (RFC 9728, RFC 8414)
    "/api/oauth/token/",
    "/api/oauth/register/",
]

# fmt: off
MATRIX: dict[tuple[str, str], str] = {
    #                                    anon outsider pi admin lead contrib pviewer nonproj lviewer
    ("GET",    "core:health"):           "2   2        2  2     2    2       2       2       2",
    ("GET",    "core:me"):               "401 2        2  2     2    2       2       2       2",
    ("PATCH",  "core:me"):               "401 2        2  2     2    2       2       2       2",
    # D156: SSO routing by email domain, public
    ("POST",   "core:login-methods"):    "2   2        2  2     2    2       2       2       2",
    ("GET",    "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("POST",   "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("GET",    "labs:institution-search"): "401 2      2  2     2    2       2       2       2",
    ("GET",    "labs:lab-detail"):       "401 404      2  2     2    2       2       2       2",
    ("PATCH",  "labs:lab-detail"):       "401 404      2  2     403  403     403     403     403",
    # D170: PI dashboard, pi and lab_admin only
    ("GET",    "labs:dashboard"):        "401 404      2  2     403  403     403     403     403",
    # Contribution graph on the dashboard: same audience
    ("GET",    "labs:contributions"):    "401 404      2  2     403  403     403     403     403",
    ("GET",    "labs:getting-started"):  "401 404      2  2     2    2       2       2       2",
    ("POST",   "labs:getting-started"):  "401 404      2  2     2    2       2       2       2",
    ("GET",    "labs:member-list"):      "401 404      2  2     2    2       2       2       2",
    ("PATCH",  "labs:member-detail"):    "401 404      2  2     403  403     403     403     403",
    ("DELETE", "labs:member-detail"):    "401 404      2  2     403  403     403     403     403",
    ("GET",    "labs:invite-list"):      "401 404      2  2     403  403     403     403     403",
    ("POST",   "labs:invite-list"):      "401 404      2  2     403  403     403     403     403",
    ("DELETE", "labs:invite-detail"):    "401 404      2  2     403  403     403     403     403",
    ("GET",    "audit:audit-event-list"): "401 404      2  2     403  403     403     403     403",
    ("POST",   "labs:invite-preview"):   "2   2        2  2     2    2       2       2       2",
    ("POST",   "labs:invite-accept"):    "401 2        2  2     2    2       2       2       2",
    # --- projects/tasks (Phase 3) ---
    # Reasoned from SPEC and ARCHITECTURE section 3, per persona on P1 (lead, contrib, pviewer
    # are P1's lead/contributor/viewer; nonproj is not on P1 so P1 is invisible: 404; lviewer is
    # capped to viewer, D19; pi and admin are implicit leads). Delete needs delete_project:
    # pi and lab_admin only (D28), so even P1's lead gets 403.
    ("GET", "projects:project-list"): "401 404 2 2 2 2 2 2 2",
    ("POST", "projects:project-list"): "401 404 2 2 2 2 2 2 403",
    ("GET", "projects:project-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH", "projects:project-detail"): "401 404 2 2 2 403 403 404 403",
    ("DELETE", "projects:project-detail"): "401 404 2 2 403 403 403 404 403",
    ("GET", "projects:projectmember-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:projectmember-list"): "401 404 2 2 2 403 403 404 403",
    ("PATCH", "projects:projectmember-detail"): "401 404 2 2 2 403 403 404 403",
    ("DELETE", "projects:projectmember-detail"): "401 404 2 2 2 403 403 404 403",
    ("GET", "projects:deadline-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:deadline-list"): "401 404 2 2 2 403 403 404 403",
    ("PATCH", "projects:deadline-detail"): "401 404 2 2 2 403 403 404 403",
    ("DELETE", "projects:deadline-detail"): "401 404 2 2 2 403 403 404 403",
    # My tasks: your own, filtered to projects you can see, so nonproj gets a 2 with no P1 rows.
    ("GET", "projects:my-tasks"): "401 404 2 2 2 2 2 2 2",
    ("GET", "projects:task-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:task-list"): "401 404 2 2 2 2 403 404 403",
    ("GET", "projects:task-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH", "projects:task-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "projects:task-detail"): "401 404 2 2 2 2 403 404 403",
    # Chat (D206): everyone on P1 reads and posts, viewers too. The message is contrib's, so
    # contrib may delete it as author, and pi, admin and lead as leads. Viewers are not the author.
    ("GET", "projects:chatmessage-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:chatmessage-list"): "401 404 2 2 2 2 2 404 2",
    ("DELETE", "projects:chatmessage-detail"): "401 404 2 2 2 2 403 404 403",
    # Read state (D207) is your own: anyone who can see P1 may mark it read. Unread counts are
    # per lab and filtered to the projects you can see, so nonproj gets a 2 with no P1 rows.
    ("POST", "projects:chatmessage-read"): "401 404 2 2 2 2 2 404 2",
    ("GET", "projects:chat-unread"): "401 404 2 2 2 2 2 2 2",
    # --- task thread and links (Run 4, D141/D142) ---
    # Reading the thread needs view_project; posting and linking need edit_content. The fixture
    # post is pi's: only its author may edit it (so admin and lead get 403), and the author or a
    # lead (pi, admin, lead) may delete it; contrib is neither.
    ("GET", "projects:taskpost-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:taskpost-list"): "401 404 2 2 2 2 403 404 403",
    ("PATCH", "projects:taskpost-detail"): "401 404 2 403 403 403 403 404 403",
    ("DELETE", "projects:taskpost-detail"): "401 404 2 2 2 403 403 404 403",
    ("POST", "projects:task-document-add"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "projects:task-document-remove"): "401 404 2 2 2 2 403 404 403",
    ("POST", "projects:task-attachment-add"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "projects:task-attachment-remove"): "401 404 2 2 2 2 403 404 403",
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3) ---
    # Reasoned per persona on P1: reads need view_project (everyone on P1, including the
    # lab viewer capped to viewer, D19); writes need edit_content (lead, contrib, and the implicit
    # leads pi/admin; pviewer and lviewer get 403). nonproj is not on P1, so every P1 object is
    # invisible to them: 404 (D21). outsider is in no Lab A role: 404. Attachment delete is
    # edit_content, not edit_project, so contrib may delete. Download needs only view_project.
    ("GET",    "documents:document-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:document-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:lab-document-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "documents:lab-document-list"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "documents:document-detail"): "401 404 2 2 2 2 2 404 2",
    ("PUT",    "documents:document-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "documents:document-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:revision-list"): "401 404 2 2 2 2 2 404 2",
    ("GET",    "documents:revision-detail"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:revision-restore"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:attachment-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:attachment-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:attachment-detail"): "401 404 2 2 2 2 2 404 2",
    ("DELETE", "documents:attachment-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:attachment-download"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:document-move"): "401 404 2 2 2 2 403 404 403",
    ("POST",   "documents:attachment-move"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "documents:folder-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:folder-list"): "401 404 2 2 2 2 403 404 403",
    ("PATCH",  "documents:folder-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "documents:folder-detail"): "401 404 2 2 2 2 403 404 403",
    # --- end documents/attachments (Phase 3) ---
    # --- provenance (Phase 4) ---
    # Same shape as documents: reads need view_project (everyone on P1, the capped lab viewer
    # included); create, edit and delete need edit_content (lead, contrib, implicit leads
    # pi/admin; pviewer and lviewer 403). nonproj is not on P1, so its objects are invisible:
    # 404 (D21); outsider is in no Lab A role: 404. Lineage is a read: view_project. Export
    # needs `export` (D28): only leads, so contrib is 403 even though contrib may edit; pi and
    # admin are implicit leads.
    ("GET",    "provenance:dataset-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:dataset-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:dataset-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:dataset-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:dataset-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:analysis-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:analysis-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:analysis-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:analysis-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:analysis-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:result-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:result-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:result-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:result-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:result-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:decision-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:decision-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:decision-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:decision-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:decision-detail"): "401 404 2 2 2 2 403 404 403",
    # Workflow records (Run 4, D133 to D138) follow the same shape as the other provenance
    # records: reads view_project, writes edit_content. Holder/reviewer in the payloads is the
    # acting persona, who can view P1 (anon and outsiders never get that far).
    # Funding is the exception (D226): PIs only. Every other persona gets 403 on the project's
    # list, and 404 on a record, because a record they may not see does not exist for them.
    ("GET",    "provenance:funding-list"): "401 404 2 403 403 403 403 404 403",
    ("POST",   "provenance:funding-list"): "401 404 2 403 403 403 403 404 403",
    ("GET",    "provenance:funding-detail"): "401 404 2 404 404 404 404 404 404",
    ("PATCH",  "provenance:funding-detail"): "401 404 2 404 404 404 404 404 404",
    ("DELETE", "provenance:funding-detail"): "401 404 2 404 404 404 404 404 404",
    ("GET",    "provenance:review-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:review-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:review-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:review-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:review-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:recruitment-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:recruitment-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:recruitment-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:recruitment-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:recruitment-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:recruitment-plan"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:recruitment-plan"): "401 404 2 2 2 2 403 404 403",
    # Project page batch: External records, the full-set result form and Workflow progress
    # follow the same shape: reads view_project, writes edit_content.
    ("POST",   "provenance:result-set"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:external-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:external-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:external-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:external-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:external-detail"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:workflow-progress"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:workflow-progress"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "labs:protocol-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "labs:protocol-list"): "401 404 2 2 2 2 403 404 403",
    ("PATCH",  "labs:protocol-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "labs:protocol-detail"): "401 404 2 2 2 2 403 404 403",
    ("POST",   "labs:protocol-use"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "labs:inventory-usage"): "401 404 2 2 2 2 2 404 2",
    # Undoing a use needs a lead, or the person who recorded it (D228). `lead` recorded the
    # fixture's usage; pi and admin are implicit leads; contrib did not record it.
    ("POST",   "labs:inventory-usage-reverse"): "401 404 2 2 2 403 403 404 403",
    ("GET",    "provenance:manuscript-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:manuscript-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:manuscript-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:manuscript-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:manuscript-detail"): "401 404 2 2 2 2 403 404 403",
    # Data management plan (Run 5, D180): reads view_project, writes edit_content, approve and
    # delete need a project lead (edit_project).
    ("GET",    "provenance:dmp"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:dmp"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:dmp"): "401 404 2 2 2 403 403 404 403",
    ("POST",   "provenance:dmp-approve"): "401 404 2 2 2 403 403 404 403",
    ("GET",    "provenance:dmp-revisions"): "401 404 2 2 2 2 2 404 2",
    ("GET",    "provenance:lineage"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:export"): "401 404 2 2 2 403 403 404 403",
    # --- end provenance (Phase 4) ---
    # --- ethics and notifications (Phase 5) ---
    # Approvals are lab-level (D27): every lab role reads them (view_ethics), pi/admin/member
    # edit them (edit_ethics), the lab viewer cannot. P1 membership does not matter for the
    # approval itself, only for its files and its project links (D48). Uploading is file access:
    # edit_ethics plus a visible linked project (nonproj sees none: 403) or pi/admin.
    # D52: PATCH and DELETE need the same visibility of every linked project, so nonproj is 403.
    # A notification is its recipient's alone: the fixture one is addressed to pi, so everyone
    # else in the lab gets 404, not 403. read-all only touches the caller's own rows. Retention
    # review needs view_retention: pi and lab_admin only.
    ("GET",    "ethics:approval-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "ethics:approval-list"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "ethics:approval-detail"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "ethics:approval-detail"): "401 404 2 2 2 2 2 403 403",
    ("DELETE", "ethics:approval-detail"): "401 404 2 2 2 2 2 403 403",
    ("POST",   "ethics:approval-attachments"): "401 404 2 2 2 2 2 403 403",
    # Search needs only view_lab, so all lab members get 200 (results: core/tests/test_search.py).
    ("GET",    "core:search"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "core:notification-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "core:notification-read"): "401 404 2 404 404 404 404 404 404",
    ("POST",   "core:notification-read-all"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "projects:retention-due"): "401 404 2 2 403 403 403 403 403",
    # --- end ethics and notifications (Phase 5) ---
    # --- handover (Phase 6) ---
    # Member handover needs manage_members (pi, admin) or the target being the requester. The
    # fixture membership is contrib's own, so contrib succeeds and every other member, the lab
    # viewer included, gets 403. Project handover needs manage_project_members on P1: leads and
    # the implicit leads pi/admin; contrib, pviewer and the capped lviewer get 403; nonproj
    # cannot see P1: 404.
    ("GET", "projects:member-handover"): "401 404 2 2 403 2 403 403 403",
    ("GET", "projects:project-handover"): "401 404 2 2 2 403 403 404 403",
    # --- end handover (Phase 6) ---
    # --- integrations (Run 2) ---
    # Providers are readable by every lab member (view_lab). Own accounts and connecting need
    # manage_integrations, which every lab role holds, the viewer included (D69). The fixture
    # account belongs to contrib: the owner disconnects it, pi and admin hold
    # manage_lab_integrations and revoke it, and nobody else can see it: 404, not 403 (D21, D54).
    # The OAuth callback needs only a login (the state check is inside), and with no state it
    # redirects to the error page for everyone, even a user of no Lab A role. External links
    # follow documents: read view_project, write edit_content; nonproj cannot see P1: 404.
    ("GET",    "integrations:provider-list"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "integrations:account-list"): "401 404 2 2 2 2 2 2 2",
    ("DELETE", "integrations:account-detail"): "401 404 2 2 404 2 404 404 404",
    ("POST",   "integrations:connect"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "integrations:oauth-callback"): "401 302 302 302 302 302 302 302 302",
    ("GET",    "integrations:external-link-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "integrations:external-link-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "integrations:external-link-detail"): "401 404 2 2 2 2 2 404 2",
    ("DELETE", "integrations:external-link-detail"): "401 404 2 2 2 2 403 404 403",
    # D70: the picker token is the requester's own active Drive account's, so only the four
    # people the fixture gave one get 200; everyone else in the lab gets 404.
    ("GET",    "integrations:picker-token"): "401 404 2 2 2 2 404 404 404",
    # A freshness check needs only view_project (it uses the linker's account); accepting a
    # change is a write: edit_content.
    ("POST",   "integrations:external-link-check"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "integrations:external-link-accept-change"): "401 404 2 2 2 2 403 404 403",
    # --- end integrations (Run 2) ---
    # --- integrations framework (Run 3, D85) ---
    # Item search reads the provider for something to link, so it needs edit_content on P1:
    # the implicit leads pi/admin, lead and contrib (each holds an active fake account); the
    # project viewer and the capped lviewer get 403; nonproj cannot see P1: 404.
    ("GET",    "integrations:item-search"): "401 404 2 2 2 2 403 404 403",
    # --- end integrations framework (Run 3) ---
    # --- automation and imports (D240-D242) ---
    # Task import and the Zotero import use your own connected account: pi, admin, lead and
    # contrib hold one in the fixture; anyone else permitted gets 404, as for the picker token.
    # Webhooks are manage_lab_integrations: pi and admin only.
    ("GET",    "integrations:task-sources"): "401 404 2 2 2 2 404 404 404",
    ("POST",   "integrations:import-tasks"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "integrations:webhook-list"): "401 404 2 2 403 403 403 403 403",
    ("POST",   "integrations:webhook-list"): "401 404 2 2 403 403 403 403 403",
    ("PATCH",  "integrations:webhook-detail"): "401 404 2 2 403 403 403 403 403",
    ("DELETE", "integrations:webhook-detail"): "401 404 2 2 403 403 403 403 403",
    ("POST",   "integrations:webhook-test"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "papers:zotero-import"): "401 404 2 2 2 2 404 404 403",
    ("POST",   "papers:zotero-import"): "401 404 2 2 2 2 404 404 403",
    # --- end automation and imports ---
    # --- admin area (Run 4, D146-D151) ---
    # Lab details, institution resources (writes) and onboarding need manage_lab: pi and admin
    # only. Resources are read by every lab member (view_lab). Inventory is read by every member,
    # the viewer included, and edited with manage_inventory: pi, admin and members; the lab
    # viewer gets 403 (D147). Another lab's ids are 404 for everyone (cross-lab swap test).
    ("GET",    "labs:resource-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:resource-list"): "401 404 2 2 403 403 403 403 403",
    ("POST",   "labs:resource-load-starters"): "401 404 2 2 403 403 403 403 403",
    ("PATCH",  "labs:resource-detail"): "401 404 2 2 403 403 403 403 403",
    ("DELETE", "labs:resource-detail"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "labs:onboarding-list"): "401 404 2 2 403 403 403 403 403",
    ("POST",   "labs:onboarding-list"): "401 404 2 2 403 403 403 403 403",
    ("PATCH",  "labs:onboarding-detail"): "401 404 2 2 403 403 403 403 403",
    ("DELETE", "labs:onboarding-detail"): "401 404 2 2 403 403 403 403 403",
    ("POST",   "labs:onboarding-completion"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "labs:inventory-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:inventory-list"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "labs:inventory-export"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:inventory-import"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "labs:inventory-detail"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "labs:inventory-detail"): "401 404 2 2 2 2 2 2 403",
    ("DELETE", "labs:inventory-detail"): "401 404 2 2 2 2 2 2 403",
    # Orders: everyone in the lab reads and exports, manage_inventory writes, so viewers get 403.
    ("GET",    "labs:order-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:order-list"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "labs:order-export"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "labs:order-detail"): "401 404 2 2 2 2 2 2 403",
    # --- end admin area (Run 4) ---
    # --- lab chat and calendar ---
    # Lab chat is D206 for the whole lab: every member reads and posts, the lab viewer included.
    # The fixture message is contrib's: its author or manage_lab (pi, admin) may delete it.
    ("GET",    "labs:labchat-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:labchat-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:labchat-read"): "401 404 2 2 2 2 2 2 2",
    ("DELETE", "labs:labchat-detail"): "401 404 2 2 403 2 403 403 403",
    # The calendar is a read for every member (rows are filtered: test_lab_tools.py); events need
    # contribute_lab, which the lab viewer lacks.
    ("GET",    "labs:calendar"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:labevent-list"): "401 404 2 2 2 2 2 2 403",
    ("PATCH",  "labs:labevent-detail"): "401 404 2 2 2 2 2 2 403",
    ("DELETE", "labs:labevent-detail"): "401 404 2 2 2 2 2 2 403",
    # D230: everyone is on the fixture meeting, so reaching it needs only the write permission;
    # someone not on it gets a 404 (test_meetings_feeds.py).
    ("POST",   "labs:meeting-list"): "401 404 2 2 2 2 2 2 403",
    ("PATCH",  "labs:meeting-detail"): "401 404 2 2 2 2 2 2 403",
    ("DELETE", "labs:meeting-detail"): "401 404 2 2 2 2 2 2 403",
    # D231: your own feed link, for any member. The .ics URL takes a token, not a session: anon
    # has none (401); outsider holds a real one but is not in the lab (404).
    ("GET",    "labs:calendar-feed"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:calendar-feed"): "401 404 2 2 2 2 2 2 2",
    ("DELETE", "labs:calendar-feed"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "labs:calendar-ics"): "401 404 2 2 2 2 2 2 2",
    # D253 to D256: your own Google Calendar and call settings. Every lab role may connect its
    # own accounts (manage_integrations, the viewer too), and nobody in the fixture is connected,
    # so each answer is the "not connected" state rather than an error.
    ("GET",    "labs:calendar-google"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "labs:calendar-google"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "labs:calendar-google-sync"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "labs:calendar-google-events"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "labs:calendar-video-options"): "401 404 2 2 2 2 2 2 2",
    # --- end lab chat and calendar ---
    # --- training (Run 5, D175-D179) ---
    # Requirements are read by every lab member and managed with manage_training (pi, admin).
    # Records: the fixture one is contrib's. Everyone may call the endpoints, but the queryset is
    # the owner's own (or everything for manage_training), so everyone else gets 404, not 403
    # (D176). Verify, the compliance matrix and the expiring list need manage_training: 403.
    # Filing a record is open to every member (a viewer too); the payload files it for oneself.
    ("GET",    "training:requirement-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "training:requirement-list"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "training:requirement-detail"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "training:requirement-detail"): "401 404 2 2 403 403 403 403 403",
    ("DELETE", "training:requirement-detail"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "training:record-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "training:record-list"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "training:record-detail"): "401 404 2 2 404 2 404 404 404",
    ("PATCH",  "training:record-detail"): "401 404 2 2 404 2 404 404 404",
    ("DELETE", "training:record-detail"): "401 404 2 2 404 2 404 404 404",
    ("POST",   "training:record-verify"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "training:record-certificate"): "401 404 2 2 404 2 404 404 404",
    ("POST",   "training:record-certificate"): "401 404 2 2 404 2 404 404 404",
    ("GET",    "training:compliance"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "training:my-training"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "training:expiring"): "401 404 2 2 403 403 403 403 403",
    # --- end training (Run 5) ---
    # --- paper library ---
    # Every member reads; contribute_lab (not the lab viewer) adds. The fixture paper and note are
    # contrib's: an author edits only their own note; the author, pi or admin removes it.
    ("GET",    "papers:paper-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "papers:paper-list"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "papers:doi-lookup"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "papers:paper-detail"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "papers:paper-detail"): "401 404 2 2 2 2 2 2 403",
    ("DELETE", "papers:paper-detail"): "401 404 2 2 403 2 403 403 403",
    ("GET",    "papers:paper-pdf"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "papers:paper-pdf"): "401 404 2 2 2 2 2 2 403",
    ("GET",    "papers:paper-citation"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "papers:paper-notes"): "401 404 2 2 2 2 2 2 403",
    ("PATCH",  "papers:note-detail"): "401 404 403 403 403 2 403 403 403",
    ("DELETE", "papers:note-detail"): "401 404 2 2 403 2 403 403 403",
    # --- end paper library ---
    # --- AI access (Run 5, D160-D169) ---
    # The consent API and your own grants need only a login (they are the user's own); the
    # payloads consent for, or create a token on, the persona's own lab. The fixture grant is
    # contrib's: only its owner sees it, so everyone else gets 404, not 403 (D21). Each lab's
    # grant list and removing the lab from a grant need manage_lab_integrations: pi and admin.
    ("POST",   "assistant:authorize"): "401 2 2 2 2 2 2 2 2",
    ("GET",    "assistant:grant-list"): "401 2 2 2 2 2 2 2 2",
    ("POST",   "assistant:grant-list"): "401 2 2 2 2 2 2 2 2",
    ("DELETE", "assistant:grant-detail"): "401 404 404 404 404 2 404 404 404",
    ("GET",    "assistant:lab-grant-list"): "401 404 2 2 403 403 403 403 403",
    ("DELETE", "assistant:lab-grant-detail"): "401 404 2 2 403 403 403 403 403",
    # --- end AI access (Run 5) ---
    # --- in-app assistant (Run 5, D187-D192) ---
    # Keys are the caller's own (every persona holds one), so every signed-in person succeeds.
    # The lab's AI policy is read by every member and changed by manage_lab (pi, admin). The
    # fixture conversation is pi's: only its owner may read, delete or continue it, so everyone
    # else gets 404 (never 403, and not even a lab admin), and it has a write waiting for approval
    # so both the message and the approval endpoints can answer 200 (the stream is not read).
    ("GET",    "assistant:key-list"): "401 2 2 2 2 2 2 2 2",
    ("PUT",    "assistant:key-detail"): "401 2 2 2 2 2 2 2 2",
    ("PATCH",  "assistant:key-detail"): "401 2 2 2 2 2 2 2 2",
    ("DELETE", "assistant:key-detail"): "401 2 2 2 2 2 2 2 2",
    ("GET",    "assistant:ai-policy"): "401 404 2 2 2 2 2 2 2",
    ("PATCH",  "assistant:ai-policy"): "401 404 2 2 403 403 403 403 403",
    ("GET",    "assistant:assistant-config"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "assistant:conversation-list"): "401 404 2 2 2 2 2 2 2",
    ("POST",   "assistant:conversation-list"): "401 404 2 2 2 2 2 2 2",
    ("GET",    "assistant:conversation-detail"): "401 404 2 404 404 404 404 404 404",
    ("DELETE", "assistant:conversation-detail"): "401 404 2 404 404 404 404 404 404",
    ("POST",   "assistant:conversation-message"): "401 404 2 404 404 404 404 404 404",
    ("POST",   "assistant:conversation-approval"): "401 404 2 404 404 404 404 404 404",
    # --- end in-app assistant (Run 5) ---
}
# fmt: on


# ---------------------------------------------------------------- world

_n = iter(range(10**6))


def _user(name):
    user = User.objects.create(email=f"{name}@example.com", display_name=name)
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


# --- documents/attachments (Phase 3) ---
def _doc_fixtures(lab, project, user, tag):
    """A document with 2 revisions and a small PDF, in `lab`'s P1. Bytes carry `tag`."""
    doc = document_services.create_document(
        project=project, user=user, title=f"Doc {tag}", content=[{"type": "paragraph"}]
    )
    doc = document_services.save_document(
        doc, title=f"Doc {tag}", content=[{"type": "paragraph", "n": 2}], base_version=1, user=user
    )
    pdf = SimpleUploadedFile(
        f"file-{tag}.pdf", f"%PDF-1.4 bytes of {tag}".encode(), content_type="application/pdf"
    )
    attachment = document_services.upload_attachment(project=project, user=user, file=pdf)
    return doc, attachment


def _folder_fixture(project, user, tag):
    return document_services.create_folder(project=project, user=user, name=f"Folder {tag}")


# --- end documents/attachments (Phase 3) ---


# --- provenance (Phase 4) ---
def _prov_fixtures(lab, project, user, doc, attachment, tag):
    """One of each provenance model in `project`, linked together. The dataset and analysis
    the URLs name (`ds_free`, `an_free`) are not blocked from deletion (a dataset used by an
    analysis, and an analysis with results, both give 409), so DELETE can succeed."""
    kw = {"lab": lab, "project": project}
    ran = {"ran_by": user, "ran_at": "2030-01-01T00:00:00Z"}
    code = {"code_repo_url": f"https://example.com/{tag}.git", "code_commit": "abc1234"}
    ds_used = DatasetRecord.objects.create(
        name=f"Dataset {tag}", version_label="v1", created_by=user, **kw
    )
    ds_free = DatasetRecord.objects.create(
        name=f"Dataset {tag}", version_label="v2", previous_version=ds_used, created_by=user, **kw
    )
    an_main = Analysis.objects.create(title=f"Analysis {tag}", **ran, **code, **kw)
    an_main.datasets.add(ds_used)
    an_free = Analysis.objects.create(title=f"Analysis free {tag}", **ran, **code, **kw)
    an_free.datasets.add(ds_used)
    result = Result.objects.create(title=f"Result {tag}", analysis=an_main, created_by=user, **kw)
    result.attachments.add(attachment)
    manuscript = ManuscriptLink.objects.create(
        title=f"Manuscript {tag}", url="https://example.com/ms", created_by=user, **kw
    )
    manuscript.results.add(result)
    decision = Decision.objects.create(
        title=f"Decision {tag}", decided_on="2030-01-01", decided_by=user, **kw
    )
    decision.analyses.add(an_main)
    decision.results.add(result)
    decision.datasets.add(ds_free)
    decision.supporting_documents.add(doc)
    decision.supporting_attachments.add(attachment)
    # Workflow records (Run 4): a funding record, a review item, one recruitment entry
    funding = FundingRecord.objects.create(
        funder=f"Funder {tag}",
        amount="1000.00",
        holder=user,
        created_by=user,
        **kw,
    )
    review = ReviewItem.objects.create(title=f"Review {tag}", reviewer=user, created_by=user, **kw)
    entry = RecruitmentEntry.objects.create(
        entry_date="2030-01-01",
        status="screened",
        count=3,
        notes=f"Entry {tag}",
        created_by=user,
        **kw,
    )
    DataManagementPlan.objects.create(data_description=f"DMP {tag}", updated_by=user, **kw)
    external = ExternalOutput.objects.create(
        title=f"Poster {tag}",
        type="poster",
        date="2030-01-01",
        attachment=attachment,
        created_by=user,
        **kw,
    )
    return {
        "externaloutput_id": external.pk,
        "fundingrecord_id": funding.pk,
        "reviewitem_id": review.pk,
        "recruitmententry_id": entry.pk,
        "datasetrecord_id": ds_free.pk,
        "analysis_id": an_free.pk,
        "result_id": result.pk,
        "decision_id": decision.pk,
        "manuscriptlink_id": manuscript.pk,
    }


# --- end provenance (Phase 4) ---


# --- ethics and notifications (Phase 5) ---
def _ethics_fixtures(lab, project, user, tag):
    """An approval linked to `project` with one PDF, and a notification addressed to `user`
    (the lab's pi). Names carry `tag` so the swap test can look for leaks."""
    approval = EthicsApproval.objects.create(
        lab=lab,
        approval_number=f"NUM-{tag}",
        board="Board X",
        title=f"Ethics {tag}",
        approval_date="2030-01-01",
        expiry_date="2031-01-01",
        created_by=user,
    )
    approval.projects.add(project)
    pdf = SimpleUploadedFile(
        f"ethics-{tag}.pdf", f"%PDF-1.4 ethics bytes of {tag}".encode(), "application/pdf"
    )
    attachment = document_services.upload_attachment(approval=approval, user=user, file=pdf)
    notification = Notification.objects.create(
        lab=lab,
        recipient=user,
        kind=NotificationKind.ETHICS_EXPIRY,
        title=f"Notification {tag}",
        dedupe_key=f"matrix:{tag}",
    )
    return approval, attachment, notification


# --- end ethics and notifications (Phase 5) ---


def _webhook(lab, user, tag):  # webhooks (D241)
    return Webhook.objects.create(
        lab=lab,
        created_by=user,
        name=f"Webhook {tag}",
        kind="webhook",
        url_ct="x",
        secret_ct="y",
        host="hooks.example.org",
        events=["project.created"],
    )


# --- integrations (Run 2) ---
def _integration_fixtures(lab, project, owners, tag):
    """An active connected account per owner (name -> user), and one external link made by the
    first owner on their account. Titles and emails carry `tag` so the swap test can look for
    leaks. Nothing here holds a token."""
    now = datetime.datetime(2030, 1, 1, tzinfo=datetime.UTC)
    accounts = {
        name: ConnectedAccount.objects.create(
            lab=lab,
            user=user,
            provider="fake",
            external_account_id=f"ext-{name}-{tag}",
            external_email=f"{name}-{tag}@fake.test",
            connected_at=now,
        )
        for name, user in owners.items()
    }
    for name, user in owners.items():  # a Drive account with a token for the picker (D70)
        drive = ConnectedAccount(
            lab=lab,
            user=user,
            provider="google_drive",
            external_account_id=f"gd-{name}-{tag}",
            external_email=f"gd-{name}-{tag}@fake.test",
            connected_at=now,
        )
        drive.set_tokens(access=f"matrix-{name}", refresh=None, expires_at=None)
        drive.save()
    for name, user in owners.items():  # a Zotero account for the paper import (D242)
        ConnectedAccount.objects.create(
            lab=lab,
            user=user,
            provider="zotero",
            external_account_id=f"zot-{name}-{tag}",
            external_email=f"zot-{name}-{tag}@fake.test",
            connected_at=now,
        )
    first = next(iter(owners))
    link = ExternalLink.objects.create(
        lab=lab,
        project=project,
        provider="fake",
        connected_account=accounts[first],
        external_id=f"file-{tag}",
        url="https://fake.test/file",
        title=f"External link {tag}",
        linked_by=owners[first],
    )
    return accounts, link


# --- admin area (Run 4) ---
def _admin_fixtures(lab, tag):
    """One resource, onboarding item and inventory item; names carry `tag` for the swap test."""
    res = InstitutionResource.objects.create(
        lab=lab, category="funding", title=f"Resource {tag}", url=f"https://example.edu/{tag}"
    )
    item = OnboardingItem.objects.create(lab=lab, kind="new_member", title=f"Onboarding {tag}")
    inv = InventoryItem.objects.create(lab=lab, name=f"Inventory {tag}", category="equipment")
    return res, item, inv


# --- end admin area (Run 4) ---


def _protocol_fixtures(lab, project, user, tag):
    """A protocol with one reagent and one recorded use by `user` (for inventory, D228)."""
    reagent_item = InventoryItem.objects.create(
        lab=lab, name=f"Reagent {tag}", category="reagent", quantity=100, unit="mL"
    )
    protocol = Protocol.objects.create(
        lab=lab, project=project, name=f"Protocol {tag}", created_by=user
    )
    reagent = ProtocolReagent.objects.create(
        lab=lab, protocol=protocol, item=reagent_item, amount=1, unit="mL"
    )
    usage = InventoryUsage.objects.create(
        lab=lab,
        project=project,
        protocol=protocol,
        protocol_name=protocol.name,
        item=reagent_item,
        amount=1,
        unit="mL",
        used_by=user,
        request_id=uuid.uuid4(),
    )
    return {"protocol_id": protocol.pk, "reagent_id": reagent.pk, "inventoryusage_id": usage.pk}


def _lab_tool_fixtures(lab, user, inv, tag, attendees=()):
    """An inventory order, a lab chat message and a calendar event, all made by `user`, and a
    meeting with `user` and everyone in `attendees` on it."""
    meeting = Meeting.objects.create(
        lab=lab,
        title=f"Meeting {tag}",
        starts_at="2030-01-01T10:00:00Z",
        ends_at="2030-01-01T11:00:00Z",
        created_by=user,
    )
    meeting.attendees.set([user, *attendees])
    return {
        "meeting_id": meeting.pk,
        "inventoryorder_id": InventoryOrder.objects.create(
            lab=lab, item=inv, name=f"Order {tag}", requested_by=user
        ).pk,
        "labchatmessage_id": LabChatMessage.objects.create(
            lab=lab, author=user, body=f"Lab chat {tag}"
        ).pk,
        "labevent_id": LabEvent.objects.create(
            lab=lab, title=f"Event {tag}", date="2030-01-01", created_by=user
        ).pk,
    }


# --- training (Run 5) ---
def _training_fixtures(lab, owner, tag):
    """`free` has no records (the URL's DELETE can succeed); `used` has the owner's record, with a
    certificate whose bytes carry `tag`. Returns (free, record)."""
    free = TrainingRequirement.objects.create(
        lab=lab, name=f"Training free {tag}", category="safety", validity_months=12
    )
    used = TrainingRequirement.objects.create(
        lab=lab, name=f"Training {tag}", category="ethics", validity_months=24
    )
    record = TrainingRecord.objects.create(
        lab=lab,
        requirement=used,
        user=owner,
        completed_on=datetime.date(2030, 1, 1),
        expires_on=datetime.date(2032, 1, 1),
        notes=f"Notes {tag}",
    )
    cert = SimpleUploadedFile(
        f"cert-{tag}.pdf", f"cert bytes of {tag}".encode(), content_type="application/pdf"
    )
    training_services.upload_certificate(record, actor=owner, file=cert)
    return free, record


# --- end training (Run 5) ---


def _paper_fixtures(lab, owner, tag):  # paper library
    paper = paper_services.create_paper(
        lab, user=owner, data={"title": f"Paper {tag}", "abstract": f"Abstract {tag}"}
    )
    note = paper_services.add_note(paper, author=owner, body=f"Paper note {tag}")
    pdf = SimpleUploadedFile(
        f"paper-{tag}.pdf", f"%PDF-1.4 bytes of {tag}".encode(), content_type="application/pdf"
    )
    paper_services.upload_pdf(paper, user=owner, file=pdf)
    return paper, note


@pytest.fixture(autouse=True)
def _matrix_fake_provider(monkeypatch, settings):
    """The fake provider is configured, and reads items without any network."""

    def fetch_item(account, external_id):
        return {
            "title": "Linked",
            "url": "https://fake.test/f",
            "mime_type": "text/plain",
            "modified_at": None,
            "version": "1",
            "checksum": "",
        }

    def search_items(account, query, target):  # integrations framework (Run 3)
        return [{"id": "f1", "title": "Linked", "subtitle": "", "modified": None, "url": ""}]

    monkeypatch.setitem(
        registry.PROVIDERS,
        "fake",
        dataclasses.replace(
            FAKE,
            fetch_item=fetch_item,
            search_items=search_items,
            task_sources=lambda account: [{"id": "s1", "name": "List"}],  # task import (D240)
            fetch_tasks=lambda account, source: [
                {"title": "Imported", "notes": "", "due_date": None}
            ],
        ),
    )
    # Zotero import (D242) and webhooks (D241): no network.
    monkeypatch.setitem(
        registry.PROVIDERS,
        "zotero",
        dataclasses.replace(
            registry.PROVIDERS["zotero"],
            search_items=lambda account, query, target: [
                {"id": "u1:ABCD2345", "title": "Paper", "subtitle": ""}
            ],
        ),
    )
    monkeypatch.setattr(
        zotero_provider, "paper_fields", lambda account, external_id: {"title": "Imported paper"}
    )
    monkeypatch.setattr(integrations_http, "_resolve", lambda host: ["93.184.216.34"])
    monkeypatch.setattr(webhooks, "_post", lambda hook, message: 200)
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "fake": {"client_id": "fake-client", "client_secret": "fake-secret"},
    }


# --- end integrations (Run 2) ---


# --- AI access (Run 5) ---
def _ai_fixtures(lab, owner, tag):
    """A read-only personal-access grant on `lab` (no token row: nothing secret in the world)."""
    grant = AIGrant.objects.create(user=owner, kind="pat", name=f"AI grant {tag}", access="read")
    grant.labs.add(lab)
    return grant


def _ai_lab(user, w):
    """The persona's own lab: Lab B for its PI (the outsider), Lab A for everyone else."""
    outsider = user is not None and user.pk == w.user_ids["outsider"]
    return str((w.b if outsider else w.a)["lab_id"])


def _ai_consent(user, w):
    cb = "https://claude.ai/api/mcp/auth_callback"
    client = register_client({"client_name": "Matrix app", "redirect_uris": [cb]})
    return {
        "response_type": "code",
        "client_id": client.client_id,
        "redirect_uri": cb,
        "code_challenge": "c" * 43,
        "code_challenge_method": "S256",
        "decision": "approve",
        "labs": [_ai_lab(user, w)],
        "access": "read",
    }


# --- end AI access (Run 5) ---


# --- in-app assistant (Run 5) ---
def _assistant_fixtures(lab, owner, project, tag):
    """The owner's conversation, ending on a write that waits for approval."""
    conv = Conversation.objects.create(
        user=owner,
        lab=lab,
        project=project,
        provider="anthropic",
        model="claude-opus-5-5",
        title=f"Chat {tag}",
        system_prompt="system",
    )
    Message.objects.create(
        conversation=conv, seq=1, role="user", content=[{"type": "text", "text": f"Question {tag}"}]
    )
    Message.objects.create(
        conversation=conv,
        seq=2,
        role="assistant",
        stop_reason="tool_use",
        model="claude-opus-5-5",
        content=[
            {
                "type": "tool_use",
                "id": "toolu_matrix",
                "name": "create_task",
                "input": {"lab_id": str(lab.pk), "project_id": str(project.pk), "title": "Add"},
            }
        ],
    )
    return conv


@pytest.fixture(autouse=True)
def _matrix_fake_key_check(monkeypatch):
    """Saving a key makes one provider call; the matrix never reaches the network."""
    monkeypatch.setattr(ai_keys, "check", lambda provider, api_key: None)


# --- end in-app assistant (Run 5) ---


def build_world():
    """Two labs, each with a project, a membership and a pending invite. Add each new
    lab-data model here, once for A and once for B."""
    inst, _ = Institution.objects.get_or_create(name="Matrix Institution")
    users = {name: _user(name) for name in PERSONAS if name != "anon"}
    lab_roles = {
        "pi": LabRole.PI,
        "admin": LabRole.LAB_ADMIN,
        "lead": LabRole.MEMBER,
        "contrib": LabRole.MEMBER,
        "pviewer": LabRole.MEMBER,
        "nonproj": LabRole.MEMBER,
        "lviewer": LabRole.VIEWER,
    }
    lab_a = Lab.objects.create(institution=inst, name="Lab A", created_by=users["pi"])
    memberships = {
        n: LabMembership.objects.create(lab=lab_a, user=users[n], role=r)
        for n, r in lab_roles.items()
    }
    p1 = Project.objects.create(lab=lab_a, name="P1", created_by=users["pi"])
    Project.objects.create(lab=lab_a, name="P2", created_by=users["pi"])  # nobody is on it
    for name, role in [
        ("lead", ProjectRole.LEAD),
        ("contrib", ProjectRole.CONTRIBUTOR),
        ("pviewer", ProjectRole.VIEWER),
        ("lviewer", ProjectRole.CONTRIBUTOR),
    ]:
        ProjectMembership.objects.create(lab=lab_a, project=p1, user=users[name], role=role)
    # --- projects/tasks (Phase 3): Lab A fixtures ---
    task_a = Task.objects.create(lab=lab_a, project=p1, title="Task A", created_by=users["pi"])
    deadline_a = ProjectDeadline.objects.create(
        lab=lab_a, project=p1, title="Deadline A", due_date="2030-01-01"
    )
    chat_a = ChatMessage.objects.create(lab=lab_a, project=p1, author=users["contrib"], body="Hi")
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3): Lab A fixtures ---
    doc_a, attachment_a = _doc_fixtures(lab_a, p1, users["pi"], "lab-a")
    task_a.documents.add(doc_a)  # task thread and links (Run 4)
    task_a.attachments.add(attachment_a)
    post_a = TaskPost.objects.create(lab=lab_a, task=task_a, author=users["pi"], body="Post lab-a")
    # --- end documents/attachments (Phase 3) ---
    prov_a = _prov_fixtures(lab_a, p1, users["pi"], doc_a, attachment_a, "lab-a")  # Phase 4
    eth_a, eth_att_a, note_a = _ethics_fixtures(lab_a, p1, users["pi"], "lab-a")  # Phase 5
    int_accounts_a, link_a = _integration_fixtures(
        lab_a, p1, {n: users[n] for n in ("pi", "admin", "lead", "contrib")}, "lab-a"
    )  # integrations (Run 2)
    res_a, onb_a, inv_a = _admin_fixtures(lab_a, "lab-a")  # admin area (Run 4)
    tools_a = _lab_tool_fixtures(lab_a, users["contrib"], inv_a, "lab-a", users.values())
    protocol_a = _protocol_fixtures(lab_a, p1, users["lead"], "lab-a")
    tr_free_a, tr_rec_a = _training_fixtures(lab_a, users["contrib"], "lab-a")  # training (Run 5)
    paper_a, paper_note_a = _paper_fixtures(lab_a, users["contrib"], "lab-a")
    ai_a = _ai_fixtures(lab_a, users["contrib"], "lab-a")  # AI access (Run 5)
    for persona_user in users.values():  # in-app assistant (Run 5): everyone holds a key
        row = AIProviderKey(user=persona_user, provider="anthropic")
        row.set_key("sk-ant-api03-matrix-key-abcdefghijklmnop")
        row.save()
    conv_a = _assistant_fixtures(lab_a, users["pi"], p1, "lab-a")
    invite_a, _ = Invite.issue(
        lab=lab_a, email="invitee-a@example.com", role=LabRole.MEMBER, invited_by=users["pi"]
    )

    secret_pi = users["outsider"]
    lab_b = Lab.objects.create(institution=inst, name="Lab B Secret", created_by=secret_pi)
    membership_b = LabMembership.objects.create(lab=lab_b, user=secret_pi, role=LabRole.PI)
    p1_b = Project.objects.create(lab=lab_b, name="P1 Secret", created_by=secret_pi)
    # --- projects/tasks (Phase 3): Lab B mirror ---
    pm_b = ProjectMembership.objects.create(
        lab=lab_b, project=p1_b, user=secret_pi, role=ProjectRole.LEAD
    )
    task_b = Task.objects.create(
        lab=lab_b, project=p1_b, title="Task B Secret", created_by=secret_pi
    )
    deadline_b = ProjectDeadline.objects.create(
        lab=lab_b, project=p1_b, title="Deadline B Secret", due_date="2030-01-01"
    )
    chat_b = ChatMessage.objects.create(
        lab=lab_b, project=p1_b, author=secret_pi, body="Chat B Secret"
    )
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3): Lab B mirror ---
    doc_b, attachment_b = _doc_fixtures(lab_b, p1_b, secret_pi, "LAB-B-SECRET")
    task_b.documents.add(doc_b)  # task thread and links (Run 4)
    task_b.attachments.add(attachment_b)
    post_b = TaskPost.objects.create(
        lab=lab_b, task=task_b, author=secret_pi, body="Post LAB-B-SECRET"
    )
    # --- end documents/attachments (Phase 3) ---
    prov_b = _prov_fixtures(lab_b, p1_b, secret_pi, doc_b, attachment_b, "LAB-B-SECRET")  # Ph. 4
    eth_b, eth_att_b, note_b = _ethics_fixtures(lab_b, p1_b, secret_pi, "LAB-B-SECRET")  # Phase 5
    int_accounts_b, link_b = _integration_fixtures(
        lab_b, p1_b, {"outsider": secret_pi}, "LAB-B-SECRET"
    )  # integrations (Run 2)
    res_b, onb_b, inv_b = _admin_fixtures(lab_b, "LAB-B-SECRET")  # admin area (Run 4)
    tools_b = _lab_tool_fixtures(lab_b, secret_pi, inv_b, "LAB-B-SECRET")
    protocol_b = _protocol_fixtures(lab_b, p1_b, secret_pi, "LAB-B-SECRET")
    tr_free_b, tr_rec_b = _training_fixtures(lab_b, secret_pi, "LAB-B-SECRET")  # training (Run 5)
    paper_b, paper_note_b = _paper_fixtures(lab_b, secret_pi, "LAB-B-SECRET")
    ai_b = _ai_fixtures(lab_b, secret_pi, "LAB-B-SECRET")  # AI access (Run 5)
    conv_b = _assistant_fixtures(lab_b, secret_pi, p1_b, "LAB-B-SECRET")  # assistant (Run 5)
    invite_b, _ = Invite.issue(
        lab=lab_b,
        email="invitee-b-secret@example.com",
        role=LabRole.MEMBER,
        invited_by=secret_pi,
    )
    return SimpleNamespace(
        user_ids={n: u.pk for n, u in users.items()},
        a={
            "lab_id": lab_a.pk,
            "membership_id": memberships["contrib"].pk,
            "invite_id": invite_a.pk,
            # --- projects/tasks (Phase 3) ---
            "project_id": p1.pk,
            "projectmembership_id": ProjectMembership.objects.for_lab(lab_a)
            .get(project=p1, user=users["contrib"])
            .pk,
            "projectdeadline_id": deadline_a.pk,
            "task_id": task_a.pk,
            "chatmessage_id": chat_a.pk,
            "taskpost_id": post_a.pk,
            # --- documents/attachments (Phase 3) ---
            "document_id": doc_a.pk,
            "version": 1,
            "attachment_id": attachment_a.pk,
            "folder_id": _folder_fixture(p1, users["pi"], "lab-a").pk,
            **prov_a,  # provenance (Phase 4)
            "ethicsapproval_id": eth_a.pk,  # ethics and notifications (Phase 5)
            "notification_id": note_a.pk,
            "ethics_attachment_id": eth_att_a.pk,  # not a URL kwarg: ethics download test
            "provider": "fake",  # integrations (Run 2)
            "connectedaccount_id": int_accounts_a["contrib"].pk,
            "externallink_id": link_a.pk,
            "webhook_id": _webhook(lab_a, users["pi"], "lab-a").pk,  # webhooks (D241)
            "institutionresource_id": res_a.pk,  # admin area (Run 4)
            "onboardingitem_id": onb_a.pk,
            "inventoryitem_id": inv_a.pk,
            **tools_a,
            **protocol_a,
            "trainingrequirement_id": tr_free_a.pk,  # training (Run 5)
            "trainingrecord_id": tr_rec_a.pk,
            "paper_id": paper_a.pk,
            "papernote_id": paper_note_a.pk,
            "aigrant_id": ai_a.pk,  # AI access (Run 5)
            "ai_provider": "anthropic",  # in-app assistant (Run 5)
            "conversation_id": conv_a.pk,
        },
        b={
            "lab_id": lab_b.pk,
            "membership_id": membership_b.pk,
            "invite_id": invite_b.pk,
            # --- projects/tasks (Phase 3) ---
            "project_id": p1_b.pk,
            "projectmembership_id": pm_b.pk,
            "projectdeadline_id": deadline_b.pk,
            "task_id": task_b.pk,
            "chatmessage_id": chat_b.pk,
            "taskpost_id": post_b.pk,
            # --- documents/attachments (Phase 3) ---
            "document_id": doc_b.pk,
            "version": 1,
            "attachment_id": attachment_b.pk,
            "folder_id": _folder_fixture(p1_b, secret_pi, "LAB-B-SECRET").pk,
            **prov_b,  # provenance (Phase 4)
            "ethicsapproval_id": eth_b.pk,  # ethics and notifications (Phase 5)
            "notification_id": note_b.pk,
            "ethics_attachment_id": eth_att_b.pk,
            "provider": "fake",  # integrations (Run 2)
            "connectedaccount_id": int_accounts_b["outsider"].pk,
            "externallink_id": link_b.pk,
            "webhook_id": _webhook(lab_b, users["outsider"], "lab-b").pk,  # webhooks (D241)
            "institutionresource_id": res_b.pk,  # admin area (Run 4)
            "onboardingitem_id": onb_b.pk,
            "inventoryitem_id": inv_b.pk,
            **tools_b,
            **protocol_b,
            "trainingrequirement_id": tr_free_b.pk,  # training (Run 5)
            "trainingrecord_id": tr_rec_b.pk,
            "paper_id": paper_b.pk,
            "papernote_id": paper_note_b.pk,
            "aigrant_id": ai_b.pk,  # AI access (Run 5)
            "ai_provider": "anthropic",  # in-app assistant (Run 5)
            "conversation_id": conv_b.pk,
        },
        b_names=[
            "Lab B Secret",
            "P1 Secret",
            "invitee-b-secret@example.com",
            "Task B Secret",  # projects/tasks (Phase 3)
            "Chat B Secret",
            "Deadline B Secret",
            "Post LAB-B-SECRET",  # task thread (Run 4)
            # --- documents/attachments (Phase 3): titles, filename and the file's bytes ---
            "Doc LAB-B-SECRET",
            "Folder LAB-B-SECRET",
            "file-LAB-B-SECRET.pdf",
            "bytes of LAB-B-SECRET",
            # --- provenance (Phase 4): every title and the repo URL carry the tag ---
            "Dataset LAB-B-SECRET",
            "Analysis LAB-B-SECRET",
            "Analysis free LAB-B-SECRET",
            "Result LAB-B-SECRET",
            "Decision LAB-B-SECRET",
            "Manuscript LAB-B-SECRET",
            "Funder LAB-B-SECRET",  # workflow (Run 4)
            "Review LAB-B-SECRET",
            "Entry LAB-B-SECRET",
            "LAB-B-SECRET.git",
            # --- ethics and notifications (Phase 5) ---
            "Ethics LAB-B-SECRET",
            "NUM-LAB-B-SECRET",
            "ethics-LAB-B-SECRET.pdf",
            "ethics bytes of LAB-B-SECRET",
            "Notification LAB-B-SECRET",
            # --- integrations (Run 2) ---
            "External link LAB-B-SECRET",
            "outsider-LAB-B-SECRET@fake.test",
            # --- admin area (Run 4) ---
            "Resource LAB-B-SECRET",
            "Onboarding LAB-B-SECRET",
            "Inventory LAB-B-SECRET",
            "Reagent LAB-B-SECRET",
            "Protocol LAB-B-SECRET",
            "Order LAB-B-SECRET",
            "Lab chat LAB-B-SECRET",
            "Event LAB-B-SECRET",
            # --- training (Run 5) ---
            "Training LAB-B-SECRET",
            "Training free LAB-B-SECRET",
            "Notes LAB-B-SECRET",
            "cert-LAB-B-SECRET.pdf",
            "cert bytes of LAB-B-SECRET",
            "Paper LAB-B-SECRET",
            "Paper note LAB-B-SECRET",
            "paper-LAB-B-SECRET.pdf",
            "AI grant LAB-B-SECRET",  # AI access (Run 5)
            "Chat LAB-B-SECRET",  # in-app assistant (Run 5)
            "Question LAB-B-SECRET",
        ],
    )


# --- documents/attachments (Phase 3) ---
@pytest.fixture(scope="session")
def matrix_lab_files(tmp_path_factory):
    """Fixture files go to a temp dir, never the real lab_files volume."""
    from django.test import override_settings

    storage = {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
        "OPTIONS": {"location": str(tmp_path_factory.mktemp("lab_files"))},
    }
    from django.conf import settings

    with override_settings(STORAGES={**settings.STORAGES, "lab_files": storage}):
        yield


# --- end documents/attachments (Phase 3) ---


@pytest.fixture(scope="session")
def world(django_db_setup, django_db_blocker, matrix_lab_files):
    """Built once per session; each test runs in a rolled-back transaction on top of it."""
    with django_db_blocker.unblock():
        yield build_world()


def client_for(persona, w):
    client = APIClient()
    if persona != "anon":
        # D194: a signed-in persona has signed in just now; consent and token creation ask for that
        sign_in(client, User.objects.get(pk=w.user_ids[persona]))
    return client


# ---------------------------------------------------------------- payloads


def _fresh_invite_for(email, w):
    """An invite in a brand-new lab, so accepting it is always valid for its addressee."""
    pi = User.objects.get(pk=w.user_ids["pi"])
    inst = Institution.objects.get(name="Matrix Institution")
    lab = Lab.objects.create(institution=inst, name=f"Fresh {next(_n)}", created_by=pi)
    inviter = User.objects.create_user(email=f"inviter{next(_n)}@example.com", password="pw")
    LabMembership.objects.create(lab=lab, user=inviter, role=LabRole.PI)  # D40: a current PI
    _, token = Invite.issue(lab=lab, email=email, role=LabRole.MEMBER, invited_by=inviter)
    return {"token": token}


# (persona user or None, world) -> a valid request body, so an allowed call returns 2xx.
PAYLOADS = {
    ("PATCH", "core:me"): lambda user, w: {"display_name": "New Name"},
    ("POST", "core:login-methods"): lambda user, w: {"email": "someone@example.com"},
    ("POST", "labs:lab-list"): lambda user, w: {"name": "Brand New Lab"},
    ("POST", "labs:getting-started"): lambda user, w: {"dismissed": True},
    ("POST", "documents:lab-document-list"): lambda user, w: {"title": "Lab manual", "content": []},
    ("PATCH", "labs:lab-detail"): lambda user, w: {"name": "Renamed Lab"},
    ("PATCH", "labs:member-detail"): lambda user, w: {"role": "viewer"},
    ("POST", "labs:invite-list"): lambda user, w: {
        "email": f"new{next(_n)}@example.com",
        "role": "member",
    },
    ("POST", "labs:invite-preview"): lambda user, w: _fresh_invite_for("someone@example.com", w),
    ("POST", "labs:invite-accept"): lambda user, w: _fresh_invite_for(
        user.email if user else "nobody@example.com", w
    ),
    # --- projects/tasks (Phase 3) ---
    ("POST", "projects:project-list"): lambda user, w: {"name": "New Project"},
    ("PATCH", "projects:project-detail"): lambda user, w: {"description": "Edited"},
    ("POST", "projects:projectmember-list"): lambda user, w: {
        "user": str(w.user_ids["nonproj"]),  # a lab member not yet on P1
        "role": "viewer",
    },
    ("PATCH", "projects:projectmember-detail"): lambda user, w: {"role": "viewer"},
    ("POST", "projects:deadline-list"): lambda user, w: {"title": "New", "due_date": "2031-02-03"},
    ("PATCH", "projects:deadline-detail"): lambda user, w: {"done": True},
    ("POST", "projects:task-list"): lambda user, w: {
        "title": "New task",
        "assignee": str(w.user_ids["contrib"]),  # on P1, so allowed
    },
    ("PATCH", "projects:task-detail"): lambda user, w: {"status": "in_progress", "position": 0},
    ("POST", "projects:chatmessage-list"): lambda user, w: {"body": "Hello"},
    ("POST", "projects:chatmessage-read"): lambda user, w: {"last_read_at": "2030-01-01T00:00:00Z"},
    ("POST", "projects:taskpost-list"): lambda user, w: {"body": "An update"},
    ("PATCH", "projects:taskpost-detail"): lambda user, w: {"body": "Edited update"},
    ("POST", "projects:task-document-add"): lambda user, w: {"id": str(w.a["document_id"])},
    ("POST", "projects:task-attachment-add"): lambda user, w: {"id": str(w.a["attachment_id"])},
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3) ---
    ("POST", "documents:document-list"): lambda user, w: {
        "title": "New doc",
        "content": [{"type": "paragraph"}],
    },
    # fixture document is at version 2 (created, then saved once); each case is rolled back
    ("PUT", "documents:document-detail"): lambda user, w: {
        "title": "Edited",
        "content": [{"type": "paragraph"}],
        "base_version": 2,
    },
    ("POST", "documents:revision-restore"): lambda user, w: {},
    ("POST", "documents:attachment-list"): lambda user, w: {
        "file": SimpleUploadedFile("up.pdf", b"%PDF-1.4 upload", content_type="application/pdf"),
        "acknowledged_notice": "true",
    },
    ("POST", "documents:document-move"): lambda user, w: {"folder": None},
    ("POST", "documents:attachment-move"): lambda user, w: {"folder": None},
    ("POST", "documents:folder-list"): lambda user, w: {"name": "New folder"},
    ("PATCH", "documents:folder-detail"): lambda user, w: {"name": "Renamed folder"},
    # --- end documents/attachments (Phase 3) ---
    # --- provenance (Phase 4): links point at Lab A / P1 fixtures, so allowed calls return 2xx ---
    ("POST", "provenance:dataset-list"): lambda user, w: {
        "name": "New dataset",
        "version_label": "v9",
        "location_url": "https://example.com/data",
        "checksum": "sha256:" + "ab" * 32,
    },
    ("PATCH", "provenance:dataset-detail"): lambda user, w: {"access_notes": "Edited"},
    ("POST", "provenance:analysis-list"): lambda user, w: {
        "title": "New analysis",
        "code_repo_url": "https://example.com/repo.git",
        "code_commit": "abc1234",
        "datasets": [str(w.a["datasetrecord_id"])],
    },
    ("PATCH", "provenance:analysis-detail"): lambda user, w: {"description": "Edited"},
    ("POST", "provenance:result-list"): lambda user, w: {
        "title": "New result",
        "analysis": str(w.a["analysis_id"]),
    },
    ("PATCH", "provenance:result-detail"): lambda user, w: {"summary": "Edited"},
    ("POST", "provenance:decision-list"): lambda user, w: {
        "title": "New decision",
        "analyses": [str(w.a["analysis_id"])],
        "supporting_documents": [str(w.a["document_id"])],
    },
    ("PATCH", "provenance:decision-detail"): lambda user, w: {"rationale": "Edited"},
    ("POST", "provenance:manuscript-list"): lambda user, w: {
        "title": "New manuscript",
        "url": "https://www.overleaf.com/project/abc",
        "results": [str(w.a["result_id"])],
    },
    ("PATCH", "provenance:manuscript-detail"): lambda user, w: {"status": "submitted"},
    # --- workflow (Run 4) ---
    ("POST", "provenance:funding-list"): lambda user, w: {
        "funder": "NSERC",
        "program": "Discovery",
        "status": "applied",
        "holder": str(user.pk) if user else None,
        "attachment": str(w.a["attachment_id"]),
    },
    ("PATCH", "provenance:funding-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "provenance:review-list"): lambda user, w: {
        "title": "Sign-off",
        "reviewer": str(user.pk) if user else None,
        "status": "requested",
    },
    ("PATCH", "provenance:review-detail"): lambda user, w: {"status": "approved"},
    ("POST", "provenance:recruitment-list"): lambda user, w: {
        "entry_date": "2030-02-01",
        "status": "enrolled",
        "count": 2,
    },
    ("PATCH", "provenance:recruitment-detail"): lambda user, w: {"count": 5},
    ("PATCH", "provenance:recruitment-plan"): lambda user, w: {"target_enrolment": 40},
    ("POST", "provenance:result-set"): lambda user, w: {
        "analysis": str(w.a["analysis_id"]),
        "items": [{"title": "Figure 1"}, {"title": "Figure 2"}],
    },
    ("POST", "provenance:external-list"): lambda user, w: {
        "title": "Poster",
        "type": "poster",
        "date": "2030-02-01",
        "attachment": str(w.a["attachment_id"]),
    },
    ("PATCH", "provenance:external-detail"): lambda user, w: {"place": "Halifax"},
    ("PATCH", "provenance:workflow-progress"): lambda user, w: {"stage": "ethics", "done": True},
    ("PATCH", "provenance:dmp"): lambda user, w: {"storage": "Edited"},
    ("POST", "provenance:dmp-approve"): lambda user, w: {},
    # --- end workflow (Run 4) ---
    ("POST", "provenance:export"): lambda user, w: {},
    # --- end provenance (Phase 4) ---
    # --- ethics and notifications (Phase 5) ---
    ("POST", "ethics:approval-list"): lambda user, w: {
        "approval_number": f"N-{next(_n)}",
        "board": "Board Y",
        "title": "New approval",
        "approval_date": "2030-01-01",
        "expiry_date": "2031-01-01",
    },
    ("PATCH", "ethics:approval-detail"): lambda user, w: {"title": "Edited approval"},
    ("POST", "ethics:approval-attachments"): lambda user, w: {
        "file": SimpleUploadedFile("up.pdf", b"%PDF-1.4 upload", content_type="application/pdf"),
        "acknowledged_notice": "true",
    },
    ("POST", "core:notification-read"): lambda user, w: {},
    ("POST", "core:notification-read-all"): lambda user, w: {},
    # --- integrations (Run 2): pi, admin, lead and contrib each hold an active fake account ---
    ("POST", "integrations:connect"): lambda user, w: {},
    ("POST", "integrations:external-link-check"): lambda user, w: {},
    ("POST", "integrations:import-tasks"): lambda user, w: {"source": "s1"},  # D240
    ("POST", "integrations:webhook-list"): lambda user, w: {  # D241
        "name": "Zap",
        "kind": "webhook",
        "url": "https://hooks.example.org/x",
        "events": ["project.created"],
    },
    ("PATCH", "integrations:webhook-detail"): lambda user, w: {"name": "Renamed"},
    ("POST", "integrations:webhook-test"): lambda user, w: {},
    ("POST", "papers:zotero-import"): lambda user, w: {"ids": ["u1:ABCD2345"]},  # D242
    ("POST", "integrations:external-link-accept-change"): lambda user, w: {},
    ("POST", "integrations:external-link-list"): lambda user, w: {
        "provider": "fake",
        "external_id": f"file-{next(_n)}",
    },
    # --- end ethics and notifications (Phase 5) ---
    # --- admin area (Run 4) ---
    ("POST", "labs:resource-load-starters"): lambda user, w: {},
    ("POST", "labs:resource-list"): lambda user, w: {
        "category": "ethics",
        "title": "New resource",
        "url": f"https://example.edu/new-{next(_n)}",
    },
    ("PATCH", "labs:resource-detail"): lambda user, w: {"title": "Edited resource"},
    ("POST", "labs:onboarding-list"): lambda user, w: {"kind": "new_member", "title": "New item"},
    ("PATCH", "labs:onboarding-detail"): lambda user, w: {"required": False},
    ("POST", "labs:onboarding-completion"): lambda user, w: {
        "user": str(w.user_ids["contrib"]),
        "done": True,
    },
    ("POST", "labs:inventory-list"): lambda user, w: {"name": "New item", "category": "reagent"},
    ("POST", "labs:inventory-import"): lambda user, w: {
        "file": SimpleUploadedFile("i.csv", b"Name,Category\nFlask,equipment\n", "text/csv"),
        "commit": "true",
    },
    ("POST", "labs:protocol-list"): lambda user, w: {"name": "New protocol"},
    ("PATCH", "labs:protocol-detail"): lambda user, w: {"name": "Renamed"},
    ("POST", "labs:protocol-use"): lambda user, w: {
        "reagent": w.a["reagent_id"],
        "request_id": str(uuid.uuid4()),
    },
    ("POST", "labs:inventory-usage-reverse"): lambda user, w: {},
    ("PATCH", "labs:inventory-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "labs:order-list"): lambda user, w: {"name": "New order", "quantity": "2"},
    ("PATCH", "labs:order-detail"): lambda user, w: {"status": "ordered"},
    # --- end admin area (Run 4) ---
    # --- lab chat and calendar (GET payloads are query strings) ---
    ("POST", "labs:labchat-list"): lambda user, w: {"body": "Hello"},
    ("POST", "labs:labchat-read"): lambda user, w: {"last_read_at": "2030-01-01T00:00:00Z"},
    ("GET", "labs:calendar"): lambda user, w: {"from": "2030-01-01", "to": "2030-01-31"},
    ("POST", "labs:labevent-list"): lambda user, w: {"title": "New", "date": "2030-02-01"},
    ("PATCH", "labs:labevent-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "labs:meeting-list"): lambda user, w: {
        "title": "New",
        "starts_at": "2030-02-01T10:00:00Z",
        "ends_at": "2030-02-01T11:00:00Z",
    },
    ("PATCH", "labs:meeting-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "labs:calendar-feed"): lambda user, w: {},
    ("PATCH", "labs:calendar-google"): lambda user, w: {"push_tasks": False},
    ("POST", "labs:calendar-google-sync"): lambda user, w: {},
    ("GET", "labs:calendar-google-events"): lambda user, w: {
        "from": "2030-01-01",
        "to": "2030-01-31",
    },
    ("GET", "labs:calendar-ics"): lambda user, w: (
        {"token": CalendarFeedToken.issue(lab=Lab.objects.get(pk=w.a["lab_id"]), user=user)[1]}
        if user
        else {}
    ),
    # --- end lab chat and calendar ---
    # --- training (Run 5) ---
    ("POST", "training:requirement-list"): lambda user, w: {
        "name": f"New training {next(_n)}",
        "category": "safety",
        "validity_months": 12,
    },
    ("PATCH", "training:requirement-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "training:record-list"): lambda user, w: {
        "requirement": str(w.a["trainingrequirement_id"]),
        "completed_on": "2030-03-01",
    },
    ("PATCH", "training:record-detail"): lambda user, w: {"notes": "Edited"},
    ("POST", "training:record-verify"): lambda user, w: {},
    ("POST", "training:record-certificate"): lambda user, w: {
        "file": SimpleUploadedFile("up.pdf", b"%PDF-1.4 upload", content_type="application/pdf"),
        "acknowledged_notice": "true",
    },
    # --- end training (Run 5) ---
    # --- paper library ---
    ("POST", "papers:paper-list"): lambda user, w: {"title": f"New paper {next(_n)}"},
    ("PATCH", "papers:paper-detail"): lambda user, w: {"venue": "Edited"},
    ("POST", "papers:paper-pdf"): lambda user, w: {
        "file": SimpleUploadedFile("up.pdf", b"%PDF-1.4 upload", content_type="application/pdf"),
        "acknowledged_notice": "true",
    },
    ("POST", "papers:paper-notes"): lambda user, w: {"body": "New note"},
    ("PATCH", "papers:note-detail"): lambda user, w: {"body": "Edited"},
    # --- end paper library ---
    # --- AI access (Run 5) ---
    ("POST", "assistant:authorize"): _ai_consent,
    ("POST", "assistant:grant-list"): lambda user, w: {
        "name": "Matrix token",
        "labs": [_ai_lab(user, w)],
        "access": "read",
        "expires_in_days": 7,
    },
    # --- end AI access (Run 5) ---
    # --- in-app assistant (Run 5) ---
    ("PUT", "assistant:key-detail"): lambda user, w: {
        "api_key": "sk-ant-api03-matrix-key-abcdefghijklmnop"
    },
    ("PATCH", "assistant:key-detail"): lambda user, w: {"refusal_fallback": True},
    ("PATCH", "assistant:ai-policy"): lambda user, w: {"ai_policy": "full"},
    ("POST", "assistant:conversation-list"): lambda user, w: {"provider": "anthropic"},
    ("POST", "assistant:conversation-message"): lambda user, w: {"text": "Hello"},
    ("POST", "assistant:conversation-approval"): lambda user, w: {
        "decisions": {"toolu_matrix": True}
    },
    # --- end in-app assistant (Run 5) ---
}


# ---------------------------------------------------------------- enumeration


def discover():
    """Walk the URL resolver: {(METHOD, url_name): (url kwarg names)}."""
    found = {}

    def walk(patterns, prefix, ns, kwargs):
        for p in patterns:
            route = prefix + str(p.pattern)
            if any(("/" + route).startswith(x) for x in EXEMPT_PREFIXES):
                continue
            if isinstance(p, URLResolver):
                sub_ns = ns + (p.namespace + ":" if p.namespace else "")
                walk(p.url_patterns, route, sub_ns, kwargs + tuple(p.pattern.converters))
                continue
            assert isinstance(p, URLPattern)
            cb = p.callback
            if hasattr(cb, "actions"):  # ViewSet
                methods = [m.upper() for m in cb.actions]
            else:
                cls = getattr(cb, "cls", None)
                assert cls is not None, f"{route}: not a DRF view; exempt it or convert it"
                methods = [
                    m.upper()
                    for m in cls.http_method_names
                    if m not in ("head", "options") and hasattr(cls, m)
                ]
            assert p.name, f"{route}: URL has no name"
            for m in methods:
                found[(m, ns + p.name)] = kwargs + tuple(p.pattern.converters)

    walk(get_resolver().url_patterns, "", "", ())
    return found


def test_every_endpoint_has_a_matrix_row():
    missing = sorted(discover().keys() - MATRIX.keys())
    assert not missing, f"endpoints with no MATRIX row: {missing}"


def test_no_stale_matrix_rows():
    stale = sorted(MATRIX.keys() - discover().keys())
    assert not stale, f"MATRIX rows with no endpoint: {stale}"


def test_matrix_rows_are_well_formed():
    for key, row in MATRIX.items():
        tokens = row.split()
        assert len(tokens) == len(PERSONAS), key
        assert set(tokens) <= {"2", "302", "401", "403", "404"}, key  # 302: OAuth callback
        assert tokens[0] in {"2", "401"}, f"anon can only succeed or get 401: {key}"
        method, name = key
        if method in {"POST", "PATCH", "PUT"} and name != "core:health":
            assert key in PAYLOADS, f"no payload for {key}"


# ---------------------------------------------------------------- the matrix

CASES = [
    (method, name, persona, expected)
    for (method, name), row in MATRIX.items()
    for persona, expected in zip(PERSONAS, row.split(), strict=True)
]


def _request(client, method, url, payload):
    if method in {"POST", "PATCH", "PUT"}:
        payload = payload or {}
        # --- documents/attachments (Phase 3): an upload payload makes the request multipart ---
        has_file = any(hasattr(v, "read") for v in payload.values())
        for v in payload.values():
            if hasattr(v, "seek"):
                v.seek(0)  # the same payload is sent twice by the swap test
        if has_file:
            return getattr(client, method.lower())(url, payload, format="multipart")
        # --- end documents/attachments (Phase 3) ---
        return getattr(client, method.lower())(url, payload, format="json")
    if method == "GET":
        return client.get(url, payload or {})  # a GET payload is its query string
    return getattr(client, method.lower())(url)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("method", "name", "persona", "expected"),
    CASES,
    ids=[f"{m} {n} {p}" for m, n, p, _ in CASES],
)
def test_matrix(world, method, name, persona, expected):
    user = None if persona == "anon" else User.objects.get(pk=world.user_ids[persona])
    kwargs = {k: world.a[k] for k in discover()[(method, name)]}
    payload = PAYLOADS[(method, name)](user, world) if (method, name) in PAYLOADS else None
    response = _request(client_for(persona, world), method, reverse(name, kwargs=kwargs), payload)
    if expected == "2":
        assert 200 <= response.status_code < 300, (response.status_code, response.content)
    else:
        assert response.status_code == int(expected), (response.status_code, response.content)


# ---------------------------------------------------------------- cross-lab ID swap


# Not resolved at import: urls must load after pytest-django turns DEBUG off (no schema URL).
@pytest.mark.django_db
@pytest.mark.parametrize(("method", "name"), list(MATRIX), ids=[f"{m} {n}" for m, n in MATRIX])
def test_cross_lab_id_swap_is_404(world, method, name):
    """Acting as Lab A's PI: A's lab_id with B's object ID, and B's lab_id with A's object ID,
    both 404, and neither response leaks anything from Lab B."""
    if len([k for k in discover()[(method, name)] if k.endswith("_id")]) < 2:
        pytest.skip("no object ID in the URL")  # a `<provider>` slug is not an object ID
    pi = User.objects.get(pk=world.user_ids["pi"])
    client = client_for("pi", world)
    payload = PAYLOADS[(method, name)](pi, world) if (method, name) in PAYLOADS else None
    for lab_side, obj_side in [(world.a, world.b), (world.b, world.a)]:
        kwargs = {k: obj_side[k] for k in discover()[(method, name)]}
        kwargs["lab_id"] = lab_side["lab_id"]
        response = _request(client, method, reverse(name, kwargs=kwargs), payload)
        assert response.status_code == 404, (kwargs, response.status_code, response.content)
        body = response.content.decode()
        assert not any(secret in body for secret in world.b_names)


@pytest.mark.django_db
def test_options_on_lab_url_is_404_for_outsiders(world):
    url = reverse("labs:lab-detail", kwargs={"lab_id": world.a["lab_id"]})
    assert client_for("outsider", world).options(url).status_code == 404
    assert client_for("anon", world).options(url).status_code == 401
