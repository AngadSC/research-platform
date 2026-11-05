"""Permission matrix (ARCHITECTURE section 6, D32, D36). Gates every phase.

To add an endpoint in a later phase: add its model to `build_world` (for Lab A and Lab B),
its URL kwargs to `build_world().a` / `.b`, a `PAYLOADS` entry for each write method, and one
hand-written `MATRIX` row. The expected codes are never derived from the code or the role tables.
"""

import dataclasses  # integrations (Run 2)
import datetime  # integrations (Run 2)
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from django.core.files.uploadedfile import SimpleUploadedFile  # documents/attachments (Phase 3)
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from rest_framework.test import APIClient

from core.models import Institution, Notification, NotificationKind, User
from documents import services as document_services  # documents/attachments (Phase 3)
from ethics.models import EthicsApproval  # ethics (Phase 5)
from integrations import registry  # integrations (Run 2)
from integrations.models import ConnectedAccount, ExternalLink  # integrations (Run 2)
from integrations.tests.fake import FAKE  # integrations (Run 2)
from labs.models import Invite, Lab, LabMembership, LabRole
from projects.models import (  # projects/tasks (Phase 3)
    Project,
    ProjectDeadline,
    ProjectMembership,
    ProjectRole,
    Task,
)
from provenance.models import (  # provenance (Phase 4)
    Analysis,
    DatasetRecord,
    Decision,
    ManuscriptLink,
    Result,
)

# Fixed order. Lab roles: outsider is the PI of Lab B and not in Lab A; pi, admin (lab_admin),
# lead, contrib, pviewer and nonproj (members); lviewer is a lab viewer. Project roles on P1:
# lead, contrib, pviewer; nonproj has none; lviewer is a contributor, capped to viewer (D19).
PERSONAS = ["anon", "outsider", "pi", "admin", "lead", "contrib", "pviewer", "nonproj", "lviewer"]

# Each exemption needs a reason.
EXEMPT_PREFIXES = [
    "/_allauth/",  # allauth headless: its own views, covered by core/tests/test_auth.py
    "/accounts/",  # allauth OAuth provider callbacks, covered by core/tests/test_google_auth.py
    "/admin/",  # Django admin: staff only, not part of the API
    "/healthz",  # load-balancer probe: checks only, no data (core/tests/test_healthz.py)
]

# fmt: off
MATRIX: dict[tuple[str, str], str] = {
    #                                    anon outsider pi admin lead contrib pviewer nonproj lviewer
    ("GET",    "core:health"):           "2   2        2  2     2    2       2       2       2",
    ("GET",    "core:me"):               "401 2        2  2     2    2       2       2       2",
    ("PATCH",  "core:me"):               "401 2        2  2     2    2       2       2       2",
    ("GET",    "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("POST",   "labs:lab-list"):         "401 2        2  2     2    2       2       2       2",
    ("GET",    "labs:lab-detail"):       "401 404      2  2     2    2       2       2       2",
    ("PATCH",  "labs:lab-detail"):       "401 404      2  2     403  403     403     403     403",
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
    ("GET", "projects:task-list"): "401 404 2 2 2 2 2 404 2",
    ("POST", "projects:task-list"): "401 404 2 2 2 2 403 404 403",
    ("GET", "projects:task-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH", "projects:task-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "projects:task-detail"): "401 404 2 2 2 2 403 404 403",
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3) ---
    # Reasoned per persona on P1: reads need view_project (everyone on P1, including the
    # lab viewer capped to viewer, D19); writes need edit_content (lead, contrib, and the implicit
    # leads pi/admin; pviewer and lviewer get 403). nonproj is not on P1, so every P1 object is
    # invisible to them: 404 (D21). outsider is in no Lab A role: 404. Attachment delete is
    # edit_content, not edit_project, so contrib may delete. Download needs only view_project.
    ("GET",    "documents:document-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "documents:document-list"): "401 404 2 2 2 2 403 404 403",
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
    ("GET",    "provenance:manuscript-list"): "401 404 2 2 2 2 2 404 2",
    ("POST",   "provenance:manuscript-list"): "401 404 2 2 2 2 403 404 403",
    ("GET",    "provenance:manuscript-detail"): "401 404 2 2 2 2 2 404 2",
    ("PATCH",  "provenance:manuscript-detail"): "401 404 2 2 2 2 403 404 403",
    ("DELETE", "provenance:manuscript-detail"): "401 404 2 2 2 2 403 404 403",
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
    # --- end integrations (Run 2) ---
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
    return {
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

    monkeypatch.setitem(
        registry.PROVIDERS, "fake", dataclasses.replace(FAKE, fetch_item=fetch_item)
    )
    settings.INTEGRATION_CLIENTS = {
        **settings.INTEGRATION_CLIENTS,
        "fake": {"client_id": "fake-client", "client_secret": "fake-secret"},
    }


# --- end integrations (Run 2) ---


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
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3): Lab A fixtures ---
    doc_a, attachment_a = _doc_fixtures(lab_a, p1, users["pi"], "lab-a")
    # --- end documents/attachments (Phase 3) ---
    prov_a = _prov_fixtures(lab_a, p1, users["pi"], doc_a, attachment_a, "lab-a")  # Phase 4
    eth_a, eth_att_a, note_a = _ethics_fixtures(lab_a, p1, users["pi"], "lab-a")  # Phase 5
    int_accounts_a, link_a = _integration_fixtures(
        lab_a, p1, {n: users[n] for n in ("pi", "admin", "lead", "contrib")}, "lab-a"
    )  # integrations (Run 2)
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
    # --- end projects/tasks (Phase 3) ---
    # --- documents/attachments (Phase 3): Lab B mirror ---
    doc_b, attachment_b = _doc_fixtures(lab_b, p1_b, secret_pi, "LAB-B-SECRET")
    # --- end documents/attachments (Phase 3) ---
    prov_b = _prov_fixtures(lab_b, p1_b, secret_pi, doc_b, attachment_b, "LAB-B-SECRET")  # Ph. 4
    eth_b, eth_att_b, note_b = _ethics_fixtures(lab_b, p1_b, secret_pi, "LAB-B-SECRET")  # Phase 5
    int_accounts_b, link_b = _integration_fixtures(
        lab_b, p1_b, {"outsider": secret_pi}, "LAB-B-SECRET"
    )  # integrations (Run 2)
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
            # --- documents/attachments (Phase 3) ---
            "document_id": doc_a.pk,
            "version": 1,
            "attachment_id": attachment_a.pk,
            **prov_a,  # provenance (Phase 4)
            "ethicsapproval_id": eth_a.pk,  # ethics and notifications (Phase 5)
            "notification_id": note_a.pk,
            "ethics_attachment_id": eth_att_a.pk,  # not a URL kwarg: ethics download test
            "provider": "fake",  # integrations (Run 2)
            "connectedaccount_id": int_accounts_a["contrib"].pk,
            "externallink_id": link_a.pk,
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
            # --- documents/attachments (Phase 3) ---
            "document_id": doc_b.pk,
            "version": 1,
            "attachment_id": attachment_b.pk,
            **prov_b,  # provenance (Phase 4)
            "ethicsapproval_id": eth_b.pk,  # ethics and notifications (Phase 5)
            "notification_id": note_b.pk,
            "ethics_attachment_id": eth_att_b.pk,
            "provider": "fake",  # integrations (Run 2)
            "connectedaccount_id": int_accounts_b["outsider"].pk,
            "externallink_id": link_b.pk,
        },
        b_names=[
            "Lab B Secret",
            "P1 Secret",
            "invitee-b-secret@example.com",
            "Task B Secret",  # projects/tasks (Phase 3)
            "Deadline B Secret",
            # --- documents/attachments (Phase 3): titles, filename and the file's bytes ---
            "Doc LAB-B-SECRET",
            "file-LAB-B-SECRET.pdf",
            "bytes of LAB-B-SECRET",
            # --- provenance (Phase 4): every title and the repo URL carry the tag ---
            "Dataset LAB-B-SECRET",
            "Analysis LAB-B-SECRET",
            "Analysis free LAB-B-SECRET",
            "Result LAB-B-SECRET",
            "Decision LAB-B-SECRET",
            "Manuscript LAB-B-SECRET",
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
        client.force_login(User.objects.get(pk=w.user_ids[persona]))
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
    ("POST", "labs:lab-list"): lambda user, w: {"name": "Brand New Lab"},
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
    ("POST", "integrations:external-link-list"): lambda user, w: {
        "provider": "fake",
        "external_id": f"file-{next(_n)}",
    },
    # --- end ethics and notifications (Phase 5) ---
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
