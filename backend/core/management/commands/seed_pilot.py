"""Fill a dev database with obviously fake pilot data (D46). Objects go through the service
layer. Users, lab memberships and email addresses have no service, so they are created
directly. Re-running is a no-op once the seed lab exists."""

import base64
import datetime

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import User
from documents.services import create_document, save_document, upload_attachment
from ethics import services as ethics_services
from ethics.models import EthicsApproval
from labs.models import Lab, LabMembership, LabRole
from labs.services import create_lab
from projects import services as project_services
from projects.models import ProjectRole, TaskStatus
from provenance import services as prov

LAB_NAME = "Example Cognition Lab (FAKE)"
PASSWORD = "seed-password-not-secret"  # noqa: S105 (dev-only, printed on purpose)
FRONTEND_URL = "http://localhost:5173"
APPROVAL_NUMBER = "FAKE-IRB-2026-001"
FAKE_COMMIT = "3f2c9a1e7b4d" + "0" * 28  # 40 hex characters, visibly padded

# Smallest valid 1x1 PNG.
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def make_pdf() -> bytes:
    """A one-page PDF with a correct xref table."""
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    ]
    body, offsets = b"%PDF-1.4\n", []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(body))
        body += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    body += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return body


def block(kind, text, **props):
    return {
        "type": kind,
        "props": props,
        "content": [{"type": "text", "text": text, "styles": {}}],
        "children": [],
    }


class Command(BaseCommand):
    help = "Seed a dev database with fake pilot data (only when DEBUG is on)."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_pilot only runs with DEBUG=True.")
        if Lab.objects.filter(name=LAB_NAME).exists():
            self.stdout.write(f"Seed lab already exists ({LAB_NAME}); nothing to do.")
        else:
            with transaction.atomic():
                self.seed()
            self.stdout.write("Seeded pilot data.")
        self.summary()

    def make_user(self, email, display_name, lab=None, role=None):
        user = User.objects.create_user(email=email, password=PASSWORD, display_name=display_name)
        EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        if lab is not None:
            LabMembership.objects.create(lab=lab, user=user, role=role)
        return user

    def seed(self):
        today = timezone.localdate()

        # The PI is created first; create_lab adds their PI membership.
        pi = self.make_user("pi@example.test", "Pat Example (PI)")
        lab = create_lab(user=pi, name=LAB_NAME)
        self.make_user("admin@example.test", "Alex Admin (FAKE)", lab, LabRole.LAB_ADMIN)
        lead = self.make_user("lead@example.test", "Lee Lead (FAKE)", lab, LabRole.MEMBER)
        student = self.make_user("student@example.test", "Sam Student (FAKE)", lab, LabRole.MEMBER)
        viewer = self.make_user("viewer@example.test", "Vic Viewer (FAKE)", lab, LabRole.VIEWER)

        project = project_services.create_project(
            lab=lab,
            user=lead,
            data={
                "name": "Pilot Attention Study (FAKE)",
                "description": "Fake study data.",
                "status": "active",
            },
        )
        project_services.add_member(
            project=project, by=pi, user_id=student.pk, role=ProjectRole.CONTRIBUTOR
        )
        # So a demo login as the lab viewer sees the pilot project (read only).
        project_services.add_member(
            project=project, by=pi, user_id=viewer.pk, role=ProjectRole.VIEWER
        )
        for title, status, assignee, days in [
            ("Draft consent wording (FAKE)", TaskStatus.DONE, lead, -10),
            ("Recruit 12 participants (FAKE)", TaskStatus.IN_PROGRESS, student, 5),
            ("Clean RT export (FAKE)", TaskStatus.IN_PROGRESS, student, 9),
            ("Fit primary RT model (FAKE)", TaskStatus.TODO, student, 20),
            ("Write results section (FAKE)", TaskStatus.TODO, None, 30),
            ("Plan follow-up sample (FAKE)", TaskStatus.TODO, lead, 45),
        ]:
            project_services.create_task(
                project=project,
                by=lead,
                data={
                    "title": title,
                    "status": status,
                    "assignee": assignee.pk if assignee else None,
                    "due_date": today + datetime.timedelta(days=days),
                },
            )
        for author, body in [
            (lead, "Welcome to the project chat. Use it for quick questions (FAKE)."),
            (student, "RT export is cleaned. Fitting the primary model next (FAKE)."),
            (lead, "Great. Please link the result when it is ready (FAKE)."),
        ]:
            project_services.post_message(project=project, by=author, body=body)
        for title, days in [("Pilot data freeze (FAKE)", 21), ("Ethics check-in (FAKE)", 60)]:
            project_services.create_deadline(
                project=project,
                data={"title": title, "due_date": today + datetime.timedelta(days=days)},
            )

        # The protocol is edited twice after creation, so it ends with three revisions.
        protocol = create_document(
            project=project,
            user=lead,
            title="Study protocol draft (FAKE)",
            content=[
                block("heading", "Study protocol (FAKE)", level=1),
                block("paragraph", "Fake placeholder text for a dev database."),
            ],
        )
        for text in ["Second version, still fake.", "Third version, still fake."]:
            protocol = save_document(
                protocol,
                title=protocol.title,
                content=[
                    block("heading", "Study protocol (FAKE)", level=1),
                    block("paragraph", text),
                ],
                base_version=protocol.version,
                user=lead,
            )
        notes = create_document(
            project=project,
            user=student,
            title="Meeting notes (FAKE)",
            content=[
                block("heading", "Meeting notes (FAKE)", level=2),
                block("paragraph", "Fake notes: nothing happened here."),
            ],
        )
        # Past its retention date, so the PI review list and the retention job have an item.
        save_document(
            notes,
            title=notes.title,
            content=notes.content,
            base_version=notes.version,
            user=pi,
            retain_until=today - datetime.timedelta(days=30),
            retention_note="Fake policy: keep 5 years after study close (FAKE).",
        )
        upload_attachment(
            project=project,
            user=lead,
            file=SimpleUploadedFile(
                "fake-protocol.pdf", make_pdf(), content_type="application/pdf"
            ),
        )

        # Provenance chain: dataset v1 -> v2 -> analysis -> result -> manuscript, plus a decision.
        dataset = {
            "name": "Attention task responses (FAKE)",
            "location_text": "Institutional secure drive (FAKE)",
            "location_url": "https://example.test/data/attention-responses",
            "controlled_by": lead.pk,
            "access_notes": "Fake access note: the lead approves all requests.",
        }
        v1 = prov.create(
            "dataset",
            project=project,
            user=lead,
            data={**dataset, "version_label": "v1", "checksum": "sha256:" + "ab12" * 16},
        )
        v2 = prov.create(
            "dataset",
            project=project,
            user=lead,
            data={
                **dataset,
                "version_label": "v2",
                "previous_version": v1.pk,
                "checksum": "sha256:" + "cd34" * 16,
            },
        )
        analysis = prov.create(
            "analysis",
            project=project,
            user=student,
            data={
                "title": "Primary RT model (FAKE)",
                "description": "Fake mixed model of reaction times.",
                "code_repo_url": "https://example.test/git/attention-analysis",
                "code_commit": FAKE_COMMIT,
                "datasets": [v2.pk],
                "ran_by": student.pk,
            },
        )
        figure = upload_attachment(
            project=project,
            user=student,
            file=SimpleUploadedFile("fake-figure.png", PNG_BYTES, content_type="image/png"),
        )
        result = prov.create(
            "result",
            project=project,
            user=student,
            data={
                "title": "Reaction time effect (FAKE)",
                "summary": "Fake summary: an invented effect.",
                "analysis": analysis.pk,
                "attachments": [figure.pk],
            },
        )
        prov.create(
            "manuscript",
            project=project,
            user=lead,
            data={
                "title": "Attention and response speed (draft, FAKE)",
                "url": "https://example.test/overleaf/fake",
                "status": "drafting",
                "results": [result.pk],
            },
        )
        prov.create(
            "decision",
            project=project,
            user=lead,
            data={
                "title": "Exclude trials under 200 ms (FAKE)",
                "rationale": "Fake rationale: implausibly fast responses.",
                "decided_on": today,
                "analyses": [analysis.pk],
                "supporting_documents": [protocol.pk],
            },
        )

        # Expires in 25 days, so the 30-day reminder is due (reminders: run the job, see summary).
        ethics_services.create_approval(
            lab=lab,
            user=lead,
            data={
                "approval_number": APPROVAL_NUMBER,
                "board": "Example IRB (FAKE)",
                "title": "Pilot attention study approval (FAKE)",
                "approval_date": today - datetime.timedelta(days=340),
                "expiry_date": today + datetime.timedelta(days=25),
                "status": "active",
                "projects": [project.pk],
            },
        )

        # Archived project with the student as its only lead (the handover "no other owner" case).
        archived = project_services.create_project(
            lab=lab,
            user=student,
            data={
                "name": "Archived Survey (FAKE)",
                "description": "Fake archived survey.",
                "status": "archived",
            },
        )
        project_services.update_project(  # D55: only the PI sets retention
            project=archived,
            user=pi,
            data={
                "retain_until": today - datetime.timedelta(days=60),
                "retention_note": "Fake policy: review after archive (FAKE).",
            },
        )
        create_document(
            project=archived,
            user=student,
            title="Survey items (FAKE)",
            content=[block("paragraph", "Fake survey item text.")],
        )

    def summary(self):
        self.stdout.write(f"Frontend: {FRONTEND_URL}")
        self.stdout.write(f"Password: {PASSWORD}")
        self.stdout.write("Logins (all share the password above):")
        for email, role in [
            ("pi@example.test", "pi"),
            ("admin@example.test", "lab_admin"),
            ("lead@example.test", "member, project lead"),
            ("student@example.test", "member, departing student"),
            ("viewer@example.test", "viewer, read-only on the pilot project"),
        ]:
            self.stdout.write(f"  {email}  ({role})")
        lab = Lab.objects.filter(name=LAB_NAME).first()
        approval = (
            lab
            and EthicsApproval.objects.for_lab(lab).filter(approval_number=APPROVAL_NUMBER).first()
        )
        if approval:
            self.stdout.write(
                f"Ethics approval: {approval.approval_number} ({approval.board}), "
                f"expires {approval.expiry_date} "
                f"({(approval.expiry_date - timezone.localdate()).days} days)"
            )
