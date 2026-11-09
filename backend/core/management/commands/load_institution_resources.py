"""Add the starter and national links (core/institution_starters.py) to every lab.
Idempotent (D149). `--set-lab <name>` first points that lab at the University of Alberta."""

from django.core.management.base import BaseCommand, CommandError

from core.institution_starters import UALBERTA
from core.models import Institution
from labs.admin_services import apply_starter_resources
from labs.models import Lab


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--set-lab", help="Name of a lab to move to the University of Alberta")

    def handle(self, *args, **opts):
        if name := opts["set_lab"]:
            lab = Lab.objects.filter(name=name).first()
            if lab is None:
                raise CommandError(f"No lab named {name!r}")
            lab.institution, _ = Institution.objects.get_or_create(name=UALBERTA)
            lab.save()
        added = 0
        for lab in Lab.objects.select_related("institution"):
            added += apply_starter_resources(lab)
        self.stdout.write(f"Added {added} starter link(s).")
