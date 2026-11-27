"""A fake glycobiology lab for the wet-lab demo (.night/WETLAB.md): people, a project, inventory
with reagent lots, instruments with parsed demo files, and freezer sensors. Everything is made up
and every address is @example.test. Safe to run twice: what exists is kept, what is missing is
added, and the logins are reset to the demo password.

Like seed_pilot, it runs only with DEBUG on or QA_PASSWORD set."""

import os
from pathlib import Path

from allauth.account.models import EmailAddress
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

import instrument_parsers
from core.models import User
from instruments import demo as instruments_demo
from instruments.jobs import parse_instrument_file
from instruments.models import InstrumentFile, UploadedVia
from instruments.services import drop_file
from labs import demo_lots
from labs.models import InventoryItem, Lab, LabMembership, LabRole
from labs.services import create_lab
from monitoring import demo as monitoring_demo
from projects import services as project_services
from projects.models import Project, ProjectMembership, ProjectRole
from samples import demo as samples_demo
from samples import services as sample_services
from samples.models import Sample

LAB_NAME = "Glycoenzyme Demo Lab"
PROJECT_NAME = "Sialyltransferase engineering"
PASSWORD = "wetlab-demo-not-secret"  # noqa: S105 (demo-only, printed on purpose)
# key, email, display name, lab role, project role (None: not on the project)
PEOPLE = [
    ("pi", "glyco-pi@example.test", "Dr. Robin Example (FAKE PI)", LabRole.PI, None),
    ("admin", "glyco-admin@example.test", "Alex Manager (FAKE)", LabRole.LAB_ADMIN, None),
    ("lead", "glyco-postdoc@example.test", "Jordan Postdoc (FAKE)", LabRole.MEMBER, "lead"),
    (
        "student",
        "glyco-student@example.test",
        "Casey Student (FAKE)",
        LabRole.MEMBER,
        ProjectRole.CONTRIBUTOR,
    ),
    ("viewer", "glyco-viewer@example.test", "Taylor Visitor (FAKE)", LabRole.VIEWER, None),
]
DEMO_FILES = Path(instrument_parsers.__file__).parent / "demo_files"
# demo file -> the demo instrument (instruments/demo.py) it is dropped on
FILES = {
    "gen5_sialyltransferase_phosphate_assay.txt": "Plate reader (Synergy H1)",
    "nanodrop_purified_MBP_ST6GAL1.txt": "NanoDrop 8000",
    "unicorn_MBP_ST6GAL1_NiNTA_run.zip": "ÄKTA pure 25",
    "gel_SDS_PAGE_MBP_ST6GAL1_16bit.tif": "Gel imager (ChemiDoc)",
    "cfx_ST6GAL1_knockdown_cq.csv": "qPCR (CFX Opus 96)",
    "sanger_ST6GAL1_insert_T7.ab1": "Sanger sequencing (DNA core)",
}


# A made-up, very short GenBank record: not a real sequence.
PLASMID_MAP = """LOCUS       pCW-MalE-CST06          60 bp    DNA     circular SYN 24-NOV-2026
DEFINITION  Fake demo plasmid: MBP-tagged CST-06 sialyltransferase (not a real map).
FEATURES             Location/Qualifiers
     CDS             1..30
                     /label="MalE (MBP)"
     CDS             31..54
                     /label="CST-06"
ORIGIN
        1 atgaaaatcg aagaaggtaa actggtaatc tgggctgaca acaccgcatt ctaaggatcc
//
"""


class Command(BaseCommand):
    help = "Seed a fake glycobiology lab for the wet-lab demo (only when DEBUG is on)."

    def handle(self, *args, **options):
        qa_password = os.environ.get("QA_PASSWORD", "")
        if not settings.DEBUG and not qa_password:
            raise CommandError("seed_wetlab_demo runs with DEBUG=True, or with QA_PASSWORD set.")
        self.password = qa_password or PASSWORD
        with transaction.atomic():
            lab, users = self.people()
            project = self.project(lab, users)
            lab.inventory_enabled = True
            lab.save(update_fields=["inventory_enabled"])
            demo_lots.seed(lab, users)
            instruments_demo.seed(lab, users)
            monitoring_demo.seed(lab, users)
            samples_demo.seed(lab, users)
        self.drop_files(lab, project, users["lead"])
        self.link_batch(lab, project)
        self.link_plasmid(lab, project, users["lead"])
        self.summary(lab)

    def user(self, email, name):
        user = User.objects.filter(email=email).first()
        if user is None:
            user = User.objects.create_user(email=email, password=self.password, display_name=name)
            EmailAddress.objects.create(user=user, email=email, verified=True, primary=True)
        else:  # a known password every run, and no two-step setup, as in seed_pilot
            from allauth.mfa.models import Authenticator

            user.set_password(self.password)
            user.save(update_fields=["password"])
            Authenticator.objects.filter(user=user).delete()
        return user

    def people(self):
        users = {key: self.user(email, name) for key, email, name, _, _ in PEOPLE}
        lab = Lab.objects.filter(name=LAB_NAME).first()
        if lab is None:
            lab = create_lab(user=users["pi"], name=LAB_NAME)  # placeholder institution
        for key, _, _, role, _ in PEOPLE:
            LabMembership.objects.for_lab(lab).get_or_create(
                lab=lab, user=users[key], defaults={"role": role}
            )
        return lab, users

    def project(self, lab, users):
        project = Project.objects.for_lab(lab).filter(name=PROJECT_NAME).first()
        if project is None:
            project = project_services.create_project(
                lab=lab,
                user=users["lead"],
                data={
                    "name": PROJECT_NAME,
                    "description": (
                        "MBP-tagged ST6GAL1 variants expressed in SHuffle E. coli, purified on "
                        "Ni-NTA and assayed with CMP-Neu5Ac. Demo data, all made up."
                    ),
                    "status": "active",
                },
            )
        for key, _, _, _, role in PEOPLE:
            on_project = ProjectMembership.objects.for_lab(lab).filter(
                project=project, user=users[key]
            )
            if role and role != "lead" and not on_project.exists():
                project_services.add_member(
                    project=project, by=users["lead"], user_id=users[key].pk, role=role
                )
        return project

    def drop_files(self, lab, project, user):
        """Each demo file goes onto its instrument through the drop page's service, then is
        parsed here and now. Eager Celery keeps the service's after-commit queueing off the
        broker (it finds the file already parsed and does nothing)."""
        from config.celery import app

        app.conf.task_always_eager = True
        for filename, instrument_name in FILES.items():
            instrument = InventoryItem.objects.for_lab(lab).get(name=instrument_name)
            done = InstrumentFile.objects.for_lab(lab).filter(
                instrument=instrument, attachment__original_filename=filename
            )
            if done.exists():
                continue
            item = drop_file(
                instrument=instrument,
                project=project,
                user=user,
                file=SimpleUploadedFile(filename, (DEMO_FILES / filename).read_bytes()),
                via=UploadedVia.PAGE,
            )
            parse_instrument_file(str(item.pk), str(lab.pk))

    def link_plasmid(self, lab, project, user):
        """P0001 (the CST-06 plasmid) joins the demo project and gets a small fake map."""
        plasmid = Sample.objects.for_lab(lab).filter(name="pCW-MalE-CST06 (FAKE)").first()
        if plasmid is None:
            return
        plasmid.projects.add(project)
        if not plasmid.attachments.filter(deleted_at__isnull=True).exists():
            sample_services.upload_file(
                plasmid,
                user=user,
                file=SimpleUploadedFile(
                    "pCW-MalE-CST06_map.gb", PLASMID_MAP.encode(), content_type="text/plain"
                ),
            )

    def link_batch(self, lab, project):
        """The purified enzyme batch points at its NanoDrop reading and its ÄKTA run."""
        batch = Sample.objects.for_lab(lab).filter(name="MBP-CST06 batch 2 (FAKE)").first()
        if batch is None:
            return
        files = InstrumentFile.objects.for_lab(lab).filter(
            instrument__name__in=["NanoDrop 8000", "ÄKTA pure 25"]
        )
        batch.projects.add(project)
        batch.linked_files.add(*[f.attachment for f in files])

    def summary(self, lab):
        self.stdout.write(f"Demo lab: {LAB_NAME}  ({settings.FRONTEND_URL})")
        for f in InstrumentFile.objects.for_lab(lab).select_related("instrument", "attachment"):
            self.stdout.write(
                f"  {f.instrument.name}: {f.attachment.original_filename} -> {f.status}"
            )
        self.stdout.write(
            "Live sensor demo: open Monitoring, pick a sensor, make a device token under "
            "Connect, then run:\n"
            "  python manage.py simulate_sensor <token> --count 40 --every 15\n"
            "(a door opens at reading 10 and raises an alert). Sensor readings are set to "
            "now each time this command runs, and go quiet after a week."
        )
        shown = PASSWORD if self.password == PASSWORD else "the QA_PASSWORD setting"
        self.stdout.write(f"Password: {shown}")
        self.stdout.write("Logins (all share the password above):")
        for _, email, _, role, project_role in PEOPLE:
            extra = f", project {project_role}" if project_role else ""
            self.stdout.write(f"  {email}  ({role}{extra})")
